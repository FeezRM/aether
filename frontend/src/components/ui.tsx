import type { ReactNode } from 'react'
import { opt, useEditor } from '../editor'

export function Section({ title, children }: { title?: string; children: ReactNode }) {
  return (
    <section className="panel-section">
      {title && <h4>{title}</h4>}
      {children}
    </section>
  )
}

/** A text/number/color/select/checkbox input bound to a tool option. */
export function OptInput(props: {
  k: string
  label: string
  type?: 'text' | 'number' | 'color' | 'select' | 'checkbox' | 'password' | 'textarea'
  def: string | number | boolean
  options?: string[] | [string, string][]
  placeholder?: string
}) {
  const ed = useEditor()
  const value = opt(ed, props.k, props.def)
  const set = (v: unknown) => ed.setOpt(props.k, v)
  const type = props.type ?? 'text'
  if (type === 'checkbox') {
    return (
      <label className="check">
        <input type="checkbox" checked={Boolean(value)} onChange={(e) => set(e.target.checked)} />
        {props.label}
      </label>
    )
  }
  return (
    <label className="field">
      <span>{props.label}</span>
      {type === 'select' ? (
        <select value={String(value)} onChange={(e) => set(e.target.value)}>
          {(props.options ?? []).map((o) => {
            const [v, l] = Array.isArray(o) ? o : [o, o]
            return <option key={v} value={v}>{l}</option>
          })}
        </select>
      ) : type === 'textarea' ? (
        <textarea value={String(value)} placeholder={props.placeholder} rows={3} onChange={(e) => set(e.target.value)} />
      ) : (
        <input
          type={type}
          value={String(value)}
          placeholder={props.placeholder}
          onChange={(e) => set(type === 'number' ? Number(e.target.value) : e.target.value)}
        />
      )}
    </label>
  )
}

export function ActionButton({ label, onClick, kind, disabled }: {
  label: string
  onClick: () => unknown
  kind?: 'primary' | 'danger'
  disabled?: boolean
}) {
  return (
    <button className={`action ${kind ?? ''}`} disabled={disabled} onClick={() => void onClick()}>
      {label}
    </button>
  )
}

/** Parse "1-3, 5" (1-based) into 0-based page indices. */
export function parsePages(spec: string, count: number): number[] | null {
  const out: number[] = []
  for (const part of spec.split(',').map((s) => s.trim()).filter(Boolean)) {
    const m = /^(\d*)\s*-\s*(\d*)$/.exec(part)
    const a = m ? Number(m[1] || 1) : Number(part)
    const b = m ? Number(m[2] || count) : Number(part)
    if (!Number.isInteger(a) || !Number.isInteger(b) || a < 1 || b > count || a > b) return null
    for (let i = a; i <= b; i++) out.push(i - 1)
  }
  return out.length ? [...new Set(out)] : null
}

/** Pages chosen in a "Pages" option: all, current, selected thumbnails, or a range. */
export function targetPages(ed: ReturnType<typeof useEditor>, key = 'pages'): number[] | undefined {
  const mode = opt(ed, `${key}.mode`, 'all')
  if (mode === 'all') return undefined
  if (mode === 'current') return [ed.page]
  if (mode === 'selected') return ed.selectedPages.length ? ed.selectedPages : [ed.page]
  const parsed = parsePages(opt(ed, `${key}.range`, ''), ed.info?.page_count ?? 0)
  if (!parsed) throw new Error('Invalid page range')
  return parsed
}

export function PagesOption({ k = 'pages' }: { k?: string }) {
  const ed = useEditor()
  return (
    <>
      <OptInput k={`${k}.mode`} label="Pages" type="select" def="all"
        options={[['all', 'All pages'], ['current', 'Current page'], ['selected', 'Selected thumbnails'], ['range', 'Range…']]} />
      {opt(ed, `${k}.mode`, 'all') === 'range' && <OptInput k={`${k}.range`} label="Range" def="" placeholder="e.g. 1-3, 7" />}
    </>
  )
}
