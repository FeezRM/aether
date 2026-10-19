import { useEditor } from '../editor'
import { selectPage, useDragReorder } from './Sidebar'
import { Thumb } from './Thumb'

/** Organize Pages: a grid of large thumbnails with selection and drag-to-reorder. */
export function PageGrid() {
  const ed = useEditor()
  const drag = useDragReorder(ed)
  return (
    <div className="page-grid">
      {ed.info!.pages.map((p) => (
        <div
          key={p.index}
          className={`grid-item ${ed.selectedPages.includes(p.index) ? 'selected' : ''} ${drag.over === p.index ? 'drop' : ''} ${drag.dragging === p.index ? 'dragging' : ''}`}
          onClick={(e) => selectPage(ed, p.index, e)}
          onDoubleClick={() => { ed.setGroup(null); ed.goTo(p.index) }}
          {...drag.props(p.index)}
        >
          <Thumb index={p.index} width={170} />
          <div className="grid-label">
            {p.label}
            <span className="grid-actions">
              <button className="icon" title="Rotate" onClick={(e) => { e.stopPropagation(); void ed.runOp('rotate_pages', { angle: 90, pages: [p.index] }) }}>⟳</button>
              <button className="icon" title="Delete" onClick={(e) => { e.stopPropagation(); void ed.runOp('delete_pages', { pages: [p.index] }) }}>🗑</button>
            </span>
          </div>
        </div>
      ))}
    </div>
  )
}
