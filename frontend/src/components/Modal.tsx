import { useState } from 'react'
import type { PromptField } from '../editor'

export interface PromptState {
  title: string
  fields: PromptField[]
  ok: string
  resolve: (v: Record<string, string> | null) => void
}

export function PromptDialog({ state, onClose }: { state: PromptState; onClose: () => void }) {
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(state.fields.map((f) => [f.name, String(f.value ?? (f.type === 'select' ? f.options?.[0] ?? '' : ''))])),
  )
  const done = (v: Record<string, string> | null) => {
    state.resolve(v)
    onClose()
  }
  return (
    <div className="modal-backdrop" onMouseDown={() => done(null)}>
      <form className="modal" onMouseDown={(e) => e.stopPropagation()}
        onSubmit={(e) => { e.preventDefault(); done(values) }}>
        <h3>{state.title}</h3>
        {state.fields.map((f, i) => {
          const set = (v: string) => setValues((s) => ({ ...s, [f.name]: v }))
          if (f.type === 'checkbox') {
            return (
              <label key={f.name} className="check">
                <input type="checkbox" checked={values[f.name] === 'true'} onChange={(e) => set(String(e.target.checked))} />
                {f.label}
              </label>
            )
          }
          return (
            <label key={f.name} className="field">
              <span>{f.label}</span>
              {f.type === 'textarea' ? (
                <textarea autoFocus={i === 0} rows={4} value={values[f.name]} placeholder={f.placeholder}
                  onChange={(e) => set(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) done(values) }} />
              ) : f.type === 'select' ? (
                <select value={values[f.name]} onChange={(e) => set(e.target.value)}>
                  {f.options?.map((o) => <option key={o}>{o}</option>)}
                </select>
              ) : (
                <input autoFocus={i === 0} type={f.type ?? 'text'} value={values[f.name]} placeholder={f.placeholder}
                  onChange={(e) => set(e.target.value)} />
              )}
            </label>
          )
        })}
        <div className="row end">
          <button type="button" onClick={() => done(null)}>Cancel</button>
          <button type="submit" className="primary">{state.ok}</button>
        </div>
      </form>
    </div>
  )
}

export function Modal({ children, onClose }: { children: React.ReactNode; onClose: () => void }) {
  return (
    <div className="modal-backdrop" onMouseDown={onClose}>
      <div className="modal" onMouseDown={(e) => e.stopPropagation()}>{children}</div>
    </div>
  )
}
