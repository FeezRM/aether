import { api } from '../api'
import { opt, useEditor, type Editor, type ToolGroup } from '../editor'
import type { Gesture } from '../types'
import { ActionButton, OptInput, Section } from '../components/ui'

const color = (ed: Editor, fallback: string) => opt(ed, 'comment.color', '') || fallback

async function askText(ed: Editor, title: string, label = 'Text'): Promise<string | null> {
  const v = await ed.prompt(title, [{ name: 'text', label, type: 'textarea' }])
  return v?.text?.trim() ? v.text : null
}

const markup = (kind: string, fallback: string) => async (g: Gesture, ed: Editor) => {
  if (g.kind !== 'text') return
  await ed.runOp('add_markup', { page: g.page, rects: g.rects, kind, color: color(ed, fallback) })
}

export const STAMPS = ['Approved', 'NotApproved', 'Draft', 'Final', 'Confidential', 'ForComment',
  'ForPublicRelease', 'NotForPublicRelease', 'Departmental', 'Experimental', 'Expired', 'Sold', 'TopSecret', 'AsIs']

export const commentGroup: ToolGroup = {
  id: 'comment',
  label: 'Comment',
  icon: '💬',
  description: 'Highlights, sticky notes, text boxes and drawing markup',
  needsDoc: true,
  tools: [
    { id: 'highlight', label: 'Highlight', gesture: 'text', hint: 'Select text to highlight', onGesture: markup('highlight', '#ffd400') },
    { id: 'underline', label: 'Underline', gesture: 'text', hint: 'Select text to underline', onGesture: markup('underline', '#2a7fff') },
    { id: 'strikeout', label: 'Strikethrough', gesture: 'text', hint: 'Select text to strike out', onGesture: markup('strikeout', '#e0302d') },
    { id: 'squiggly', label: 'Squiggly', gesture: 'text', hint: 'Select text', onGesture: markup('squiggly', '#2fae4e') },
    {
      id: 'note', label: 'Sticky note', gesture: 'click', cursor: 'copy', hint: 'Click where the note goes',
      async onGesture(g, ed) {
        if (g.kind !== 'click') return
        const text = await askText(ed, 'Sticky note', 'Comment')
        if (text) await ed.runOp('add_note', { page: g.page, point: g.point, contents: text, color: color(ed, '#ffd400') })
      },
    },
    {
      id: 'textbox', label: 'Text box', gesture: 'drag', hint: 'Drag a box, then type',
      async onGesture(g, ed) {
        if (g.kind !== 'drag') return
        const text = await askText(ed, 'Text box')
        if (text) await ed.runOp('add_text_box', {
          page: g.page, rect: g.rect, text, fontsize: opt(ed, 'comment.size', 12),
          color: opt(ed, 'comment.textColor', '#000000'), border_color: color(ed, '#e0302d'),
        })
      },
    },
    {
      id: 'callout', label: 'Callout', gesture: 'drag', hint: 'Drag from the point to where the text box goes',
      async onGesture(g, ed) {
        if (g.kind !== 'drag') return
        const text = await askText(ed, 'Callout')
        if (!text) return
        const [ex, ey] = g.end
        const box: [number, number, number, number] = [ex, ey - 30, ex + 160, ey]
        await ed.runOp('add_text_box', {
          page: g.page, rect: box, text, fontsize: opt(ed, 'comment.size', 12),
          border_color: color(ed, '#e0302d'), callout: [g.start, [ex, ey - 15]],
        })
      },
    },
    {
      id: 'typewriter', label: 'Add text comment', gesture: 'click', cursor: 'text', hint: 'Click and type',
      async onGesture(g, ed) {
        if (g.kind !== 'click') return
        const text = await askText(ed, 'Typewriter text')
        if (text) await ed.runOp('add_typewriter', { page: g.page, point: g.point, text, fontsize: opt(ed, 'comment.size', 12) })
      },
    },
    ...(['rect', 'circle'] as const).map((kind) => ({
      id: `shape-${kind}`, label: kind === 'rect' ? 'Rectangle' : 'Oval', gesture: 'drag' as const,
      async onGesture(g: Gesture, ed: Editor) {
        if (g.kind !== 'drag') return
        await ed.runOp('add_shape', { page: g.page, kind, rect: g.rect, color: color(ed, '#e0302d'), width: opt(ed, 'comment.width', 1.5) })
      },
    })),
    ...(['line', 'arrow'] as const).map((kind) => ({
      id: `shape-${kind}`, label: kind === 'line' ? 'Line' : 'Arrow', gesture: 'drag' as const, hint: 'Drag from start to end',
      async onGesture(g: Gesture, ed: Editor) {
        if (g.kind !== 'drag') return
        await ed.runOp('add_shape', { page: g.page, kind, points: [g.start, g.end], color: color(ed, '#e0302d'), width: opt(ed, 'comment.width', 1.5) })
      },
    })),
    ...(['polygon', 'polyline', 'cloud'] as const).map((kind) => ({
      id: `shape-${kind}`, label: kind === 'polyline' ? 'Connected lines' : kind === 'cloud' ? 'Cloud' : 'Polygon',
      gesture: 'poly' as const, hint: 'Click points, double-click to finish (Esc cancels)',
      async onGesture(g: Gesture, ed: Editor) {
        if (g.kind !== 'poly') return
        await ed.runOp('add_shape', { page: g.page, kind, points: g.points, color: color(ed, '#e0302d'), width: opt(ed, 'comment.width', 1.5) })
      },
    })),
    {
      id: 'ink', label: 'Draw', gesture: 'ink', cursor: 'crosshair', hint: 'Draw freehand; strokes are saved after a pause',
      async onGesture(g, ed) {
        if (g.kind !== 'ink') return
        await ed.runOp('add_ink', { page: g.page, strokes: g.strokes, color: color(ed, '#2a7fff'), width: opt(ed, 'comment.width', 2) })
      },
    },
    {
      id: 'eraser', label: 'Erase drawing', gesture: 'drag', hint: 'Drag over drawings to erase them',
      async onGesture(g, ed) {
        if (g.kind !== 'drag') return
        const r = await ed.runOp<{ removed: number }>('erase_ink', { page: g.page, rect: g.rect })
        if (r) ed.notify(`Erased ${r.removed} drawing(s)`)
      },
    },
    {
      id: 'caret', label: 'Insert text mark', gesture: 'click', cursor: 'text',
      async onGesture(g, ed) {
        if (g.kind !== 'click') return
        const text = await askText(ed, 'Text to insert')
        if (text) await ed.runOp('add_caret', { page: g.page, point: g.point, contents: text })
      },
    },
    {
      id: 'attach-file', label: 'Attach file', gesture: 'click', cursor: 'copy',
      async onGesture(g, ed) {
        if (g.kind !== 'click') return
        const [file] = await ed.pickFile('*/*')
        if (!file) return
        const blob_id = await api.blob(file)
        await ed.runOp('add_file_annotation', { page: g.page, point: g.point, blob_id })
      },
    },
  ],
  Panel: CommentPanel,
}

