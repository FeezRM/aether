import { createContext, useContext } from 'react'
import type { PageViewport, PDFDocumentProxy } from './pdf'
import type { DocInfo, Gesture, PageDetail, SearchHit } from './types'

export type GestureKind = 'none' | 'click' | 'drag' | 'ink' | 'poly' | 'text'

export interface PromptField {
  name: string
  label: string
  type?: 'text' | 'password' | 'textarea' | 'number' | 'select' | 'checkbox'
  value?: string | number | boolean
  options?: string[]
  placeholder?: string
}

export interface ToolLayerProps {
  page: number
  viewport: PageViewport
}

export interface Tool {
  id: string
  label: string
  gesture: GestureKind
  hint?: string
  cursor?: string
  onGesture?: (g: Gesture, ed: Editor) => Promise<void> | void
  /** Extra per-page layer drawn over the page while this tool is active. */
  Layer?: (props: ToolLayerProps) => React.ReactNode
}

export interface ToolGroup {
  id: string
  label: string
  description: string
  icon: string
  tools: Tool[]
  /** Options / actions shown in the right panel when this group is open. */
  Panel?: () => React.ReactNode
  needsDoc?: boolean
}

export interface Editor {
  info: DocInfo | null
  docs: { id: string; name: string; dirty: boolean }[]
  pdf: PDFDocumentProxy | null
  zoom: number
  setZoom: (z: number) => void
  page: number
  /** Scroll to a page. */
  goTo: (page: number) => void
  /** Record the page in view without scrolling. */
  setPage: (page: number) => void
  group: string | null
  setGroup: (g: string | null) => void
  tool: Tool | null
  setTool: (id: string | null) => void
  opts: Record<string, unknown>
  setOpt: (key: string, value: unknown) => void
  runOp: <R = Record<string, unknown>>(name: string, params: object) => Promise<R | null>
  setInfo: (info: DocInfo) => void
  openInfo: (info: DocInfo) => void
  switchDoc: (id: string) => void
  closeDoc: (id: string) => void
  selectedPages: number[]
  setSelectedPages: (p: number[]) => void
  selectedAnnot: number | null
  setSelectedAnnot: (xref: number | null) => void
  notify: (msg: string, kind?: 'info' | 'error' | 'success') => void
  prompt: (title: string, fields: PromptField[], ok?: string) => Promise<Record<string, string> | null>
  pageDetail: (page: number) => Promise<PageDetail>
  hits: SearchHit[]
  setHits: (h: SearchHit[]) => void
  busy: string | null
  withBusy: <T>(label: string, fn: () => Promise<T>) => Promise<T | null>
  pickFile: (accept: string, multiple?: boolean) => Promise<File[]>
  openModal: (node: React.ReactNode) => void
  closeModal: () => void
}

export const EditorContext = createContext<Editor | null>(null)

export function useEditor(): Editor {
  const ed = useContext(EditorContext)
  if (!ed) throw new Error('useEditor outside EditorContext')
  return ed
}

export function opt(ed: Editor, key: string, fallback: string): string
export function opt(ed: Editor, key: string, fallback: number): number
export function opt(ed: Editor, key: string, fallback: boolean): boolean
export function opt<T>(ed: Editor, key: string, fallback: T): T
export function opt<T>(ed: Editor, key: string, fallback: T): T {
  const v = ed.opts[key]
  return (v === undefined ? fallback : v) as T
}

export function today(): string {
  return new Date().toLocaleDateString()
}
