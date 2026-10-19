import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import { opt, today, useEditor, type Editor, type ToolGroup, type ToolLayerProps } from '../editor'
import { toViewBox } from '../pdf'
import type { Field, Gesture } from '../types'
import { ActionButton, OptInput, Section } from '../components/ui'

const FIELD_TYPES = ['text', 'checkbox', 'radio', 'combobox', 'listbox', 'signature', 'button']

/** Live form-filling inputs positioned over each field. */
function FillLayer({ page, viewport }: ToolLayerProps) {
  const ed = useEditor()
  const fields = ed.info?.fields.filter((f) => f.page === page) ?? []
  const set = (f: Field, value: string | boolean) => ed.runOp('fill_fields', { values: { [f.name]: value } })
  return (
    <div className="tool-layer">
      {fields.map((f) => {
        const box = toViewBox(viewport, f.rect)
        const style = { ...box, fontSize: Math.max(10, Math.min(box.height * 0.6, 16)) }
        const key = `${f.xref}-${ed.info?.version}`
        if (f.readonly) return <div key={key} className="field-box readonly" style={box} title={`${f.name} (read-only)`} />
        if (f.type === 'checkbox' || f.type === 'radio') {
          const on = f.value === f.on_state || f.value === true
          return (
            <input key={key} type="checkbox" className="field-input check" style={box} checked={on} title={f.tooltip || f.name}
              onChange={(e) => set(f, f.type === 'radio' ? (e.target.checked ? f.on_state ?? true : 'Off') : e.target.checked)} />
          )
        }
        if (f.type === 'combobox' || f.type === 'listbox') {
          return (
            <select key={key} className="field-input" style={style} defaultValue={String(f.value ?? '')} title={f.tooltip || f.name}
              onChange={(e) => set(f, e.target.value)}>
              {f.options.map((o) => <option key={o}>{o}</option>)}
            </select>
          )
        }
        if (f.type === 'text') {
          const Tag = f.multiline ? 'textarea' : 'input'
          return (
            <Tag key={key} className={`field-input ${f.required ? 'required' : ''}`} style={style}
              defaultValue={String(f.value ?? '')} title={f.tooltip || f.name} placeholder={f.required ? 'Required' : ''}
              onBlur={(e: React.FocusEvent<HTMLInputElement | HTMLTextAreaElement>) => {
                if (e.target.value !== String(f.value ?? '')) void set(f, e.target.value)
              }} />
          )
        }
        return <div key={key} className="field-box" style={box} title={`${f.type}: ${f.name}`} />
      })}
    </div>
  )
}

/** Field outlines while preparing a form; click to edit or delete. */
function PrepareLayer({ page, viewport }: ToolLayerProps) {
  const ed = useEditor()
  const fields = ed.info?.fields.filter((f) => f.page === page) ?? []
  return (
    <div className="tool-layer passthrough">
      {fields.map((f) => (
        <div key={`${f.xref}-${f.name}`} className="field-box prepare" style={toViewBox(viewport, f.rect)}
          onClick={async (e) => {
            e.stopPropagation()
            const v = await ed.prompt(`Field: ${f.name}`, [
              { name: 'name', label: 'Name', value: f.name },
              { name: 'tooltip', label: 'Tooltip', value: f.tooltip },
              { name: 'required', label: 'Required', type: 'checkbox', value: f.required },
              { name: 'readonly', label: 'Read-only', type: 'checkbox', value: f.readonly },
              { name: 'delete', label: 'Delete this field', type: 'checkbox', value: false },
            ], 'Apply')
            if (!v) return
            if (v.delete === 'true') return void ed.runOp('delete_field', { name: f.name })
            await ed.runOp('update_field', {
              name: f.name, new_name: v.name !== f.name ? v.name : undefined, tooltip: v.tooltip,
              required: v.required === 'true', readonly: v.readonly === 'true',
            })
          }}>
          <span className="field-tag">{f.type}: {f.name}</span>
        </div>
      ))}
    </div>
  )
}