function CommentPanel() {
  const ed = useEditor()
  const id = ed.info?.id
  return (
    <>
      <Section title="Style">
        <OptInput k="comment.color" label="Color" type="color" def="#ffd400" />
        <OptInput k="comment.textColor" label="Text color" type="color" def="#000000" />
        <OptInput k="comment.size" label="Font size" type="number" def={12} />
        <OptInput k="comment.width" label="Line width" type="number" def={1.5} />
      </Section>
      <Section title="Comments">
        <ActionButton label="Export comments (CSV)" onClick={() => id && api.comments(id, 'csv')} />
        <ActionButton label="Export comments (JSON)" onClick={() => id && api.comments(id, 'json')} />
        <ActionButton label="Flatten comments" onClick={() => ed.runOp('flatten_annotations', {})} />
        <ActionButton label="Delete all comments" kind="danger" onClick={async () => {
          if (confirm('Delete every comment in this document?')) await ed.runOp('delete_all_annotations', {})
        }} />
      </Section>
    </>
  )
}

export const stampGroup: ToolGroup = {
  id: 'stamp',
  label: 'Stamp',
  icon: '🔖',
  description: "Add stamps such as 'Approved' or 'Draft'",
  needsDoc: true,
  tools: [
    {
      id: 'stamp', label: 'Place stamp', gesture: 'drag', hint: 'Choose a stamp, then drag where it goes',
      async onGesture(g, ed) {
        if (g.kind !== 'drag') return
        await ed.runOp('add_stamp', { page: g.page, rect: g.rect, stamp: opt(ed, 'stamp.name', 'Approved') })
      },
    },
    {
      id: 'stamp-image', label: 'Custom image stamp', gesture: 'drag', hint: 'Choose an image in the panel, then drag',
      async onGesture(g, ed) {
        if (g.kind !== 'drag') return
        const blob_id = opt(ed, 'stamp.blob', '')
        if (!blob_id) return ed.notify('Choose a stamp image first', 'error')
        await ed.runOp('add_image_stamp', { page: g.page, rect: g.rect, blob_id })
      },
    },
    {
      id: 'stamp-date', label: 'Date stamp', gesture: 'drag', hint: 'Drag where the dated stamp goes',
      async onGesture(g, ed) {
        if (g.kind !== 'drag') return
        const text = `${opt(ed, 'stamp.dateLabel', 'RECEIVED')}\n${new Date().toLocaleString()}`
        await ed.runOp('add_text_box', { page: g.page, rect: g.rect, text, fontsize: 11, color: '#1a4fbf', border_color: '#1a4fbf' })
      },
    },
  ],
  Panel() {
    const ed = useEditor()
    return (
      <Section title="Stamp">
        <OptInput k="stamp.name" label="Standard stamp" type="select" def="Approved" options={STAMPS} />
        <OptInput k="stamp.dateLabel" label="Date stamp label" def="RECEIVED" />
        <ActionButton label={opt(ed, 'stamp.blobName', '') ? `Image: ${opt(ed, 'stamp.blobName', '')}` : 'Choose stamp image…'}
          onClick={async () => {
            const [file] = await ed.pickFile('image/*')
            if (!file) return
            ed.setOpt('stamp.blob', await api.blob(file))
            ed.setOpt('stamp.blobName', file.name)
            ed.setTool('stamp-image')
          }} />
      </Section>
    )
  },
}
