import { useEffect, useState } from 'react'
import { useEditor } from '../editor'
import { toViewBox, type PageViewport } from '../pdf'
import type { Annotation } from '../types'

export function AnnotPopover({ annot, viewport }: { annot: Annotation; viewport: PageViewport }) {
  const ed = useEditor()
  const [text, setText] = useState(annot.contents)
  const [reply, setReply] = useState('')
  useEffect(() => setText(annot.contents), [annot.xref, annot.contents])
  const box = toViewBox(viewport, annot.rect)
  const replies = ed.info?.annotations.filter((a) => a.reply_to === annot.xref) ?? []
  const below = box.top + box.height + 8
  const left = Math.min(Math.max(box.left, 4), viewport.width - 284)

  const run = async (name: string, params: object, close = false) => {
    const r = await ed.runOp(name, { page: annot.page, xref: annot.xref, ...params })
    if (r !== null && close) ed.setSelectedAnnot(null)
  }

  return (
    <div className="annot-popover" style={{ left, top: below }} onClick={(e) => e.stopPropagation()}>
      <div className="row between">
        <strong>{annot.type}</strong>
        <span className="muted">{annot.author}</span>
        <button className="icon" onClick={() => ed.setSelectedAnnot(null)} aria-label="Close">×</button>
      </div>
      <textarea value={text} onChange={(e) => setText(e.target.value)} rows={3} placeholder="Comment text" />
      <div className="row">
        <input
          type="color"
          value={annot.color ?? '#ffd400'}
          onChange={(e) => run('update_annotation', { color: e.target.value })}
          title="Color"
        />
        <button onClick={() => run('update_annotation', { contents: text })}>Save</button>
        <button className="danger" onClick={() => run('delete_annotation', {}, true)}>Delete</button>
      </div>
      {replies.map((r) => (
        <div key={r.xref} className="reply">
          <span className="muted">{r.author}:</span> {r.contents}
        </div>
      ))}
      <div className="row">
        <input value={reply} onChange={(e) => setReply(e.target.value)} placeholder="Reply…" />
        <button
          disabled={!reply.trim()}
          onClick={async () => {
            await run('reply_annotation', { text: reply })
            setReply('')
          }}
        >
          Reply
        </button>
      </div>
    </div>
  )
}
