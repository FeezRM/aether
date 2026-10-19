import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { ApiError, api } from './api'
import { PageGrid } from './components/PageGrid'
import { Modal, PromptDialog, type PromptState } from './components/Modal'
import { pageRegistry } from './components/PageView'
import { Sidebar } from './components/Sidebar'
import { ToolsPanel } from './components/ToolsPanel'
import { TopBar } from './components/TopBar'
import { Viewer } from './components/Viewer'
import { Welcome } from './components/Welcome'
import { EditorContext, type Editor, type PromptField } from './editor'
import { loadPdf, type PDFDocumentProxy } from './pdf'
import { TOOLS } from './tools'
import type { DocInfo, PageDetail, SearchHit } from './types'

interface Toast { id: number; msg: string; kind: 'info' | 'error' | 'success' }

export default function App() {
  const [infos, setInfos] = useState<Record<string, DocInfo>>({})
  const [order, setOrder] = useState<string[]>([])
  const [activeId, setActiveId] = useState<string | null>(null)
  const [pdf, setPdf] = useState<PDFDocumentProxy | null>(null)
  const [zoom, setZoom] = useState(1.2)
  const [page, setPage] = useState(0)
  const [group, setGroup] = useState<string | null>(null)
  const [toolId, setToolId] = useState<string | null>(null)
  const [opts, setOpts] = useState<Record<string, unknown>>({})
  const [selectedPages, setSelectedPages] = useState<number[]>([])
  const [selectedAnnot, setSelectedAnnot] = useState<number | null>(null)
  const [hits, setHits] = useState<SearchHit[]>([])
  const [busy, setBusy] = useState<string | null>(null)
  const [toasts, setToasts] = useState<Toast[]>([])
  const [prompt, setPrompt] = useState<PromptState | null>(null)
  const [modal, setModal] = useState<React.ReactNode>(null)
  const detailCache = useRef(new Map<string, Promise<PageDetail>>())
  const fileInput = useRef<HTMLInputElement>(null)

  const info = activeId ? infos[activeId] ?? null : null

  const notify = useCallback((msg: string, kind: Toast['kind'] = 'info') => {
    const id = Date.now() + Math.random()
    setToasts((t) => [...t, { id, msg, kind }])
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), kind === 'error' ? 7000 : 4000)
  }, [])

  const askPrompt = useCallback((title: string, fields: PromptField[], ok = 'OK') =>
    new Promise<Record<string, string> | null>((resolve) => setPrompt({ title, fields, ok, resolve })), [])

  const setInfo = useCallback((next: DocInfo) => {
    setInfos((m) => ({ ...m, [next.id]: next }))
  }, [])

  const openInfo = useCallback((next: DocInfo) => {
    setInfos((m) => ({ ...m, [next.id]: next }))
    setOrder((o) => (o.includes(next.id) ? o : [...o, next.id]))
    setActiveId(next.id)
    setPage(0)
    setSelectedPages([])
    setHits([])
  }, [])

  // Load the rendered document whenever the active document or its version changes.
  useEffect(() => {
    if (!info) {
      setPdf(null)
      return
    }
    let live = true
    let loaded: PDFDocumentProxy | null = null
    loadPdf(api.fileUrl(info.id, info.version))
      .then((d) => {
        loaded = d
        if (live) setPdf(d)
        else void d.loadingTask.destroy()
      })
      .catch((e) => notify(`Could not render: ${e.message}`, 'error'))
    return () => {
      live = false
      if (loaded) setTimeout(() => void loaded?.loadingTask.destroy(), 2000)
    }
  }, [info?.id, info?.version, notify])

  const withBusy = useCallback(async <T,>(label: string, fn: () => Promise<T>): Promise<T | null> => {
    setBusy(label)
    try {
      return await fn()
    } catch (e) {
      notify((e as Error).message, 'error')
      return null
    } finally {
      setBusy(null)
    }
  }, [notify])

  const runOp = useCallback(async <R,>(name: string, params: object): Promise<R | null> => {
    if (!activeId) return null
    setBusy(name.replace(/_/g, ' '))
    try {
      const res = await api.op<R>(activeId, name, params)
      setInfo(res.info)
      return (res.result ?? ({} as R))
    } catch (e) {
      if (e instanceof ApiError && e.status === 403) {
        const v = await askPrompt('This document is protected', [
          { name: 'pw', label: e.message, type: 'password' },
        ], 'Unlock')
        if (v?.pw) {
          try {
            await api.unlock(activeId, v.pw)
            const res = await api.op<R>(activeId, name, params)
            setInfo(res.info)
            return (res.result ?? ({} as R))
          } catch (err) {
            notify((err as Error).message, 'error')
          }
        }
      } else {
        notify((e as Error).message, 'error')
      }
      return null
    } finally {
      setBusy(null)
    }
  }, [activeId, askPrompt, notify, setInfo])

  const pickFile = useCallback((accept: string, multiple = false) => new Promise<File[]>((resolve) => {
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = accept
    input.multiple = multiple
    input.onchange = () => resolve(Array.from(input.files ?? []))
    input.oncancel = () => resolve([])
    input.click()
  }), [])

  const openFiles = useCallback(async (files: File[]) => {
    for (const file of files) {
      try {
        openInfo(await api.upload(file))
      } catch (e) {
        if (e instanceof ApiError && e.status === 401) {
          const v = await askPrompt(`“${file.name}” is password protected`, [{ name: 'pw', label: 'Password', type: 'password' }], 'Open')
          if (v?.pw) await api.upload(file, v.pw).then(openInfo).catch((err) => notify(err.message, 'error'))
        } else notify(`${file.name}: ${(e as Error).message}`, 'error')
      }
    }
  }, [askPrompt, notify, openInfo])

  const openPath = useCallback(async () => {
    const v = await askPrompt('Open from path', [{ name: 'path', label: 'Full path to a PDF', placeholder: '~/Documents/file.pdf' }], 'Open')
    if (!v?.path) return
    try {
      openInfo(await api.openPath(v.path))
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) {
        const p = await askPrompt('Password required', [{ name: 'pw', label: 'Password', type: 'password' }], 'Open')
        if (p?.pw) await api.openPath(v.path, p.pw).then(openInfo).catch((err) => notify(err.message, 'error'))
      } else notify((e as Error).message, 'error')
    }
  }, [askPrompt, notify, openInfo])

  const save = useCallback(async (as: boolean) => {
    if (!info) return
    let path: string | undefined
    if (as || !info.source_path) {
      const v = await askPrompt('Save as', [{ name: 'path', label: 'Save to (full path)', value: info.source_path ?? `~/Documents/${info.name}` }], 'Save')
      if (!v?.path) return
      path = v.path
    }
    const saved = await withBusy('Saving', () => api.save(info.id, path))
    if (saved) {
      setInfo(saved)
      notify(`Saved to ${saved.source_path}`, 'success')
    }
  }, [askPrompt, info, notify, setInfo, withBusy])

  const closeDoc = useCallback(async (id: string) => {
    if (infos[id]?.dirty && !confirm(`Close “${infos[id].name}” without saving?`)) return
    await api.close(id)
    setInfos((m) => {
      const { [id]: _gone, ...rest } = m
      return rest
    })
    setOrder((o) => {
      const next = o.filter((x) => x !== id)
      if (activeId === id) setActiveId(next[next.length - 1] ?? null)
      return next
    })
  }, [activeId, infos])

  const goTo = useCallback((p: number) => {
    setPage(p)
    pageRegistry.get(p)?.el.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }, [])

  const pageDetail = useCallback((p: number) => {
    if (!info) return Promise.reject(new Error('No document'))
    const key = `${info.id}:${info.version}:${p}`
    let pending = detailCache.current.get(key)
    if (!pending) {
      pending = api.page(info.id, p)
      detailCache.current.set(key, pending)
    }
    return pending
  }, [info])

  const editor: Editor = useMemo(() => ({
    info, pdf, zoom, setZoom, page, goTo, setPage, group,
    docs: order.map((id) => ({ id, name: infos[id]?.name ?? '', dirty: infos[id]?.dirty ?? false })),
    setGroup: (g) => { setGroup(g); setSelectedAnnot(null) },
    tool: toolId ? TOOLS[toolId] ?? null : null,
    setTool: (id) => { setToolId(id); setSelectedAnnot(null) },
    opts, setOpt: (k, v) => setOpts((o) => ({ ...o, [k]: v })),
    runOp, setInfo, openInfo, switchDoc: setActiveId, closeDoc,
    selectedPages, setSelectedPages, selectedAnnot, setSelectedAnnot,
    notify, prompt: askPrompt, pageDetail, hits, setHits, busy, withBusy, pickFile,
    openModal: setModal, closeModal: () => setModal(null),
  }), [info, pdf, zoom, page, goTo, group, order, infos, toolId, opts, runOp, setInfo, openInfo, closeDoc,
    selectedPages, selectedAnnot, notify, askPrompt, pageDetail, hits, busy, withBusy, pickFile])

  // Keyboard shortcuts.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const typing = (e.target as HTMLElement).closest('input, textarea, select')
      const mod = e.metaKey || e.ctrlKey
      if (mod && e.key.toLowerCase() === 'o') { e.preventDefault(); fileInput.current?.click() }
      if (mod && e.key.toLowerCase() === 's') { e.preventDefault(); void save(e.shiftKey) }
      if (mod && e.key.toLowerCase() === 'f') { e.preventDefault(); window.dispatchEvent(new Event('localpdf:find')) }
      if (typing || !info) return
      if (mod && e.key.toLowerCase() === 'z') {
        e.preventDefault()
        const call = e.shiftKey ? api.redo : api.undo
        call(info.id).then(setInfo).catch((err) => notify(err.message, 'error'))
      }
      if (e.key === 'Escape') { setToolId(null); setSelectedAnnot(null) }
      if (e.key === 'Delete' || e.key === 'Backspace') {
        const a = info.annotations.find((x) => x.xref === selectedAnnot)
        if (a) { void runOp('delete_annotation', { page: a.page, xref: a.xref }); setSelectedAnnot(null) }
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [info, save, setInfo, notify, selectedAnnot, runOp])

  // Warn before losing unsaved work.
  useEffect(() => {
    const dirty = Object.values(infos).some((i) => i.dirty)
    const onUnload = (e: BeforeUnloadEvent) => { if (dirty) e.preventDefault() }
    window.addEventListener('beforeunload', onUnload)
    return () => window.removeEventListener('beforeunload', onUnload)
  }, [infos])

  const organizing = group === 'organize' && info

  return (
    <EditorContext.Provider value={editor}>
      <div className="app"
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault()
          const files = Array.from(e.dataTransfer.files).filter((f) => f.name.toLowerCase().endsWith('.pdf'))
          if (files.length) void openFiles(files)
        }}>
        <TopBar onOpen={() => fileInput.current?.click()} onSave={save} />
        {order.length > 0 && (
          <nav className="doc-tabs">
            {order.map((id) => (
              <div key={id} className={`doc-tab ${id === activeId ? 'active' : ''}`} onClick={() => setActiveId(id)}>
                <span className="ellipsis">{infos[id]?.dirty ? '• ' : ''}{infos[id]?.name}</span>
                <button className="icon" onClick={(e) => { e.stopPropagation(); void closeDoc(id) }}>×</button>
              </div>
            ))}
          </nav>
        )}
        <main className="workspace">
          {info && <Sidebar />}
          <section className="center">
            {!info ? (
              <Welcome onOpen={() => fileInput.current?.click()} onOpenPath={openPath}
                onBlank={() => void withBusy('Creating', () => api.blank()).then((i) => i && openInfo(i))} />
            ) : organizing ? <PageGrid /> : <Viewer />}
          </section>
          <ToolsPanel />
        </main>
        <input ref={fileInput} type="file" accept=".pdf,application/pdf" multiple hidden
          onChange={(e) => { void openFiles(Array.from(e.target.files ?? [])); e.target.value = '' }} />
        {prompt && <PromptDialog state={prompt} onClose={() => setPrompt(null)} />}
        {modal && <Modal onClose={() => setModal(null)}>{modal}</Modal>}
        <div className="toasts">
          {toasts.map((t) => <div key={t.id} className={`toast ${t.kind}`}>{t.msg}</div>)}
        </div>
      </div>
    </EditorContext.Provider>
  )
}
