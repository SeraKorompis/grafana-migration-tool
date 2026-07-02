const API_BASE = 'http://localhost:8000'

export async function fetchDashboardList() {
  const res = await fetch(`${API_BASE}/dashboards`)
  if (!res.ok) throw new Error(`Failed to load dashboard list (${res.status})`)
  return res.json()
}

export async function fetchPanels(file) {
  const url = file ? `${API_BASE}/parse?file=${encodeURIComponent(file)}` : `${API_BASE}/parse`
  const res = await fetch(url)
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

export async function exportDashboard(decisions, targetLanguage, file) {
  const res = await fetch(`${API_BASE}/export`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ decisions, target_language: targetLanguage, file }),
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail || `Export failed (${res.status})`)
  }
  return res.json()
}
