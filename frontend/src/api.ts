import type { DocInfo, PageDetail, SearchHit } from './types'

export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

async function check(res: Response): Promise<Response> {
  if (!res.ok) {
    let detail = res.statusText
    try {
      detail = (await res.json()).detail ?? detail
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(detail, res.status)
  }
  return res
}

async function json<T>(url: string, init?: RequestInit): Promise<T> {
  return (await check(await fetch(url, init))).json()
}

const post = <T>(url: string, body: unknown = {}) =>
  json<T>(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })

/** Download a response as a file through the browser. */
export async function saveResponse(res: Response, fallback: string) {
  await check(res)
  const cd = res.headers.get('Content-Disposition') ?? ''
  const name = /filename="([^"]+)"/.exec(cd)?.[1] ?? fallback
  const url = URL.createObjectURL(await res.blob())
  const a = document.createElement('a')
  a.href = url
  a.download = name
  a.click()
  setTimeout(() => URL.revokeObjectURL(url), 5000)
}

export const api = {
  upload(file: File, password?: string) {
    const fd = new FormData()
    fd.append('file', file)
    if (password) fd.append('password', password)
    return json<DocInfo>('/api/documents', { method: 'POST', body: fd })
  },
  openPath: (path: string, password?: string) => post<DocInfo>('/api/documents/open-path', { path, password }),
  blank: (pages = 1, size = 'letter') => post<DocInfo>('/api/documents/blank', { pages, size }),
  info: (id: string) => json<DocInfo>(`/api/documents/${id}`),
  close: (id: string) => fetch(`/api/documents/${id}`, { method: 'DELETE' }),
  fileUrl: (id: string, version: number) => `/api/documents/${id}/file?v=${version}`,
  page: (id: string, index: number) => json<PageDetail>(`/api/documents/${id}/pages/${index}`),
  search: (id: string, q: string) => json<SearchHit[]>(`/api/documents/${id}/search?q=${encodeURIComponent(q)}`),
  undo: (id: string) => post<DocInfo>(`/api/documents/${id}/undo`),
  redo: (id: string) => post<DocInfo>(`/api/documents/${id}/redo`),
  save: (id: string, path?: string) => post<DocInfo>(`/api/documents/${id}/save`, path ? { path } : {}),
  unlock: (id: string, password: string) => post<DocInfo>(`/api/documents/${id}/unlock`, { password }),
  op: <R = Record<string, unknown>>(id: string, name: string, params: object) =>
    post<{ result: R; info: DocInfo }>(`/api/documents/${id}/ops/${name}`, params),
  async blob(file: File | Blob, name?: string): Promise<string> {
    const fd = new FormData()
    fd.append('file', file, name ?? (file as File).name ?? 'upload')
    return (await json<{ id: string }>('/api/blobs', { method: 'POST', body: fd })).id
  },
  download: (id: string, name: string) => fetch(`/api/documents/${id}/download`).then((r) => saveResponse(r, name)),
  exportAs: (id: string, kind: string) => fetch(`/api/documents/${id}/export/${kind}`).then((r) => saveResponse(r, `export.${kind}`)),
  formData: (id: string, fmt: string) => fetch(`/api/documents/${id}/form-data?fmt=${fmt}`).then((r) => saveResponse(r, `data.${fmt}`)),
  comments: (id: string, fmt: string) => fetch(`/api/documents/${id}/comments?fmt=${fmt}`).then((r) => saveResponse(r, `comments.${fmt}`)),
  extract: (id: string, pages: number[], openAsNew: boolean) =>
    openAsNew
      ? post<DocInfo>(`/api/documents/${id}/extract`, { pages, open_as_new: true })
      : fetch(`/api/documents/${id}/extract`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ pages }),
        }).then((r) => saveResponse(r, 'extract.pdf')),
  split: (id: string, body: object) =>
    fetch(`/api/documents/${id}/split`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
    }).then((r) => saveResponse(r, 'split.zip')),
  combine: (body: object) => post<DocInfo>('/api/combine', body),
  create: (blob_ids: string[]) => post<DocInfo>('/api/create', { blob_ids }),
  compare: (old_id: string, new_id: string) =>
    post<{ report: CompareReport; info: DocInfo }>('/api/compare', { old_id, new_id }),
  accessibility: (id: string) => json<AccessReport>(`/api/documents/${id}/accessibility`),
  signatures: (id: string) => json<SignatureStatus[]>(`/api/documents/${id}/signatures`),
  async digitalId(body: object): Promise<string> {
    const res = await check(await fetch('/api/digital-id', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
    }))
    const blobId = res.headers.get('X-Blob-Id') ?? ''
    await saveResponse(res, 'digital-id.p12')
    return blobId
  },
  batch: (doc_ids: string[], steps: object[]) => post<BatchResult[]>('/api/batch', { doc_ids, steps }),
}

