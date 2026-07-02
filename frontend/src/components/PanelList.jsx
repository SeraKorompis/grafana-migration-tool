function panelDecisionState(panel, decisions) {
  const total = panel.queries.length
  if (total === 0) return 'none'
  const decided = panel.queries.filter((q) => decisions[`${panel.id}:${q.ref_id}`]).length
  if (decided === total) return 'complete'
  if (decided > 0) return 'partial'
  return 'none'
}

function StatusDot({ state }) {
  if (state === 'complete') return <span className="panel-status complete" title="All queries decided">✓</span>
  if (state === 'partial') return <span className="panel-status partial" title="Some queries decided">●</span>
  return null
}

function PanelList({ panels, selectedId, onSelect, decisions }) {
  return (
    <ul className="panel-list">
      {panels.map((panel) => {
        const state = panelDecisionState(panel, decisions)
        return (
          <li key={panel.id}>
            <button className={panel.id === selectedId ? 'selected' : ''} onClick={() => onSelect(panel)}>
              <span className="panel-title">
                <StatusDot state={state} />
                {panel.title}
              </span>
              <span className="query-count">
                {panel.queries.length} quer{panel.queries.length === 1 ? 'y' : 'ies'}
              </span>
            </button>
          </li>
        )
      })}
    </ul>
  )
}

export default PanelList
