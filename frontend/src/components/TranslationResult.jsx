import QueryDecision from './QueryDecision'

function ConfidenceBadge({ confidence }) {
  return <span className={`badge badge-${confidence}`}>{confidence}</span>
}

function StatusBadge({ status }) {
  return <span className={`badge badge-${status}`}>{status}</span>
}

function TranslationResult({ selectedPanel, result, loading, error, decisions, onDecide }) {
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
      {result.translations.map((t) => {
        const decisionKey = `${result.panel_id}:${t.ref_id}`
        const decision = decisions[decisionKey]
        const status = decision?.status ?? 'pending'

        return (
          <div key={t.ref_id} className="query-card">
            <div className="query-card-header">
              <strong>{t.ref_id}</strong>
              <ConfidenceBadge confidence={t.confidence} />
              {t.needs_review && <span className="badge badge-review">needs review</span>}
              <StatusBadge status={status} />
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
            <QueryDecision
              status={status}
              savedQuery={decision?.translatedQuery ?? null}
              defaultQuery={t.translated_query}
              onApprove={() => onDecide(result.panel_id, t.ref_id, 'approved', t.translated_query)}
              onReject={() => onDecide(result.panel_id, t.ref_id, 'rejected', null)}
              onEdit={(text) => onDecide(result.panel_id, t.ref_id, 'edited', text)}
            />
          </div>
        )
      })}
    </div>
  )
}

export default TranslationResult
