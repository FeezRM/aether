import { useEditor } from '../editor'
import { GROUPS } from '../tools'

export function Welcome({ onOpen, onOpenPath, onBlank }: { onOpen: () => void; onOpenPath: () => void; onBlank: () => void }) {
  const ed = useEditor()
  return (
    <div className="welcome">
      <h1>LocalPDF Studio</h1>
      <p className="lead">A full PDF editor that never sends your documents anywhere. Everything runs on this computer.</p>
      <div className="drop-zone" onClick={onOpen}>
        <strong>Drop PDFs here</strong>
        <span>or click to choose files</span>
      </div>
      <div className="row center">
        <button onClick={onOpenPath}>Open from a file path…</button>
        <button onClick={onBlank}>New blank PDF</button>
      </div>
      <h4>Tools that work without opening a file</h4>
      <div className="row center wrap">
        {GROUPS.filter((g) => !g.needsDoc).map((g) => (
          <button key={g.id} onClick={() => ed.setGroup(g.id)}>{g.icon} {g.label}</button>
        ))}
      </div>
    </div>
  )
}
