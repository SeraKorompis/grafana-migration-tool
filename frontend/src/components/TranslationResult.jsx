function ConfidenceBadge({ confidence }) {
  return <span className={`badge badge-${confidence}`}>{confidence}</span>
}

function TranslationResult({ selectedPanel, result, loading, error }) {
  if (!selectedPanel) return <p className="hint">Select a panel to translate its queries.</p>
  if (loading) return <p className="hint">Translating {selectedPanel.title}…</p>
  if (error) return <p className="error">{error}</p>
  if (!result) return null

  return (
    <div>
      <h2>{result.panel_title}</h2>
      <p className="languages">
        {result.source_language} → {result.target_language}
      </p>
      {result.translations.map((t) => (
        <div key={t.ref_id} className="query-card">
          <div className="query-card-header">
            <strong>{t.ref_id}</strong>
            <ConfidenceBadge confidence={t.confidence} />
            {t.needs_review && <span className="badge badge-review">needs review</span>}
          </div>
          <div className="query-block">
            <h4>Original ({result.source_language})</h4>
            <pre>{t.source_expr}</pre>
          </div>
          <div className="query-block">
            <h4>Translated ({result.target_language})</h4>
            <pre>{t.translated_query}</pre>
          </div>
          <div className="reasoning">
            <h4>Reasoning</h4>
            <p>{t.reasoning}</p>
          </div>
        </div>
      ))}
    </div>
  )
}

export default TranslationResult
