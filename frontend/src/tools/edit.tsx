import { useEffect, useState } from 'react'
import { api } from '../api'
import { opt, useEditor, type Editor, type ToolGroup, type ToolLayerProps } from '../editor'
import { toViewBox } from '../pdf'
import type { PageDetail, TextBlock } from '../types'
import { ActionButton, OptInput, PagesOption, Section, targetPages } from '../components/ui'

function EditTextLayer({ page, viewport }: ToolLayerProps) {
  const ed = useEditor()
  const [detail, setDetail] = useState<PageDetail | null>(null)
  const [editing, setEditing] = useState<{ block: TextBlock; text: string } | null>(null)
  const { pageDetail } = ed

  useEffect(() => {
    let live = true
    pageDetail(page).then((d) => live && setDetail(d)).catch(() => {})
    return () => {
      live = false
    }
  }, [pageDetail, page])

  const commit = async () => {
    if (!editing) return
    const { block, text } = editing
    setEditing(null)
    if (text === block.text) return
    await ed.runOp('edit_text', { page, rect: block.rect, text })
  }

  return (
    <div className="tool-layer">
      {detail?.blocks.map((block, i) => {
        const box = toViewBox(viewport, block.rect)
        const active = editing?.block === block
        return active ? (
          <textarea
            key={i}
            autoFocus
            onFocus={(e) => e.target.setSelectionRange(e.target.value.length, e.target.value.length)}
            className="inline-editor"
            style={{ ...box, width: Math.max(box.width + 24, 80), height: box.height + block.size * ed.zoom * 1.4,
              fontSize: block.size * ed.zoom * 0.95, color: block.color,
              fontWeight: block.bold ? 700 : 400, fontStyle: block.italic ? 'italic' : 'normal' }}
            value={editing.text}
            onChange={(e) => setEditing({ block, text: e.target.value })}
            onBlur={commit}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                void commit()
              }
              if (e.key === 'Escape') setEditing(null)
            }}
          />
        ) : (
          <div key={i} className="text-line" style={box} title="Click to edit this paragraph"
            onClick={(e) => {
              e.stopPropagation()
              setEditing({ block, text: block.text })
            }} />
        )
      })}
    </div>
  )
}

function ImageLayer({ page, viewport }: ToolLayerProps) {
  const ed = useEditor()
  const [detail, setDetail] = useState<PageDetail | null>(null)
  const { pageDetail } = ed
  useEffect(() => {
    pageDetail(page).then(setDetail).catch(() => {})
  }, [pageDetail, page])
  return (
    <div className="tool-layer">
      {detail?.images.map((im) => (
        <div key={im.xref + ':' + im.rect.join()} className="image-box" style={toViewBox(viewport, im.rect)}>
          <button onClick={async () => {
            const [file] = await ed.pickFile('image/*')
            if (file) await ed.runOp('replace_image', { page, xref: im.xref, blob_id: await api.blob(file) })
          }}>Replace</button>
          <button className="danger" onClick={() => ed.runOp('delete_area_content', { page, rect: im.rect, images: true, graphics: false })}>
            Delete
          </button>
        </div>
      ))}
    </div>
  )
}

function textOpts(ed: Editor) {
  return {
    fontsize: opt(ed, 'edit.size', 12), family: opt(ed, 'edit.family', 'sans'),
    bold: opt(ed, 'edit.bold', false), italic: opt(ed, 'edit.italic', false),
    color: opt(ed, 'edit.color', '#000000'), align: opt(ed, 'edit.align', 'left'),
  }
}

