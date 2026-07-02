const API_BASE = 'http://localhost:8000'

export async function fetchPanels() {
  const res = await fetch(`${API_BASE}/parse`)
  if (!res.ok) throw new Error(`Failed to load dashboard (${res.status})`)
  return res.json()
}

export async function translatePanel(panel, targetLanguage) {
  const res = await fetch(`${API_BASE}/translate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ panel, target_language: targetLanguage }),
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail || `Translation failed (${res.status})`)
  }
  return res.json()
}

export async function exportDashboard(decisions, targetLanguage) {
  const res = await fetch(`${API_BASE}/export`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ decisions, target_language: targetLanguage }),
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail || `Export failed (${res.status})`)
  }
  return res.json()
}
