import { useEffect, useState } from 'react'
import { fetchDashboardList, fetchPanels, translatePanel, exportDashboard } from './api'
import PanelList from './components/PanelList'
import TranslationResult from './components/TranslationResult'
import DecisionSummary from './components/DecisionSummary'
import ExportDialog from './components/ExportDialog'
import SchemaMappingScreen from './components/SchemaMappingScreen'
import './App.css'

function slugify(text) {
  return text.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '') || 'dashboard'
}

function downloadJson(data, filename) {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

const TARGET_LANGUAGES = ['InfluxDB Flux', 'LogQL', 'SQL']

function App() {
  const [dashboardFiles, setDashboardFiles] = useState([])
  const [selectedFile, setSelectedFile] = useState(null)
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
  const [showExportDialog, setShowExportDialog] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [exportError, setExportError] = useState(null)
  // null = mapping step not yet confirmed; [] = confirmed but empty/skipped.
  const [schemaMapping, setSchemaMapping] = useState(null)

  useEffect(() => {
    fetchDashboardList()
      .then((data) => {
        setDashboardFiles(data.files)
        setSelectedFile(data.default ?? data.files[0])
      })
      .catch((err) => setLoadError(err.message))
  }, [])

  useEffect(() => {
    if (!selectedFile) return
    fetchPanels(selectedFile)
      .then(setPanels)
      .catch((err) => setLoadError(err.message))
  }, [selectedFile])

  function handleSelectDashboard(file) {
    // Panel ids are only unique within a dashboard file, so decisions and cached
    // translations from the previous dashboard would otherwise bleed into this one.
    setSelectedFile(file)
    setPanels([])
    setSelectedPanel(null)
    setTranslationsCache({})
    setDecisions({})
    setTranslateError(null)
  }

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
    translatePanel(selectedPanel, targetLanguage, schemaMapping)
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
  }, [selectedPanel, targetLanguage, schemaMapping])

  function handleDecide(panelId, refId, status, translatedQuery) {
    setDecisions((prev) => ({
      ...prev,
      [`${panelId}:${refId}`]: { status, translatedQuery },
    }))
  }

  async function handleConfirmExport() {
    setExporting(true)
    setExportError(null)
    try {
      const decisionList = Object.entries(decisions).map(([key, d]) => {
        const [panelIdStr, ...refIdParts] = key.split(':')
        return {
          panel_id: Number(panelIdStr),
          ref_id: refIdParts.join(':'),
          status: d.status,
          translated_query: d.translatedQuery,
        }
      })
      const data = await exportDashboard(decisionList, targetLanguage, selectedFile)
      downloadJson(data.dashboard, `${slugify(data.dashboard.title)}.json`)
      setShowExportDialog(false)
    } catch (err) {
      setExportError(err.message)
    } finally {
      setExporting(false)
    }
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
  const hasDecisions = Object.keys(decisions).length > 0

  if (schemaMapping === null) {
    return (
      <div className="app">
        <header>
          <h1>Grafana Migration Tool</h1>
        </header>
        <SchemaMappingScreen onConfirm={setSchemaMapping} />
      </div>
    )
  }

  return (
    <div className="app">
      <header>
        <h1>Grafana Migration Tool</h1>
        <div className="header-controls">
          <label>
            Dashboard:{' '}
            <select value={selectedFile ?? ''} onChange={(e) => handleSelectDashboard(e.target.value)}>
              {dashboardFiles.map((file) => (
                <option key={file} value={file}>
                  {file}
                </option>
              ))}
            </select>
          </label>
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
          {hasDecisions && (
            <button
              className="decision-btn approve active"
              onClick={() => {
                setExportError(null)
                setShowExportDialog(true)
              }}
            >
              Export Dashboard
            </button>
          )}
        </div>
      </header>

      <DecisionSummary counts={summaryCounts} />

      {loadError && <p className="error">Failed to load dashboard: {loadError}</p>}

      {showExportDialog && (
        <ExportDialog
          counts={summaryCounts}
          targetLanguage={targetLanguage}
          exporting={exporting}
          error={exportError}
          onConfirm={handleConfirmExport}
          onCancel={() => setShowExportDialog(false)}
        />
      )}

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
