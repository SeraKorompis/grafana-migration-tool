import { useEffect, useState } from 'react'
import { fetchPanels, translatePanel } from './api'
import PanelList from './components/PanelList'
import TranslationResult from './components/TranslationResult'
import './App.css'

const TARGET_LANGUAGES = ['InfluxDB Flux', 'LogQL', 'SQL']

function App() {
  const [panels, setPanels] = useState([])
  const [loadError, setLoadError] = useState(null)
  const [selectedPanel, setSelectedPanel] = useState(null)
  const [targetLanguage, setTargetLanguage] = useState(TARGET_LANGUAGES[0])
  const [result, setResult] = useState(null)
  const [translating, setTranslating] = useState(false)
  const [translateError, setTranslateError] = useState(null)

  useEffect(() => {
    fetchPanels()
      .then(setPanels)
      .catch((err) => setLoadError(err.message))
  }, [])

  useEffect(() => {
    if (!selectedPanel) return
    let cancelled = false
    setResult(null)
    setTranslateError(null)
    setTranslating(true)
    translatePanel(selectedPanel, targetLanguage)
      .then((data) => {
        if (!cancelled) setResult(data)
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
  }, [selectedPanel, targetLanguage])

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

      {loadError && <p className="error">Failed to load dashboard: {loadError}</p>}

      <div className="layout">
        <aside>
          <PanelList panels={panels} selectedId={selectedPanel?.id} onSelect={setSelectedPanel} />
        </aside>
        <main>
          <TranslationResult
            selectedPanel={selectedPanel}
            result={result}
            loading={translating}
            error={translateError}
          />
        </main>
      </div>
    </div>
  )
}

export default App
