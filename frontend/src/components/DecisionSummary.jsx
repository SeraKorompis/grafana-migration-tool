function DecisionSummary({ counts }) {
  return (
    <div className="decision-summary">
      <span className="summary-item badge-approved">{counts.approved} approved</span>
      <span className="summary-item badge-rejected">{counts.rejected} rejected</span>
      <span className="summary-item badge-edited">{counts.edited} edited</span>
      <span className="summary-item badge-pending">{counts.pending} pending</span>
    </div>
  )
}

export default DecisionSummary
