import { useEditor } from '../editor'
import { GROUPS } from '../tools'

export function ToolsPanel() {
  const ed = useEditor()
  const group = GROUPS.find((g) => g.id === ed.group)

  if (!group) {
    return (
      <aside className="tools-panel">
        <h3>All tools</h3>
        <div className="tool-grid">
          {GROUPS.map((g) => (
            <button key={g.id} className="tool-card" disabled={g.needsDoc && !ed.info}
              onClick={() => { ed.setGroup(g.id); ed.setTool(g.tools[0]?.id ?? null) }} title={g.description}>
              <span className="tool-icon">{g.icon}</span>
              <span className="tool-name">{g.label}</span>
              <span className="tool-desc">{g.description}</span>
            </button>
          ))}
        </div>
      </aside>
    )
  }

  const Panel = group.Panel
  return (
    <aside className="tools-panel">
      <div className="row between">
        <button className="link" onClick={() => { ed.setGroup(null); ed.setTool(null) }}>← All tools</button>
      </div>
      <h3>{group.icon} {group.label}</h3>
      {group.tools.length > 0 && (
        <div className="tool-buttons">
          {group.tools.map((t) => (
            <button key={t.id} className={ed.tool?.id === t.id ? 'active' : ''}
              onClick={() => ed.setTool(ed.tool?.id === t.id ? null : t.id)} title={t.hint}>
              {t.label}
            </button>
          ))}
        </div>
      )}
      {ed.tool?.hint && <p className="hint">👉 {ed.tool.hint}</p>}
      {(!group.needsDoc || ed.info) && Panel && <Panel />}
    </aside>
  )
}
