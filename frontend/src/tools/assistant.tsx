import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from 'react'
import { ai, api, type ChatEvent, type ModelStatus, type ModelTier } from '../api'
import { useEditor, type Editor, type ToolGroup } from '../editor'
import type { SearchHit } from '../types'

interface Step {
  tool: string
  text: string
  ok?: boolean
  detail?: string
}

interface Msg {
  role: 'user' | 'assistant'
  text: string
  steps: Step[]
  citations: SearchHit[]
  confirm?: { turn: string; text: string; state: 'pending' | 'approved' | 'declined' }
  changed?: boolean
  undone?: boolean
  error?: string
  pending?: boolean
}

// Conversations per document, kept outside the panel so they survive switching tools.
const EMPTY: Msg[] = []
const chats = new Map<string, Msg[]>()
const listeners = new Set<() => void>()

function subscribe(listener: () => void) {
  listeners.add(listener)
  return () => { listeners.delete(listener) }
}

function setChat(docId: string, msgs: Msg[]) {
  chats.set(docId, msgs)
  listeners.forEach((l) => l())
}

function patchLast(docId: string, fn: (m: Msg) => Msg) {
  const msgs = chats.get(docId) ?? []
  if (msgs.length) setChat(docId, [...msgs.slice(0, -1), fn(msgs[msgs.length - 1])])
}

function useChat(docId: string): Msg[] {
  return useSyncExternalStore(subscribe, () => chats.get(docId) ?? EMPTY)
}

function apply(ed: Editor, m: Msg, e: ChatEvent): Msg {
  switch (e.type) {
    case 'token':
      return { ...m, text: m.text + e.text }
    case 'tool_call':
      return { ...m, steps: [...m.steps, { tool: e.tool, text: e.text }] }
    case 'tool_result': {
      const last = m.steps[m.steps.length - 1]
      const detail = e.ok ? undefined : e.text
      if (last?.tool === e.tool && last.ok === undefined) {
        return { ...m, steps: [...m.steps.slice(0, -1), { ...last, ok: e.ok, detail }] }
      }
      return { ...m, steps: [...m.steps, { tool: e.tool, text: e.tool, ok: e.ok, detail }] }
    }
    case 'confirm':
      return { ...m, confirm: { turn: e.turn, text: e.text, state: 'pending' } }
    case 'doc_changed':
      ed.setInfo(e.info)
      return m
    case 'citations':
      return { ...m, citations: e.citations }
    case 'done':
      return { ...m, changed: e.changed }
    case 'error':
      return { ...m, error: e.text }
    default:
      return m
  }
}

async function send(ed: Editor, docId: string, text: string) {
  const prior = chats.get(docId) ?? []
  const history = prior.filter((m) => !m.error && m.text).map((m) => ({ role: m.role, content: m.text }))
  setChat(docId, [...prior, { role: 'user', text, steps: [], citations: [] },
    { role: 'assistant', text: '', steps: [], citations: [], pending: true }])
  try {
    await ai.chat(docId, text, history, (e) => patchLast(docId, (m) => apply(ed, m, e)))
  } catch (err) {
    patchLast(docId, (m) => ({ ...m, error: (err as Error).message }))
  }
  patchLast(docId, (m) => ({ ...m, pending: false }))
}

function formatSize(bytes: number) {
  return bytes >= 1e9 ? `${(bytes / 1e9).toFixed(1)} GB` : `${Math.round(bytes / 1e6)} MB`
}

const CITE = /(\[p\.?\s?\d+\])/i

function AnswerText({ m }: { m: Msg }) {
  const ed = useEditor()
  return (
    <div className="chat-text">
      {m.text.split(CITE).map((part, i) => {
        const n = CITE.test(part) ? Number(/\d+/.exec(part)![0]) : null
        if (n === null) return <span key={i}>{part}</span>
        const hit = m.citations.find((c) => c.page === n - 1)
        return (
          <button key={i} className="cite" title={hit?.context ?? `Page ${n}`} onClick={() => {
            ed.goTo(n - 1)
            if (hit) ed.setHits([hit])
          }}>p{n}</button>
        )
      })}
    </div>
  )
}

