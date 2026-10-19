export type Rect = [number, number, number, number]
export type Point = [number, number]

export interface PageInfo {
  index: number
  width: number
  height: number
  rotation: number
  label: string
}

export interface Annotation {
  page: number
  xref: number
  type: string
  rect: Rect
  contents: string
  author: string
  modified: string
  color: string | null
  reply_to: number | null
}

export interface Field {
  name: string
  type: 'text' | 'checkbox' | 'radio' | 'combobox' | 'listbox' | 'signature' | 'button' | 'unknown'
  value: string | boolean | null
  page: number
  rect: Rect
  options: string[]
  xref: number
  on_state: string | null
  required: boolean
  readonly: boolean
  multiline: boolean
  tooltip: string
}

export interface OutlineItem {
  level: number
  title: string
  page: number
}

export interface DocInfo {
  id: string
  name: string
  version: number
  dirty: boolean
  can_undo: boolean
  can_redo: boolean
  encrypted: boolean
  permissions: Record<string, boolean>
  page_count: number
  pages: PageInfo[]
  metadata: Record<string, string>
  outline: OutlineItem[]
  annotations: Annotation[]
  fields: Field[]
  attachments: string[]
  file_size: number
  has_signatures: boolean
  source_path: string | null
}

export interface TextLine {
  rect: Rect
  text: string
  font: string
  size: number
  color: string
  bold: boolean
  italic: boolean
}

export interface TextBlock extends TextLine {
  line_count: number
}

export interface PageDetail {
  index: number
  lines: TextLine[]
  blocks: TextBlock[]
  images: { xref: number; rect: Rect }[]
  links: { index: number; rect: Rect; uri: string | null; page: number | null }[]
}

export interface SearchHit {
  page: number
  rect: Rect
  context: string
}

/** A pointer gesture on a page, already converted to PDF user space. */
export type Gesture =
  | { kind: 'click'; page: number; point: Point }
  | { kind: 'drag'; page: number; rect: Rect; start: Point; end: Point }
  | { kind: 'ink'; page: number; strokes: Point[][] }
  | { kind: 'poly'; page: number; points: Point[] }
  | { kind: 'text'; page: number; rects: Rect[]; text: string }
