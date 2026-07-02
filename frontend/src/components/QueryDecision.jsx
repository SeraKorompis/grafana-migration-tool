import { useState } from 'react'

function QueryDecision({ status, savedQuery, defaultQuery, onApprove, onReject, onEdit }) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(savedQuery ?? defaultQuery)

  function startEditing() {
    setDraft(savedQuery ?? defaultQuery)
    setEditing(true)
  }

  function saveEdit() {
    onEdit(draft)
    setEditing(false)
  }

  return (
    <div className="decision">
      <div className="decision-buttons">
        <button
          className={`decision-btn approve ${status === 'approved' ? 'active' : ''}`}
          onClick={() => {
            setEditing(false)
            onApprove()
          }}
        >
          Approve
        </button>
        <button
          className={`decision-btn reject ${status === 'rejected' ? 'active' : ''}`}
          onClick={() => {
            setEditing(false)
            onReject()
          }}
        >
          Reject
        </button>
        <button className={`decision-btn edit ${status === 'edited' ? 'active' : ''}`} onClick={startEditing}>
          Edit
        </button>
      </div>

      {editing && (
        <div className="edit-box">
          <textarea value={draft} onChange={(e) => setDraft(e.target.value)} rows={5} />
          <div className="edit-actions">
            <button className="decision-btn edit active" onClick={saveEdit}>
              Save edit
            </button>
            <button className="decision-btn" onClick={() => setEditing(false)}>
              Cancel
            </button>
          </div>
        </div>
      )}

      {status === 'edited' && !editing && (
        <div className="query-block">
          <h4>Approved (edited)</h4>
          <pre>{savedQuery}</pre>
        </div>
      )}
    </div>
  )
}

export default QueryDecision
