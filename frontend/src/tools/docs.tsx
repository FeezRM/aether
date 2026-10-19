import { useState } from 'react'
import { api, type AccessReport, type BatchResult, type CompareReport } from '../api'
import { opt, useEditor, type ToolGroup } from '../editor'
import type { Point } from '../types'
import { ActionButton, OptInput, PagesOption, Section, targetPages } from '../components/ui'

export const combineGroup: ToolGroup = {
  id: 'combine',
  label: 'Combine Files',
  icon: '🧩',
  description: 'Merge PDFs and images into one PDF',
  tools: [],
  Panel() {
    const ed = useEditor()
    const [chosen, setChosen] = useState<string[]>(ed.info ? [ed.info.id] : [])
    const [files, setFiles] = useState<File[]>([])
    const toggle = (id: string) => setChosen((c) => (c.includes(id) ? c.filter((x) => x !== id) : [...c, id]))
    return (
      <>
        <Section title="Open documents">
          {ed.docs.map((d) => (
            <label key={d.id} className="check">
              <input type="checkbox" checked={chosen.includes(d.id)} onChange={() => toggle(d.id)} /> {d.name}
            </label>
          ))}
        </Section>
        <Section title="Other files">
          <ActionButton label="Add files…" onClick={async () => setFiles([...files, ...(await ed.pickFile('.pdf,image/*', true))])} />
          {files.map((f, i) => (
            <div key={i} className="row between">
              <span className="ellipsis">{f.name}</span>
              <button className="small" onClick={() => setFiles(files.filter((_, j) => j !== i))}>×</button>
            </div>
          ))}
        </Section>
        <OptInput k="combine.bookmarks" label="Add a bookmark per file" type="checkbox" def={true} />
        <ActionButton label="Combine" kind="primary" disabled={chosen.length + files.length < 2} onClick={async () => {
          const info = await ed.withBusy('Combining', async () => {
            const blob_ids = await Promise.all(files.map((f) => api.blob(f)))
            return api.combine({ doc_ids: chosen, blob_ids, bookmarks: opt(ed, 'combine.bookmarks', true) })
          })
          if (info) {
            ed.openInfo(info)
            setFiles([])
          }
        }} />
      </>
    )
  },
}

export const createGroup: ToolGroup = {
  id: 'create',
  label: 'Create PDF',
  icon: '➕',
  description: 'Create a PDF from images, text, Markdown, HTML, EPUB or a blank page',
  tools: [],
  Panel() {
    const ed = useEditor()
    return (
      <>
        <Section title="From files">
          <p className="muted small">Images (PNG, JPEG, TIFF…), text, Markdown, HTML, EPUB, XPS, CBZ. Several files become one PDF.</p>
          <ActionButton label="Choose files…" kind="primary" onClick={async () => {
            const files = await ed.pickFile('image/*,.txt,.md,.markdown,.html,.htm,.epub,.xps,.cbz,.svg', true)
            if (!files.length) return
            const info = await ed.withBusy('Creating PDF', async () => api.create(await Promise.all(files.map((f) => api.blob(f)))))
            if (info) ed.openInfo(info)
          }} />
        </Section>
        <Section title="Blank document">
          <OptInput k="blank.pages" label="Pages" type="number" def={1} />
          <OptInput k="blank.size" label="Size" type="select" def="letter" options={['letter', 'legal', 'a4', 'a3', 'a5']} />
          <ActionButton label="Create blank PDF" onClick={async () => {
            const info = await ed.withBusy('Creating', () => api.blank(Number(opt(ed, 'blank.pages', 1)), opt(ed, 'blank.size', 'letter')))
            if (info) ed.openInfo(info)
          }} />
        </Section>
      </>
    )
  },
}

