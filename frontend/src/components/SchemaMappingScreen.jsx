import { useEffect, useState } from 'react'
import { fetchSchema, proposeMapping } from '../api'

const CONFIDENCE_LEVELS = ['high', 'medium', 'low']

function SchemaMappingScreen({ onConfirm }) {
  const [status, setStatus] = useState('loading-schema') // loading-schema | loading-mapping | ready | error
  const [error, setError] = useState(null)
  const [schema, setSchema] = useState(null)
  const [rows, setRows] = useState([])

  useEffect(() => {
    let cancelled = false

    async function load() {
      setStatus('loading-schema')
      setError(null)
      try {
        const schemaData = await fetchSchema()
        if (cancelled) return
        setSchema(schemaData)

        setStatus('loading-mapping')
        const mappingData = await proposeMapping()
        if (cancelled) return
        setRows(mappingData.mappings.map((m) => ({ ...m })))
        setStatus('ready')
      } catch (err) {
        if (!cancelled) {
          setError(err.message)
          setStatus('error')
        }
      }
    }

    load()
    return () => {
      cancelled = true
    }
  }, [])

  function updateRow(index, field, value) {
    setRows((prev) => prev.map((row, i) => (i === index ? { ...row, [field]: value } : row)))
  }

  if (status === 'loading-schema' || status === 'loading-mapping') {
    return (
      <div className="mapping-screen">
        <h2>Schema mapping</h2>
        <p className="hint">
          {status === 'loading-schema'
            ? 'Fetching live schema from Prometheus and InfluxDB…'
            : 'Asking the LLM to propose a schema mapping…'}
        </p>
      </div>
    )
  }

  if (status === 'error') {
    return (
      <div className="mapping-screen">
        <h2>Schema mapping</h2>
        <p className="error">Failed to load schema mapping: {error}</p>
        <p className="hint">
          Make sure the schema-introspection docker-compose stack is running (see README), or skip this
          step to translate without a confirmed schema mapping.
        </p>
        <button className="decision-btn" onClick={() => onConfirm([])}>
          Skip mapping
        </button>
      </div>
    )
  }

  const prometheusCount = Object.keys(schema?.prometheus?.metrics ?? {}).length
  const influxCount = Object.keys(schema?.influxdb?.measurements ?? {}).length

  return (
    <div className="mapping-screen">
      <h2>Confirm schema mapping</h2>
      <p className="hint">
        Found {prometheusCount} Prometheus metric{prometheusCount === 1 ? '' : 's'} and {influxCount} InfluxDB
        measurement{influxCount === 1 ? '' : 's'}. Review and adjust the proposed mapping below - it will be
        used to ground query translation instead of guessing target names.
      </p>

      {rows.length === 0 ? (
        <p className="hint">No mappings were proposed.</p>
      ) : (
        <table className="mapping-table">
          <thead>
            <tr>
              <th>Source metric</th>
              <th>Proposed target</th>
              <th>Confidence</th>
              <th>Reasoning</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={row.source}>
                <td>{row.source}</td>
                <td>
                  <input value={row.target} onChange={(e) => updateRow(i, 'target', e.target.value)} />
                </td>
                <td>
                  <select value={row.confidence} onChange={(e) => updateRow(i, 'confidence', e.target.value)}>
                    {CONFIDENCE_LEVELS.map((level) => (
                      <option key={level} value={level}>
                        {level}
                      </option>
                    ))}
                  </select>
                </td>
                <td>
                  <input value={row.reasoning} onChange={(e) => updateRow(i, 'reasoning', e.target.value)} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <div className="mapping-actions">
        <button className="decision-btn approve active" onClick={() => onConfirm(rows)}>
          Confirm Mapping
        </button>
        <button className="decision-btn" onClick={() => onConfirm([])}>
          Skip mapping
        </button>
      </div>
    </div>
  )
}

export default SchemaMappingScreen