export const editGroup: ToolGroup = {
  id: 'edit',
  label: 'Edit PDF',
  icon: '✏️',
  description: 'Edit text and images, add text, images and links, crop pages',
  needsDoc: true,
  tools: [
    { id: 'edit-text', label: 'Edit text', gesture: 'none', hint: 'Click a paragraph to edit it; Enter saves, Shift+Enter adds a line break, Esc cancels', Layer: EditTextLayer },
    {
      id: 'add-text', label: 'Add text', gesture: 'drag', hint: 'Drag a box where the new text goes',
      async onGesture(g, ed) {
        if (g.kind !== 'drag') return
        const v = await ed.prompt('Add text', [{ name: 'text', label: 'Text', type: 'textarea' }])
        if (v?.text) await ed.runOp('add_text', { page: g.page, rect: g.rect, text: v.text, ...textOpts(ed) })
      },
    },
    { id: 'edit-image', label: 'Edit images', gesture: 'none', hint: 'Replace or delete images on the page', Layer: ImageLayer },
    {
      id: 'add-image', label: 'Add image', gesture: 'drag', hint: 'Drag where the image goes; you will pick a file',
      async onGesture(g, ed) {
        if (g.kind !== 'drag') return
        const [file] = await ed.pickFile('image/*')
        if (file) await ed.runOp('add_image', { page: g.page, rect: g.rect, blob_id: await api.blob(file) })
      },
    },
    {
      id: 'link', label: 'Link', gesture: 'drag', hint: 'Drag over the link area',
      async onGesture(g, ed) {
        if (g.kind !== 'drag') return
        const v = await ed.prompt('Add link', [
          { name: 'kind', label: 'Link to', type: 'select', options: ['Web address', 'Page in this document'] },
          { name: 'target', label: 'URL or page number', placeholder: 'https://… or 3' },
        ])
        if (!v?.target) return
        const params = v.kind === 'Web address' ? { uri: v.target } : { target_page: Number(v.target) - 1 }
        await ed.runOp('add_link', { page: g.page, rect: g.rect, ...params })
      },
    },
    {
      id: 'crop', label: 'Crop pages', gesture: 'drag', hint: 'Drag the area to keep',
      async onGesture(g, ed) {
        if (g.kind !== 'drag') return
        const pages = opt(ed, 'crop.all', false) ? undefined : [g.page]
        await ed.runOp('crop_pages', { pages, rect: g.rect })
      },
    },
    {
      id: 'whiteout', label: 'Delete content in area', gesture: 'drag', hint: 'Drag over images or drawings to remove them',
      async onGesture(g, ed) {
        if (g.kind !== 'drag') return
        await ed.runOp('delete_area_content', { page: g.page, rect: g.rect, images: true, graphics: true, text: opt(ed, 'edit.removeText', false) })
      },
    },
  ],
  Panel() {
    const ed = useEditor()
    const id = ed.info?.id
    return (
      <>
        <Section title="Text format (new text)">
          <OptInput k="edit.family" label="Font" type="select" def="sans" options={[['sans', 'Helvetica'], ['serif', 'Times'], ['mono', 'Courier']]} />
          <OptInput k="edit.size" label="Size" type="number" def={12} />
          <OptInput k="edit.color" label="Color" type="color" def="#000000" />
          <OptInput k="edit.align" label="Align" type="select" def="left" options={['left', 'center', 'right', 'justify']} />
          <OptInput k="edit.bold" label="Bold" type="checkbox" def={false} />
          <OptInput k="edit.italic" label="Italic" type="checkbox" def={false} />
        </Section>
        <Section title="Find and replace">
          <OptInput k="replace.find" label="Find" def="" />
          <OptInput k="replace.with" label="Replace with" def="" />
          <ActionButton label="Replace all" onClick={async () => {
            const r = await ed.runOp<{ replaced: number }>('replace_text', { find: opt(ed, 'replace.find', ''), replace: opt(ed, 'replace.with', '') })
            if (r) ed.notify(`Replaced ${r.replaced} occurrence(s)`, 'success')
          }} />
        </Section>
        <Section title="Crop and delete options">
          <OptInput k="crop.all" label="Crop applies to all pages" type="checkbox" def={false} />
          <OptInput k="edit.removeText" label="Area delete also removes text" type="checkbox" def={false} />
        </Section>
        <Section title="Attachments">
          <ActionButton label="Attach a file to the PDF…" onClick={async () => {
            const [file] = await ed.pickFile('*/*')
            if (file) await ed.runOp('add_attachment', { blob_id: await api.blob(file) })
          }} />
          {ed.info?.attachments.map((name) => (
            <div key={name} className="row between">
              <span className="ellipsis">📎 {name}</span>
              <button className="danger small" onClick={() => ed.runOp('delete_attachment', { name })}>Remove</button>
            </div>
          ))}
        </Section>
        {id && <p className="muted small">Tip: edits keep the original font when it contains every needed character.</p>}
      </>
    )
  },
}