export const formsGroup: ToolGroup = {
  id: 'forms',
  label: 'Prepare Form',
  icon: '📝',
  description: 'Create fillable forms: add, detect and edit fields',
  needsDoc: true,
  tools: [
    {
      id: 'add-field', label: 'Add field', gesture: 'drag', hint: 'Pick a field type, then drag its box', Layer: PrepareLayer,
      async onGesture(g, ed) {
        if (g.kind !== 'drag') return
        const type = opt(ed, 'field.type', 'text')
        const needsOptions = type === 'combobox' || type === 'listbox'
        const fields = [
          { name: 'name', label: 'Field name', value: `${type}_${(ed.info?.fields.length ?? 0) + 1}` },
          { name: 'tooltip', label: 'Tooltip (for accessibility)' },
          ...(needsOptions ? [{ name: 'options', label: 'Options (comma separated)', placeholder: 'Yes, No' }] : []),
          ...(type === 'text' ? [{ name: 'multiline', label: 'Multi-line', type: 'checkbox' as const, value: false }] : []),
          { name: 'required', label: 'Required', type: 'checkbox' as const, value: false },
        ]
        const v = await ed.prompt(`New ${type} field`, fields)
        if (!v?.name) return
        await ed.runOp('add_field', {
          page: g.page, rect: g.rect, type, name: v.name, tooltip: v.tooltip ?? '',
          options: needsOptions ? (v.options ?? '').split(',').map((s) => s.trim()).filter(Boolean) : undefined,
          multiline: v.multiline === 'true', required: v.required === 'true',
        })
      },
    },
    { id: 'edit-fields', label: 'Edit fields', gesture: 'none', hint: 'Click a field to rename, flag or delete it', Layer: PrepareLayer },
    { id: 'fill', label: 'Fill form', gesture: 'none', hint: 'Type into the fields', Layer: FillLayer },
  ],
  Panel() {
    const ed = useEditor()
    const id = ed.info?.id
    return (
      <>
        <Section title="New field type">
          <OptInput k="field.type" label="Type" type="select" def="text" options={FIELD_TYPES} />
        </Section>
        <Section title="Form actions">
          <ActionButton label="Auto-detect form fields" kind="primary" onClick={async () => {
            const r = await ed.runOp<{ added: unknown[] }>('detect_fields', {})
            if (r) ed.notify(`Added ${r.added.length} field(s)`, 'success')
          }} />
          <ActionButton label="Clear form" onClick={() => ed.runOp('clear_form', {})} />
          <ActionButton label="Import data (JSON)…" onClick={async () => {
            const [file] = await ed.pickFile('application/json,.json')
            if (!file) return
            try {
              await ed.runOp('fill_fields', { values: JSON.parse(await file.text()) })
            } catch (e) {
              ed.notify(`Invalid JSON: ${(e as Error).message}`, 'error')
            }
          }} />
          <ActionButton label="Export data (JSON)" onClick={() => id && api.formData(id, 'json')} />
          <ActionButton label="Export data (CSV)" onClick={() => id && api.formData(id, 'csv')} />
        </Section>
        <Section title={`Fields (${ed.info?.fields.length ?? 0})`}>
          <div className="list">
            {ed.info?.fields.map((f) => (
              <div key={`${f.xref}-${f.name}`} className="list-item" onClick={() => ed.goTo(f.page)}>
                <span>{f.name}</span>
                <span className="muted small">{f.type} · p{f.page + 1}{f.required ? ' · required' : ''}</span>
              </div>
            ))}
          </div>
        </Section>
      </>
    )
  },
}

// --- Fill & Sign -----------------------------------------------------------

export function SignaturePad({ onDone }: { onDone: (strokes: [number, number][][], box: [number, number]) => void }) {
  const ed = useEditor()
  const ref = useRef<HTMLCanvasElement>(null)
  const [strokes, setStrokes] = useState<[number, number][][]>([])
  const down = useRef(false)
  useEffect(() => {
    const c = ref.current!
    const ctx = c.getContext('2d')!
    ctx.clearRect(0, 0, c.width, c.height)
    ctx.strokeStyle = '#0b1f66'
    ctx.lineWidth = 2.2
    ctx.lineCap = 'round'
    ctx.lineJoin = 'round'
    for (const s of strokes) {
      ctx.beginPath()
      s.forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)))
      ctx.stroke()
    }
  }, [strokes])
  const pos = (e: React.PointerEvent): [number, number] => {
    const r = ref.current!.getBoundingClientRect()
    return [e.clientX - r.left, e.clientY - r.top]
  }
  return (
    <div className="sigpad">
      <h3>Draw your signature</h3>
      <canvas ref={ref} width={460} height={160}
        onPointerDown={(e) => { down.current = true; ref.current!.setPointerCapture(e.pointerId); setStrokes((s) => [...s, [pos(e)]]) }}
        onPointerMove={(e) => {
          if (!down.current) return
          const p = pos(e)
          setStrokes((s) => { const c = s.slice(); c[c.length - 1] = [...c[c.length - 1], p]; return c })
        }}
        onPointerUp={() => { down.current = false }} />
      <div className="row">
        <button onClick={() => setStrokes([])}>Clear</button>
        <button onClick={() => ed.closeModal()}>Cancel</button>
        <button className="primary" disabled={!strokes.length} onClick={() => { onDone(strokes, [460, 160]); ed.closeModal() }}>Use signature</button>
      </div>
    </div>
  )
}