const EXPORTS: [string, string][] = [
  ['docx', 'Microsoft Word (.docx)'], ['xlsx', 'Microsoft Excel (.xlsx)'], ['pptx', 'Microsoft PowerPoint (.pptx)'],
  ['png', 'Images (PNG, zipped)'], ['jpg', 'Images (JPEG, zipped)'], ['txt', 'Plain text'], ['md', 'Markdown'], ['html', 'HTML'],
]

export const exportGroup: ToolGroup = {
  id: 'export',
  label: 'Export PDF',
  icon: '📤',
  description: 'Convert to Word, Excel, PowerPoint, images, text and more',
  needsDoc: true,
  tools: [],
  Panel() {
    const ed = useEditor()
    return (
      <Section title="Convert to">
        {EXPORTS.map(([kind, label]) => (
          <ActionButton key={kind} label={label} onClick={() => ed.withBusy(`Exporting ${kind}`, () => api.exportAs(ed.info!.id, kind))} />
        ))}
      </Section>
    )
  },
}

export const ocrGroup: ToolGroup = {
  id: 'ocr',
  label: 'Scan & OCR',
  icon: '🔍',
  description: 'Make scanned pages searchable and selectable',
  needsDoc: true,
  tools: [],
  Panel() {
    const ed = useEditor()
    return (
      <Section title="Recognize text">
        <PagesOption k="ocr" />
        <OptInput k="ocr.lang" label="Language" type="select" def="eng" options={[['eng', 'English'], ['osd', 'Script detection']]} />
        <OptInput k="ocr.dpi" label="Resolution (dpi)" type="number" def={300} />
        <OptInput k="ocr.force" label="Also re-OCR pages that already have text" type="checkbox" def={false} />
        <ActionButton label="Recognize text" kind="primary" onClick={async () => {
          const r = await ed.runOp<{ ocr_pages: number[]; skipped_pages: number[]; words: number }>('ocr_pages', {
            pages: targetPages(ed, 'ocr'), language: opt(ed, 'ocr.lang', 'eng'), dpi: Number(opt(ed, 'ocr.dpi', 300)),
            force: opt(ed, 'ocr.force', false),
          })
          if (r) ed.notify(`Recognized ${r.words} words on ${r.ocr_pages.length} page(s); skipped ${r.skipped_pages.length} page(s) with text.`, 'success')
        }} />
        <p className="muted small">OCR runs locally with Tesseract. More languages: brew install tesseract-lang.</p>
      </Section>
    )
  },
}