export const enhanceGroup: ToolGroup = {
  id: 'enhance',
  label: 'Watermark & Header',
  icon: '🏷️',
  description: 'Watermark, header and footer, Bates numbering, page background',
  needsDoc: true,
  tools: [],
  Panel() {
    const ed = useEditor()
    return (
      <>
        <Section title="Apply to">
          <PagesOption k="enh" />
        </Section>
        <Section title="Watermark">
          <OptInput k="wm.text" label="Text" def="CONFIDENTIAL" />
          <OptInput k="wm.size" label="Font size" type="number" def={60} />
          <OptInput k="wm.color" label="Color" type="color" def="#888888" />
          <OptInput k="wm.opacity" label="Opacity (0-1)" type="number" def={0.25} />
          <OptInput k="wm.angle" label="Angle" type="number" def={45} />
          <OptInput k="wm.behind" label="Behind page content" type="checkbox" def={false} />
          <ActionButton label="Add text watermark" kind="primary" onClick={() => ed.runOp('add_watermark', {
            text: opt(ed, 'wm.text', 'CONFIDENTIAL'), fontsize: opt(ed, 'wm.size', 60), color: opt(ed, 'wm.color', '#888888'),
            opacity: opt(ed, 'wm.opacity', 0.25), angle: opt(ed, 'wm.angle', 45), behind: opt(ed, 'wm.behind', false),
            pages: targetPages(ed, 'enh'),
          })} />
          <ActionButton label="Add image watermark…" onClick={async () => {
            const [file] = await ed.pickFile('image/*')
            if (file) await ed.runOp('add_watermark', { blob_id: await api.blob(file), opacity: opt(ed, 'wm.opacity', 0.25),
              behind: opt(ed, 'wm.behind', false), pages: targetPages(ed, 'enh') })
          }} />
        </Section>
        <Section title="Header & footer">
          <p className="muted small">Tokens: &lt;&lt;page&gt;&gt; &lt;&lt;pages&gt;&gt; &lt;&lt;date&gt;&gt;</p>
          <OptInput k="hf.hl" label="Header left" def="" />
          <OptInput k="hf.hc" label="Header center" def="" />
          <OptInput k="hf.hr" label="Header right" def="" />
          <OptInput k="hf.fl" label="Footer left" def="" />
          <OptInput k="hf.fc" label="Footer center" def="Page <<page>> of <<pages>>" />
          <OptInput k="hf.fr" label="Footer right" def="" />
          <OptInput k="hf.size" label="Font size" type="number" def={10} />
          <OptInput k="hf.start" label="Start number" type="number" def={1} />
          <ActionButton label="Add header & footer" kind="primary" onClick={() => ed.runOp('header_footer', {
            header_left: opt(ed, 'hf.hl', ''), header_center: opt(ed, 'hf.hc', ''), header_right: opt(ed, 'hf.hr', ''),
            footer_left: opt(ed, 'hf.fl', ''), footer_center: opt(ed, 'hf.fc', 'Page <<page>> of <<pages>>'),
            footer_right: opt(ed, 'hf.fr', ''), fontsize: opt(ed, 'hf.size', 10), start_number: opt(ed, 'hf.start', 1),
            pages: targetPages(ed, 'enh'),
          })} />
        </Section>
        <Section title="Bates numbering">
          <OptInput k="bates.prefix" label="Prefix" def="" />
          <OptInput k="bates.suffix" label="Suffix" def="" />
          <OptInput k="bates.start" label="Start" type="number" def={1} />
          <OptInput k="bates.digits" label="Digits" type="number" def={6} />
          <OptInput k="bates.pos" label="Position" type="select" def="footer_right"
            options={['footer_right', 'footer_left', 'footer_center', 'header_right', 'header_left']} />
          <ActionButton label="Apply Bates numbers" kind="primary" onClick={async () => {
            const r = await ed.runOp<{ first: string; last: string }>('bates_number', {
              prefix: opt(ed, 'bates.prefix', ''), suffix: opt(ed, 'bates.suffix', ''), start: opt(ed, 'bates.start', 1),
              digits: opt(ed, 'bates.digits', 6), position: opt(ed, 'bates.pos', 'footer_right'),
            })
            if (r) ed.notify(`Numbered ${r.first} to ${r.last}`, 'success')
          }} />
        </Section>
        <Section title="Background">
          <OptInput k="bg.color" label="Color" type="color" def="#fff8e0" />
          <ActionButton label="Set background color" onClick={() => ed.runOp('set_background', { color: opt(ed, 'bg.color', '#fff8e0'), pages: targetPages(ed, 'enh') })} />
          <ActionButton label="Set background image…" onClick={async () => {
            const [file] = await ed.pickFile('image/*')
            if (file) await ed.runOp('set_background', { blob_id: await api.blob(file), pages: targetPages(ed, 'enh') })
          }} />
        </Section>
      </>
    )
  },
}

