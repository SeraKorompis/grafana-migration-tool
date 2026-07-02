import { useEffect, useState } from 'react'
import { fetchPanels, translatePanel } from './api'
import PanelList from './components/PanelList'
import TranslationResult from './components/TranslationResult'
import DecisionSummary from './components/DecisionSummary'
import './App.css'

const TARGET_LANGUAGES = ['InfluxDB Flux', 'LogQL', 'SQL']

function App() {
  const [panels, setPanels] = useState([])
  const [loadError, setLoadError] = useState(null)
  const [selectedPanel, setSelectedPanel] = useState(null)
  const [targetLanguage, setTargetLanguage] = useState(TARGET_LANGUAGES[0])
  // Cache translations per panel+language so revisiting a panel doesn't
  // re-hit the API or show different wording than what a decision was made against.
  const [translationsCache, setTranslationsCache] = useState({})
  const [translating, setTranslating] = useState(false)
  const [translateError, setTranslateError] = useState(null)
  // Decisions live here (not per-panel local state) so they survive panel switches.
  const [decisions, setDecisions] = useState({})

  useEffect(() => {
    fetchPanels()
      .then(setPanels)
      .catch((err) => setLoadError(err.message))
  }, [])

  useEffect(() => {
    if (!selectedPanel) return
    const cacheKey = `${selectedPanel.id}:${targetLanguage}`
    if (translationsCache[cacheKey]) {
      setTranslating(false)
      setTranslateError(null)
      return
    }
    let cancelled = false
    setTranslateError(null)
    setTranslating(true)
    translatePanel(selectedPanel, targetLanguage)
      .then((data) => {
        if (!cancelled) setTranslationsCache((prev) => ({ ...prev, [cacheKey]: data }))
      })
      .catch((err) => {
        if (!cancelled) setTranslateError(err.message)
      })
      .finally(() => {
        if (!cancelled) setTranslating(false)
      })
    return () => {
      cancelled = true
    }
    // translationsCache is read but intentionally left out of deps: we only
    // want to (re)fetch when the selected panel or target language changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedPanel, targetLanguage])

  function handleDecide(panelId, refId, status, translatedQuery) {
    setDecisions((prev) => ({
      ...prev,
      [`${panelId}:${refId}`]: { status, translatedQuery },
    }))
  }

  const totalQueries = panels.reduce((sum, p) => sum + p.queries.length, 0)
  const decidedCounts = { approved: 0, rejected: 0, edited: 0 }
  Object.values(decisions).forEach((d) => {
    decidedCounts[d.status] = (decidedCounts[d.status] ?? 0) + 1
  })
  const summaryCounts = {
    ...decidedCounts,
    pending: totalQueries - (decidedCounts.approved + decidedCounts.rejected + decidedCounts.edited),
  }

  const result = selectedPanel ? translationsCache[`${selectedPanel.id}:${targetLanguage}`] ?? null : null

  return (
    <div className="app">
      <header>
        <h1>Grafana Migration Tool</h1>
        <label>
          Target language:{' '}
          <select value={targetLanguage} onChange={(e) => setTargetLanguage(e.target.value)}>
            {TARGET_LANGUAGES.map((lang) => (
              <option key={lang} value={lang}>
                {lang}
              </option>
            ))}
          </select>
        </label>
      </header>

      <DecisionSummary counts={summaryCounts} />

      {loadError && <p className="error">Failed to load dashboard: {loadError}</p>}

      <div className="layout">
        <aside>
          <PanelList
            panels={panels}
            selectedId={selectedPanel?.id}
            onSelect={setSelectedPanel}
            decisions={decisions}
          />
        </aside>
        <main>
          <TranslationResult
            selectedPanel={selectedPanel}
            result={result}
            loading={translating}
            error={translateError}
            decisions={decisions}
            onDecide={handleDecide}
          />
        </main>
      </div>
    </div>
  )
}

export default App