function Message({ m, docId, latestChange }: { m: Msg; docId: string; latestChange: boolean }) {
  const ed = useEditor()
  if (m.role === 'user') return <div className="chat-msg user">{m.text}</div>
  const decide = (approve: boolean) => {
    if (!m.confirm) return
    const turn = m.confirm.turn
    patchLast(docId, (x) => x.confirm ? { ...x, confirm: { ...x.confirm, state: approve ? 'approved' : 'declined' } } : x)
    ai.confirm(turn, approve).catch((e) => ed.notify(e.message, 'error'))
  }
  return (
    <div className="chat-msg assistant" data-pending={m.pending || undefined}>
      {m.steps.length > 0 && (
        <ul className="chat-steps">
          {m.steps.map((s, i) => (
            <li key={i} className={s.ok === false ? 'failed' : ''}>
              {s.ok === undefined ? '…' : s.ok ? '✓' : '✗'} {s.text}
              {s.detail && <span className="muted"> — {s.detail}</span>}
            </li>
          ))}
        </ul>
      )}
      {m.confirm && (
        <div className="chat-confirm">
          <span>{m.confirm.text}?</span>
          {m.confirm.state === 'pending' ? (
            <div className="row">
              <button className="primary" onClick={() => decide(true)}>Approve</button>
              <button onClick={() => decide(false)}>Cancel</button>
            </div>
          ) : <span className="muted small">{m.confirm.state === 'approved' ? 'Approved' : 'Cancelled'}</span>}
        </div>
      )}
      {m.text && <AnswerText m={m} />}
      {m.pending && !m.text && !m.confirm && <div className="muted small">Thinking…</div>}
      {m.error && <div className="chat-error">{m.error}</div>}
      {m.changed && !m.pending && latestChange && (
        m.undone ? <div className="muted small">Changes undone.</div> : (
          <button className="link small" onClick={() => {
            if (!ed.info) return
            api.undo(ed.info.id).then((info) => {
              ed.setInfo(info)
              const msgs = chats.get(docId) ?? []
              setChat(docId, msgs.map((x) => x === m ? { ...x, undone: true } : x))
            }).catch((e) => ed.notify(e.message, 'error'))
          }}>↶ Undo these changes</button>
        )
      )}
    </div>
  )
}

function TierCard({ tier, recommended, onChange }: {
  tier: ModelTier
  recommended: boolean
  onChange: (p: Promise<ModelStatus>) => void
}) {
  const dl = tier.download
  const downloading = dl?.state === 'downloading'
  return (
    <div className={`card tier ${tier.active ? 'active' : ''}`}>
      <div className="row between">
        <strong>{tier.label}</strong>
        <span className="muted small">{formatSize(tier.size)}</span>
      </div>
      {recommended && <span className="badge recommended">Recommended for this computer</span>}
      <span className="small">{tier.description}</span>
      {downloading ? (
        <>
          <progress value={dl.received} max={dl.total || 1} />
          <div className="row between">
            <span className="muted small">{formatSize(dl.received)} of {formatSize(dl.total)}</span>
            <button className="small" onClick={() => onChange(ai.cancel(tier.id))}>Cancel</button>
          </div>
        </>
      ) : tier.installed ? (
        <div className="row">
          {tier.active ? <span className="muted small">✓ In use</span>
            : <button className="small primary" onClick={() => onChange(ai.activate(tier.id))}>Use {tier.label}</button>}
          <button className="small danger" onClick={() => onChange(ai.remove(tier.id))}>Delete</button>
        </div>
      ) : (
        <button className="primary" onClick={() => onChange(ai.download(tier.id))}>Download {tier.label}</button>
      )}
      {dl?.state === 'error' && <span className="chat-error small">{dl.error}</span>}
    </div>
  )
}