export const fillSignGroup: ToolGroup = {
  id: 'fillsign',
  label: 'Fill & Sign',
  icon: '✍️',
  description: 'Fill in any form, add your signature, initials, marks and dates',
  needsDoc: true,
  tools: [
    { id: 'fs-fields', label: 'Fill form fields', gesture: 'none', hint: 'Type into the fields', Layer: FillLayer },
    {
      id: 'fs-text', label: 'Add text', gesture: 'click', cursor: 'text', hint: 'Click where the text goes',
      async onGesture(g, ed) {
        if (g.kind !== 'click') return
        const v = await ed.prompt('Text', [{ name: 'text', label: 'Text' }])
        if (v?.text) await ed.runOp('add_text_point', { page: g.page, point: g.point, text: v.text, fontsize: opt(ed, 'fs.size', 11) })
      },
    },
    {
      id: 'fs-date', label: 'Add date', gesture: 'click', cursor: 'text', hint: "Click to place today's date",
      onGesture: (g, ed) => g.kind === 'click' ? void ed.runOp('add_text_point', { page: g.page, point: g.point, text: today(), fontsize: opt(ed, 'fs.size', 11) }) : undefined,
    },
    ...(['check', 'cross', 'dot', 'circle', 'line'] as const).map((mark) => ({
      id: `fs-${mark}`, label: { check: 'Checkmark', cross: 'Cross', dot: 'Dot', circle: 'Circle', line: 'Line' }[mark],
      gesture: 'click' as const, cursor: 'copy',
      onGesture: (g: Gesture, ed: Editor) =>
        g.kind === 'click' ? void ed.runOp('place_mark', { page: g.page, point: g.point, mark, size: opt(ed, 'fs.size', 11) }) : undefined,
    })),
    {
      id: 'fs-sign', label: 'Place signature', gesture: 'drag', hint: 'Create a signature in the panel, then drag where it goes',
      async onGesture(g, ed) {
        if (g.kind !== 'drag') return
        const sig = ed.opts['fs.signature'] as { strokes?: unknown; box?: unknown; text?: string; blob?: string } | undefined
        if (!sig) return ed.notify('Create a signature first (panel on the right)', 'error')
        await ed.runOp('add_signature', {
          page: g.page, rect: g.rect,
          ...(sig.strokes ? { strokes: sig.strokes, stroke_box: sig.box } : sig.text ? { text: sig.text } : { blob_id: sig.blob }),
        })
      },
    },
  ],
  Panel() {
    const ed = useEditor()
    const sig = ed.opts['fs.signature'] as { label: string } | undefined
    const store = (value: object, label: string) => {
      ed.setOpt('fs.signature', { ...value, label })
      ed.setTool('fs-sign')
    }
    return (
      <>
        <Section title="Your signature">
          <p className="muted small">{sig ? `Ready: ${sig.label}. Drag on the page to place it.` : 'No signature yet.'}</p>
          <ActionButton label="Draw signature" kind="primary" onClick={() => ed.openModal(
            <SignaturePad onDone={(strokes, box) => store({ strokes, box }, 'drawn signature')} />,
          )} />
          <ActionButton label="Type signature" onClick={async () => {
            const v = await ed.prompt('Type your name', [{ name: 'text', label: 'Name' }])
            if (v?.text) store({ text: v.text }, `typed "${v.text}"`)
          }} />
          <ActionButton label="Use image…" onClick={async () => {
            const [file] = await ed.pickFile('image/*')
            if (file) store({ blob: await api.blob(file) }, file.name)
          }} />
        </Section>
        <Section title="Options">
          <OptInput k="fs.size" label="Text / mark size" type="number" def={11} />
        </Section>
      </>
    )
  },
}