export const propertiesGroup: ToolGroup = {
  id: 'properties',
  label: 'Properties',
  icon: 'ℹ️',
  description: 'Title, author, keywords and page numbering',
  needsDoc: true,
  tools: [],
  Panel() {
    const ed = useEditor()
    const meta = ed.info?.metadata ?? {}
    return (
      <>
        <Section title="Document properties">
          <OptInput k="meta.title" label="Title" def={meta.title ?? ''} />
          <OptInput k="meta.author" label="Author" def={meta.author ?? ''} />
          <OptInput k="meta.subject" label="Subject" def={meta.subject ?? ''} />
          <OptInput k="meta.keywords" label="Keywords" def={meta.keywords ?? ''} />
          <ActionButton label="Save properties" kind="primary" onClick={() => ed.runOp('set_metadata', {
            title: opt(ed, 'meta.title', meta.title ?? ''), author: opt(ed, 'meta.author', meta.author ?? ''),
            subject: opt(ed, 'meta.subject', meta.subject ?? ''), keywords: opt(ed, 'meta.keywords', meta.keywords ?? ''),
          })} />
        </Section>
        <Section title="Facts">
          <dl className="facts">
            <dt>Pages</dt><dd>{ed.info?.page_count}</dd>
            <dt>File size</dt><dd>{((ed.info?.file_size ?? 0) / 1024).toFixed(1)} KB</dd>
            <dt>Encrypted</dt><dd>{ed.info?.encrypted ? 'Yes' : 'No'}</dd>
            <dt>Producer</dt><dd>{meta.producer ?? '—'}</dd>
            <dt>Format</dt><dd>{meta.format ?? '—'}</dd>
            <dt>Location</dt><dd className="ellipsis">{ed.info?.source_path ?? 'Not saved to disk'}</dd>
          </dl>
        </Section>
        <Section title="Page numbering">
          <p className="muted small">Number pages before a start page with roman numerals (front matter).</p>
          <OptInput k="labels.front" label="Pages of front matter" type="number" def={0} />
          <ActionButton label="Apply page labels" onClick={() => {
            const front = Number(opt(ed, 'labels.front', 0))
            const rules = front > 0 ? [{ startpage: 0, style: 'r' }, { startpage: front, style: 'D', firstpagenum: 1 }] : [{ startpage: 0, style: 'D' }]
            return ed.runOp('set_page_labels', { rules })
          }} />
        </Section>
      </>
    )
  },
}