function ModelSetup({ status, onChange }: { status: ModelStatus; onChange: (p: Promise<ModelStatus>) => void }) {
  if (!status.runtime) {
    return (
      <p className="hint">The AI runtime isn't installed. Run <code>./start.sh</code> again to install it.</p>
    )
  }
  return (
    <div className="tier-list">
      <p className="small">
        The assistant runs entirely on this computer. Pick a model to download once; after that it works
        offline and your documents never leave this machine.
      </p>
      {status.tiers.map((t) => (
        <TierCard key={t.id} tier={t} recommended={t.id === status.recommended} onChange={onChange} />
      ))}
      <p className="muted small">Downloading a model is the only time Aether connects to the internet.</p>
    </div>
  )
}

const SUGGESTIONS = ['Summarize this document', 'What are the key dates and deadlines?', 'Highlight every email address']

function AssistantPanel() {
  const ed = useEditor()
  const docId = ed.info!.id
  const msgs = useChat(docId)
  const [status, setStatus] = useState<ModelStatus | null>(null)
  const [showModels, setShowModels] = useState(false)
  const [input, setInput] = useState('')
  const endRef = useRef<HTMLDivElement>(null)
  const busy = msgs[msgs.length - 1]?.pending ?? false

  const notify = ed.notify
  const update = useCallback((p: Promise<ModelStatus>) => {
    p.then(setStatus).catch((e) => notify(e.message, 'error'))
  }, [notify])
  useEffect(() => update(ai.models()), [update])
  const downloading = status?.tiers.some((t) => t.download?.state === 'downloading')
  useEffect(() => {
    if (!downloading) return
    const timer = setInterval(() => update(ai.models()), 800)
    return () => clearInterval(timer)
  }, [downloading, update])
  useEffect(() => endRef.current?.scrollIntoView({ block: 'end' }), [msgs])

  if (!status) return <p className="muted small">Loading…</p>
  if (!status.active || showModels || !status.runtime) {
    return (
      <>
        {status.active && <button className="link small" onClick={() => setShowModels(false)}>← Back to chat</button>}
        <ModelSetup status={status} onChange={update} />
      </>
    )
  }

  const submit = (text: string) => {
    if (!text.trim() || busy) return
    setInput('')
    void send(ed, docId, text.trim())
  }
  const lastChange = msgs.reduce((at, m, i) => (m.changed ? i : at), -1)
  const tier = status.tiers.find((t) => t.active)

  return (
    <div className="chat">
      <div className="row between">
        <span className="muted small">🔒 {tier?.label} model, on this computer</span>
        <button className="link small" onClick={() => setShowModels(true)}>Models</button>
      </div>
      <div className="chat-log">
        {msgs.length === 0 && (
          <div className="chat-empty">
            <p className="muted small">Ask about this PDF, or tell me what to change.</p>
            {SUGGESTIONS.map((s) => <button key={s} className="small" onClick={() => submit(s)}>{s}</button>)}
          </div>
        )}
        {msgs.map((m, i) => <Message key={i} m={m} docId={docId} latestChange={i === lastChange} />)}
        <div ref={endRef} />
      </div>
      <div className="chat-input">
        <textarea rows={2} value={input} placeholder={busy ? 'Working…' : 'Ask or describe a change'}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit(input) }
          }} />
        <button className="primary" disabled={busy || !input.trim()} onClick={() => submit(input)}>Send</button>
      </div>
    </div>
  )
}

export const assistantGroup: ToolGroup = {
  id: 'assistant',
  label: 'Ask AI',
  icon: '✦',
  description: 'Ask questions about this PDF or tell it what to change. Runs on this computer',
  needsDoc: true,
  tools: [],
  Panel: AssistantPanel,
}