export interface CompareReport {
  old: string
  new: string
  old_pages: number
  new_pages: number
  similarity: number
  counts: Record<string, number>
  changes: { type: string; page: number; old: string; new: string }[]
}

export interface AccessReport {
  passed: number
  failed: number
  manual: number
  checks: { rule: string; status: 'passed' | 'failed' | 'manual'; detail: string }[]
}

export interface SignatureStatus {
  field: string
  signer: string | null
  signed_at: string | null
  intact: boolean
  valid: boolean
  trusted: boolean
  covers_whole_document: boolean
  summary: string
}

export interface BatchResult {
  id: string
  name: string
  ok: boolean
  error?: string
}

// ------------------------------------------------------------- assistant --

export interface ModelTier {
  id: string
  label: string
  description: string
  size: number
  installed: boolean
  active: boolean
  download: { state: 'downloading' | 'done' | 'error' | 'cancelled'; received: number; total: number; error: string | null } | null
}

export interface ModelStatus {
  tiers: ModelTier[]
  recommended: string
  ram: number
  active: string | null
  runtime: boolean
}

export type ChatEvent =
  | { type: 'start'; turn: string }
  | { type: 'route'; category: string }
  | { type: 'token'; text: string }
  | { type: 'tool_call'; tool: string; args: Record<string, unknown>; text: string }
  | { type: 'tool_result'; tool: string; ok: boolean; text?: string; result?: unknown }
  | { type: 'confirm'; turn: string; text: string; tool: string; args: Record<string, unknown> }
  | { type: 'doc_changed'; info: DocInfo }
  | { type: 'citations'; citations: SearchHit[] }
  | { type: 'done'; changed: boolean }
  | { type: 'error'; text: string }

export interface ChatTurn {
  role: 'user' | 'assistant'
  content: string
}

export const ai = {
  models: () => json<ModelStatus>('/api/ai/models'),
  download: (tier: string) => post<ModelStatus>(`/api/ai/models/${tier}/download`),
  cancel: (tier: string) => post<ModelStatus>(`/api/ai/models/${tier}/cancel`),
  activate: (tier: string) => post<ModelStatus>(`/api/ai/models/${tier}/activate`),
  remove: (tier: string) => json<ModelStatus>(`/api/ai/models/${tier}`, { method: 'DELETE' }),
  confirm: (turn: string, approve: boolean) => post(`/api/ai/chat/${turn}/confirm`, { approve }),
  /** Run one assistant turn, calling onEvent for each server-sent event as it arrives. */
  async chat(docId: string, message: string, history: ChatTurn[], onEvent: (e: ChatEvent) => void) {
    const res = await check(await fetch('/api/ai/chat', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ doc_id: docId, message, history }),
    }))
    const reader = res.body!.pipeThrough(new TextDecoderStream()).getReader()
    let buffer = ''
    for (;;) {
      const { value, done } = await reader.read()
      if (done) break
      buffer += value
      let end
      while ((end = buffer.indexOf('\n\n')) >= 0) {
        const frame = buffer.slice(0, end)
        buffer = buffer.slice(end + 2)
        if (frame.startsWith('data: ')) onEvent(JSON.parse(frame.slice(6)) as ChatEvent)
      }
    }
  },
}
