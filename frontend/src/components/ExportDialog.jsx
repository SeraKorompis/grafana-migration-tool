function ExportDialog({ counts, targetLanguage, exporting, error, onConfirm, onCancel }) {
  const ready = counts.approved + counts.edited
  const unmigrated = counts.rejected + counts.pending

  return (
    <div className="modal-backdrop" onClick={onCancel}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h2>Export Dashboard</h2>
        <p>
          <strong>{ready}</strong> quer{ready === 1 ? 'y' : 'ies'} will be exported migrated to{' '}
          {targetLanguage} ({counts.approved} approved, {counts.edited} edited).
        </p>
        <p>
          <strong>{unmigrated}</strong> quer{unmigrated === 1 ? 'y' : 'ies'} will keep their original,
          unmigrated query and be flagged for manual attention ({counts.rejected} rejected,{' '}
          {counts.pending} pending).
        </p>
        {error && <p className="error">{error}</p>}
        <div className="modal-actions">
          <button className="decision-btn" onClick={onCancel} disabled={exporting}>
            Cancel
          </button>
          <button className="decision-btn approve active" onClick={onConfirm} disabled={exporting}>
            {exporting ? 'Exporting…' : 'Confirm Export'}
          </button>
        </div>
      </div>
    </div>
  )
}

export default ExportDialog
