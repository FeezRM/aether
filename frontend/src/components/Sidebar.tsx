import { useState } from 'react'
import { useEditor, type Editor } from '../editor'
import { Thumb } from './Thumb'

type Panel = 'pages' | 'bookmarks' | 'comments' | 'attachments'

/** Shared click-to-select logic for thumbnails (plain, Shift range, Cmd/Ctrl toggle). */
export function selectPage(ed: Editor, i: number, e: React.MouseEvent) {
  const sel = ed.selectedPages
  if (e.shiftKey && sel.length) {
    const from = sel[sel.length - 1]
    const range = Array.from({ length: Math.abs(i - from) + 1 }, (_, k) => Math.min(i, from) + k)
    ed.setSelectedPages([...new Set([...sel, ...range])])
  } else if (e.metaKey || e.ctrlKey) {
    ed.setSelectedPages(sel.includes(i) ? sel.filter((p) => p !== i) : [...sel, i])
  } else {
    ed.setSelectedPages([i])
  }
}

/** Move a page by drag and drop. */
export function useDragReorder(ed: Editor) {
  const [dragging, setDragging] = useState<number | null>(null)
  const [over, setOver] = useState<number | null>(null)
  return {
    dragging, over,
    props: (i: number) => ({
      draggable: true,
      onDragStart: () => setDragging(i),
      onDragOver: (e: React.DragEvent) => { e.preventDefault(); setOver(i) },
      onDragEnd: () => { setDragging(null); setOver(null) },
      onDrop: async (e: React.DragEvent) => {
        e.preventDefault()
        if (dragging !== null && dragging !== i) await ed.runOp('move_page', { page: dragging, to: i })
        setDragging(null)
        setOver(null)
      },
    }),
  }
}

export function Sidebar() {
  const ed = useEditor()
  const [panel, setPanel] = useState<Panel>('pages')
  const info = ed.info!
  const drag = useDragReorder(ed)
  const comments = info.annotations.filter((a) => !['Link', 'Widget', 'Popup'].includes(a.type))

  return (
    <aside className="sidebar">
      <div className="side-tabs">
        {([['pages', '▤', 'Pages'], ['bookmarks', '🔖', 'Bookmarks'], ['comments', '💬', 'Comments'], ['attachments', '📎', 'Attachments']] as const).map(
          ([id, icon, label]) => (
            <button key={id} className={panel === id ? 'active' : ''} title={label} onClick={() => setPanel(id)}>
              {icon}
            </button>
          ),
        )}
      </div>
      <div className="side-body">
        {panel === 'pages' && (
          <div className="thumbs">
            {info.pages.map((p) => (
              <div
                key={p.index}
                className={`thumb-item ${ed.page === p.index ? 'current' : ''} ${ed.selectedPages.includes(p.index) ? 'selected' : ''} ${drag.over === p.index ? 'drop' : ''}`}
                onClick={(e) => { selectPage(ed, p.index, e); ed.goTo(p.index) }}
                {...drag.props(p.index)}
              >
                <Thumb index={p.index} width={120} />
                <span>{p.label}</span>
              </div>
            ))}
          </div>
        )}
        {panel === 'bookmarks' && <Bookmarks />}
        {panel === 'comments' && (
          <div className="list">
            <h4>{comments.length} comment(s)</h4>
            {comments.map((a) => (
              <div key={`${a.page}-${a.xref}`} className={`list-item comment ${a.reply_to ? 'reply' : ''}`}
                onClick={() => { ed.goTo(a.page); ed.setTool(null); ed.setSelectedAnnot(a.xref) }}>
                <div className="row between">
                  <strong className="small">{a.type}</strong>
                  <span className="muted small">p{a.page + 1}</span>
                </div>
                {a.contents && <div className="small">{a.contents}</div>}
                <div className="muted small">{a.author}</div>
              </div>
            ))}
          </div>
        )}
        {panel === 'attachments' && (
          <div className="list">
            <h4>{info.attachments.length} attachment(s)</h4>
            {info.attachments.map((n) => <div key={n} className="list-item">📎 {n}</div>)}
            <p className="muted small">Add or remove attachments in Edit PDF.</p>
          </div>
        )}
      </div>
    </aside>
  )
}

function Bookmarks() {
  const ed = useEditor()
  const outline = ed.info!.outline
  return (
    <div className="list">
      <div className="row">
        <button className="small" onClick={async () => {
          const v = await ed.prompt('New bookmark', [{ name: 'title', label: 'Title', value: `Page ${ed.page + 1}` }])
          if (v?.title) await ed.runOp('add_bookmark', { title: v.title, page: ed.page })
        }}>+ Add (current page)</button>
        <button className="small" onClick={async () => {
          const r = await ed.runOp<{ count: number }>('auto_bookmarks', {})
          if (r) ed.notify(`Created ${r.count} bookmarks from headings`, 'success')
        }}>Auto</button>
      </div>
      {outline.length === 0 && <p className="muted small">No bookmarks.</p>}
      {outline.map((b, i) => (
        <div key={i} className="list-item bookmark" style={{ paddingLeft: 8 + (b.level - 1) * 14 }} onClick={() => ed.goTo(b.page)}>
          <span className="ellipsis">{b.title}</span>
          <span className="bm-actions">
            <button className="icon" title="Rename" onClick={async (e) => {
              e.stopPropagation()
              const v = await ed.prompt('Rename bookmark', [{ name: 'title', label: 'Title', value: b.title }])
              if (v?.title) await ed.runOp('rename_bookmark', { index: i, title: v.title })
            }}>✎</button>
            <button className="icon" title="Delete" onClick={(e) => { e.stopPropagation(); void ed.runOp('delete_bookmark', { index: i }) }}>×</button>
          </span>
        </div>
      ))}
    </div>
  )
}
