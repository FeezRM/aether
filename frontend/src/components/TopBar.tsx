import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import { useEditor } from '../editor'

export function TopBar({ onOpen, onSave }: { onOpen: () => void; onSave: (as: boolean) => void }) {
  const ed = useEditor()
  const info = ed.info
  const [query, setQuery] = useState('')
  const [searched, setSearched] = useState('')
  const [hitIndex, setHitIndex] = useState(0)
  const [speaking, setSpeaking] = useState(false)
  const [pageInput, setPageInput] = useState('')
  const searchRef = useRef<HTMLInputElement>(null)

  useEffect(() => setPageInput(info ? String(ed.page + 1) : ''), [ed.page, info])
  useEffect(() => {
    const focus = () => searchRef.current?.focus()
    window.addEventListener('localpdf:find', focus)
    return () => window.removeEventListener('localpdf:find', focus)
  }, [])

  const runSearch = async () => {
    if (!info) return
    if (!query.trim()) return ed.setHits([])
    const hits = await api.search(info.id, query)
    ed.setHits(hits)
    setSearched(query)
    setHitIndex(0)
    if (hits.length) ed.goTo(hits[0].page)
    else ed.notify(`No matches for “${query}”`)
  }

  const step = (d: number) => {
    if (!ed.hits.length) return
    const i = (hitIndex + d + ed.hits.length) % ed.hits.length
    setHitIndex(i)
    ed.goTo(ed.hits[i].page)
  }

  const print = () => {
    if (!info) return
    const frame = document.createElement('iframe')
    frame.style.display = 'none'
    frame.src = api.fileUrl(info.id, info.version)
    frame.onload = () => frame.contentWindow?.print()
    document.body.appendChild(frame)
    setTimeout(() => frame.remove(), 60_000)
  }

  const readAloud = async () => {
    if (speaking) {
      speechSynthesis.cancel()
      setSpeaking(false)
      return
    }
    if (!ed.pdf) return
    const page = await ed.pdf.getPage(ed.page + 1)
    const content = await page.getTextContent()
    const text = content.items.map((i) => ('str' in i ? i.str : '')).join(' ')
    if (!text.trim()) return ed.notify('No text on this page (try Scan & OCR)')
    const u = new SpeechSynthesisUtterance(text)
    u.onend = () => setSpeaking(false)
    speechSynthesis.speak(u)
    setSpeaking(true)
  }

  return (
    <header className="topbar">
      <div className="brand" title="Everything runs on this computer">
        <span className="logo">◆</span> LocalPDF <span className="local-badge">100% local</span>
      </div>
      <div className="group">
        <button onClick={onOpen} title="Open (⌘O)">Open</button>
        <button onClick={() => onSave(false)} disabled={!info} title="Save (⌘S)">Save{info?.dirty ? ' •' : ''}</button>
        <button onClick={() => onSave(true)} disabled={!info}>Save As…</button>
        <button onClick={() => info && api.download(info.id, info.name)} disabled={!info}>Download</button>
        <button onClick={print} disabled={!info}>Print</button>
      </div>
      <div className="group">
        <button onClick={() => info && api.undo(info.id).then(ed.setInfo).catch((e) => ed.notify(e.message, 'error'))}
          disabled={!info?.can_undo} title="Undo (⌘Z)">↶</button>
        <button onClick={() => info && api.redo(info.id).then(ed.setInfo).catch((e) => ed.notify(e.message, 'error'))}
          disabled={!info?.can_redo} title="Redo (⇧⌘Z)">↷</button>
      </div>
      <div className="group">
        <button onClick={() => ed.setZoom(Math.max(0.25, ed.zoom - 0.1))} disabled={!info}>−</button>
        <span className="zoom">{Math.round(ed.zoom * 100)}%</span>
        <button onClick={() => ed.setZoom(Math.min(4, ed.zoom + 0.1))} disabled={!info}>+</button>
        <button onClick={() => {
          const el = document.querySelector('.viewer')
          const page = info?.pages[ed.page]
          if (el && page) {
            const w = page.rotation % 180 ? page.height : page.width
            ed.setZoom(Math.max(0.25, Math.min(4, (el.clientWidth - 64) / w)))
          }
        }} disabled={!info} title="Fit width">⇔</button>
      </div>
      {info && (
        <div className="group">
          <input className="page-input" value={pageInput} onChange={(e) => setPageInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key !== 'Enter') return
              const n = Number(pageInput)
              if (n >= 1 && n <= info.page_count) ed.goTo(n - 1)
            }} />
          <span className="muted">/ {info.page_count}</span>
        </div>
      )}
      <div className="group search">
        <input ref={searchRef} placeholder="Find in document (⌘F)" value={query} disabled={!info}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              if (query === searched && ed.hits.length) step(e.shiftKey ? -1 : 1)
              else void runSearch()
            }
            if (e.key === 'Escape') { setQuery(''); ed.setHits([]) }
          }} />
        {ed.hits.length > 0 && <span className="muted small">{hitIndex + 1}/{ed.hits.length}</span>}
        {ed.hits.length > 0 && <button className="small" onClick={() => { setQuery(''); ed.setHits([]) }}>×</button>}
      </div>
      <div className="group">
        <button className={ed.group === 'assistant' ? 'active' : ''} disabled={!info} title="Ask questions or request edits (runs locally)"
          onClick={() => { ed.setGroup(ed.group === 'assistant' ? null : 'assistant'); ed.setTool(null) }}>✦ Ask AI</button>
        <button onClick={readAloud} disabled={!info} title="Read the current page aloud (local voice)">
          {speaking ? '⏹ Stop' : '🔊 Read'}
        </button>
      </div>
      {ed.busy && <div className="busy">⏳ {ed.busy}…</div>}
    </header>
  )
}