export const compareGroup: ToolGroup = {
  id: 'compare',
  label: 'Compare Files',
  icon: '🆚',
  description: 'Highlight differences between two versions',
  tools: [],
  Panel() {
    const ed = useEditor()
    const [oldId, setOld] = useState('')
    const [newId, setNew] = useState(ed.info?.id ?? '')
    const [report, setReport] = useState<CompareReport | null>(null)
    const pick = (label: string, value: string, set: (v: string) => void) => (
      <label className="field">
        <span>{label}</span>
        <select value={value} onChange={(e) => set(e.target.value)}>
          <option value="">Choose…</option>
          {ed.docs.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
        </select>
      </label>
    )
    return (
      <>
        <Section title="Documents">
          <p className="muted small">Open both versions first (they appear as tabs).</p>
          {pick('Old version', oldId, setOld)}
          {pick('New version', newId, setNew)}
          <ActionButton label="Compare" kind="primary" disabled={!oldId || !newId || oldId === newId} onClick={async () => {
            const r = await ed.withBusy('Comparing', () => api.compare(oldId, newId))
            if (r) {
              setReport(r.report)
              ed.openInfo(r.info)
            }
          }} />
        </Section>
        {report && (
          <Section title={`Result: ${report.similarity}% similar`}>
            <p className="small">{report.counts.inserted} inserted · {report.counts.deleted} deleted · {report.counts.replaced} replaced</p>
            <div className="list">
              {report.changes.map((c, i) => (
                <div key={i} className="list-item change" onClick={() => ed.goTo(c.page)}>
                  <span className={`badge ${c.type}`}>{c.type}</span>
                  <span className="small">p{c.page + 1}: {c.type === 'deleted' ? c.old : c.new}</span>
                </div>
              ))}
            </div>
          </Section>
        )}
      </>
    )
  },
}

export const optimizeGroup: ToolGroup = {
  id: 'optimize',
  label: 'Compress PDF',
  icon: '🗜️',
  description: 'Reduce file size: downsample images, subset fonts, clean up',
  needsDoc: true,
  tools: [],
  Panel() {
    const ed = useEditor()
    return (
      <Section title="Optimize">
        <OptInput k="opt.level" label="Compression" type="select" def="medium"
          options={[['low', 'Low (best quality)'], ['medium', 'Medium'], ['high', 'High (smallest file)']]} />
        <OptInput k="opt.fonts" label="Subset fonts" type="checkbox" def={true} />
        <OptInput k="opt.meta" label="Remove metadata" type="checkbox" def={false} />
        <p className="small">Current size: {((ed.info?.file_size ?? 0) / 1024).toFixed(1)} KB</p>
        <ActionButton label="Compress" kind="primary" onClick={async () => {
          const r = await ed.runOp<{ before: number; after: number; saved_percent: number }>('optimize', {
            level: opt(ed, 'opt.level', 'medium'), subset_fonts: opt(ed, 'opt.fonts', true), remove_metadata: opt(ed, 'opt.meta', false),
          })
          if (r) ed.notify(r.saved_percent > 0 ? `Saved ${r.saved_percent}% (${(r.before / 1024).toFixed(0)} → ${(r.after / 1024).toFixed(0)} KB)` : 'Already optimal; nothing to save.', 'success')
        }} />
      </Section>
    )
  },
}

export const accessibilityGroup: ToolGroup = {
  id: 'accessibility',
  label: 'Accessibility',
  icon: '♿',
  description: 'Check documents against accessibility rules',
  needsDoc: true,
  tools: [],
  Panel() {
    const ed = useEditor()
    const [rep, setRep] = useState<AccessReport | null>(null)
    return (
      <Section title="Accessibility check">
        <ActionButton label="Run full check" kind="primary" onClick={async () => {
          const r = await ed.withBusy('Checking', () => api.accessibility(ed.info!.id))
          if (r) setRep(r)
        }} />
        {rep && (
          <>
            <p className="small">{rep.passed} passed · {rep.failed} failed · {rep.manual} need manual check</p>
            {rep.checks.map((c) => (
              <div key={c.rule} className={`check-row ${c.status}`}>
                <span>{c.status === 'passed' ? '✅' : c.status === 'failed' ? '❌' : '👁️'} {c.rule}</span>
                <span className="muted small">{c.detail}</span>
              </div>
            ))}
            <p className="muted small">Fix title and language under Properties, scanned pages with Scan &amp; OCR, field tooltips in Prepare Form.</p>
          </>
        )}
      </Section>
    )
  },
}

const RECIPES: Record<string, { label: string; steps: { op: string; params: object }[] }> = {
  publish: { label: 'Prepare for distribution (sanitize + compress)', steps: [
    { op: 'sanitize', params: {} }, { op: 'optimize', params: { level: 'medium' } }] },
  confidential: { label: 'Mark confidential (watermark + page numbers)', steps: [
    { op: 'add_watermark', params: { text: 'CONFIDENTIAL' } },
    { op: 'header_footer', params: { footer_center: 'Page <<page>> of <<pages>>' } }] },
  ocr: { label: 'Make scans searchable (OCR + compress)', steps: [
    { op: 'ocr_pages', params: {} }, { op: 'optimize', params: { level: 'low' } }] },
  flatten: { label: 'Finalize (flatten comments and forms)', steps: [
    { op: 'flatten_annotations', params: { include_forms: true } }] },
  bookmarks: { label: 'Add bookmarks from headings', steps: [{ op: 'auto_bookmarks', params: {} }] },
}

export const actionsGroup: ToolGroup = {
  id: 'actions',
  label: 'Action Wizard',
  icon: '⚙️',
  description: 'Run a sequence of steps on several open documents',
  tools: [],
  Panel() {
    const ed = useEditor()
    const [chosen, setChosen] = useState<string[]>(ed.docs.map((d) => d.id))
    const [results, setResults] = useState<BatchResult[] | null>(null)
    return (
      <>
        <Section title="Action">
          <OptInput k="act.recipe" label="Action" type="select" def="publish"
            options={Object.entries(RECIPES).map(([k, r]): [string, string] => [k, r.label])} />
          <ol className="small">{RECIPES[opt(ed, 'act.recipe', 'publish')].steps.map((s, i) => <li key={i}>{s.op}</li>)}</ol>
        </Section>
        <Section title="Documents">
          {ed.docs.map((d) => (
            <label key={d.id} className="check">
              <input type="checkbox" checked={chosen.includes(d.id)}
                onChange={() => setChosen((c) => (c.includes(d.id) ? c.filter((x) => x !== d.id) : [...c, d.id]))} /> {d.name}
            </label>
          ))}
        </Section>
        <ActionButton label="Run action" kind="primary" disabled={!chosen.length} onClick={async () => {
          const r = await ed.withBusy('Running action', () => api.batch(chosen, RECIPES[opt(ed, 'act.recipe', 'publish')].steps))
          if (!r) return
          setResults(r)
          if (ed.info) ed.setInfo(await api.info(ed.info.id))
        }} />
        {results?.map((r) => <div key={r.id} className="small">{r.ok ? '✅' : '❌'} {r.name}{r.error ? `: ${r.error}` : ''}</div>)}
      </>
    )
  },
}

const UNITS: Record<string, number> = { in: 72, cm: 72 / 2.54, mm: 72 / 25.4, pt: 1 }

export const measureGroup: ToolGroup = {
  id: 'measure',
  label: 'Measure',
  icon: '📏',
  description: 'Measure distance, perimeter and area',
  needsDoc: true,
  tools: [
    {
      id: 'measure-distance', label: 'Distance', gesture: 'drag', hint: 'Drag from one point to another',
      async onGesture(g, ed) {
        if (g.kind !== 'drag') return
        const unit = opt(ed, 'measure.unit', 'in'), scale = Number(opt(ed, 'measure.scale', 1))
        const d = Math.hypot(g.end[0] - g.start[0], g.end[1] - g.start[1]) / UNITS[unit] * scale
        const label = `${d.toFixed(2)} ${unit}`
        await ed.runOp('add_shape', { page: g.page, kind: 'arrow', points: [g.start, g.end], color: '#c2185b', width: 1, contents: `Distance: ${label}` })
        ed.notify(`Distance: ${label}`, 'success')
      },
    },
    {
      id: 'measure-area', label: 'Perimeter & area', gesture: 'poly', hint: 'Click the corners, double-click to finish',
      async onGesture(g, ed) {
        if (g.kind !== 'poly') return
        const unit = opt(ed, 'measure.unit', 'in'), scale = Number(opt(ed, 'measure.scale', 1)), u = UNITS[unit]
        const pts: Point[] = g.points
        let per = 0, area = 0
        pts.forEach((p, i) => {
          const q = pts[(i + 1) % pts.length]
          per += Math.hypot(q[0] - p[0], q[1] - p[1])
          area += p[0] * q[1] - q[0] * p[1]
        })
        const label = `Perimeter ${(per / u * scale).toFixed(2)} ${unit}, area ${(Math.abs(area) / 2 / u / u * scale * scale).toFixed(2)} sq ${unit}`
        await ed.runOp('add_shape', { page: g.page, kind: 'polygon', points: pts, color: '#c2185b', width: 1, contents: label })
        ed.notify(label, 'success')
      },
    },
  ],
  Panel() {
    return (
      <Section title="Scale">
        <OptInput k="measure.unit" label="Unit" type="select" def="in" options={Object.keys(UNITS)} />
        <OptInput k="measure.scale" label="Scale (1 page unit = N real units)" type="number" def={1} />
        <p className="muted small">Each measurement is kept as a comment with its value.</p>
      </Section>
    )
  },
}

export const organizeGroup: ToolGroup = {
  id: 'organize',
  label: 'Organize Pages',
  icon: '🗂️',
  description: 'Reorder, rotate, delete, insert, extract, split and replace pages',
  needsDoc: true,
  tools: [],
  Panel() {
    const ed = useEditor()
    const sel = ed.selectedPages.length ? ed.selectedPages : [ed.page]
    const id = ed.info!.id
    const insertFile = async (at: number) => {
      const [file] = await ed.pickFile('.pdf,image/*')
      if (file) await ed.runOp('insert_pdf', { blob_id: await api.blob(file), at })
    }
    return (
      <>
        <Section title={`Selection: ${sel.map((p) => p + 1).join(', ')}`}>
          <p className="muted small">Click thumbnails to select (Shift/⌘ for many). Drag to reorder.</p>
          <div className="btn-grid">
            <button onClick={() => ed.runOp('rotate_pages', { angle: -90, pages: sel })}>⟲ Rotate left</button>
            <button onClick={() => ed.runOp('rotate_pages', { angle: 90, pages: sel })}>⟳ Rotate right</button>
            <button onClick={() => ed.runOp('duplicate_pages', { pages: sel })}>Duplicate</button>
            <button className="danger" onClick={async () => {
              if (await ed.runOp('delete_pages', { pages: sel }) !== null) ed.setSelectedPages([])
            }}>Delete</button>
            <button onClick={() => api.extract(id, sel, false)}>Extract (download)</button>
            <button onClick={async () => {
              const info = await api.extract(id, sel, true)
              if (info) ed.openInfo(info)
            }}>Extract (open)</button>
            <button onClick={() => ed.runOp('insert_blank', { at: Math.max(...sel) + 1 })}>Insert blank after</button>
            <button onClick={() => insertFile(Math.max(...sel) + 1)}>Insert file after…</button>
            <button onClick={async () => {
              const [file] = await ed.pickFile('.pdf')
              if (file) await ed.runOp('replace_pages', { start: Math.min(...sel), blob_id: await api.blob(file) })
            }}>Replace from file…</button>
          </div>
        </Section>
        <Section title="Split document">
          <OptInput k="split.mode" label="Split by" type="select" def="every"
            options={[['every', 'Number of pages'], ['ranges', 'Page ranges'], ['bookmarks', 'Top-level bookmarks'], ['size', 'File size']]} />
          {opt(ed, 'split.mode', 'every') === 'every' && <OptInput k="split.every" label="Pages per file" type="number" def={1} />}
          {opt(ed, 'split.mode', 'every') === 'ranges' && <OptInput k="split.ranges" label="Ranges" def="1-2, 3-" />}
          {opt(ed, 'split.mode', 'every') === 'size' && <OptInput k="split.mb" label="Max MB per file" type="number" def={5} />}
          <ActionButton label="Split (download zip)" onClick={() => ed.withBusy('Splitting', () => api.split(id, {
            mode: opt(ed, 'split.mode', 'every'), every: Number(opt(ed, 'split.every', 1)),
            ranges: opt(ed, 'split.ranges', '1-2, 3-'), max_mb: Number(opt(ed, 'split.mb', 5)),
          }))} />
        </Section>
        <Section title="Crop">
          <PagesOption k="crop" />
          <OptInput k="crop.margin" label="Trim margins (pt, all sides)" type="number" def={36} />
          <ActionButton label="Trim margins" onClick={() => {
            const m = Number(opt(ed, 'crop.margin', 36))
            return ed.runOp('crop_pages', { pages: targetPages(ed, 'crop'), margins: [m, m, m, m] })
          }} />
        </Section>
      </>
    )
  },
}
