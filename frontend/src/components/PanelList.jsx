function PanelList({ panels, selectedId, onSelect }) {
  return (
    <ul className="panel-list">
      {panels.map((panel) => (
        <li key={panel.id}>
          <button
            className={panel.id === selectedId ? 'selected' : ''}
            onClick={() => onSelect(panel)}
          >
            <span>{panel.title}</span>
            <span className="query-count">
              {panel.queries.length} quer{panel.queries.length === 1 ? 'y' : 'ies'}
            </span>
          </button>
        </li>
      ))}
    </ul>
  )
}

export default PanelList
