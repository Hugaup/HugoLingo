import { useState, useEffect, useRef } from 'react'
import { api } from '../../api'
import { PERSON_LABELS, sortedTable, sortTenses, tenseLabel } from '../../utils/conjugationUtils'

export default function VerbLookup({ language }) {
  const [query, setQuery]           = useState('')
  const [suggestions, setSuggestions] = useState([])
  const [table, setTable]           = useState(null)
  const [loading, setLoading]       = useState(false)
  const [error, setError]           = useState(null)
  const [allMoods, setAllMoods]     = useState([])
  const [selectedMoods, setSelectedMoods] = useState([])
  const [filterOpen, setFilterOpen] = useState(false)
  const filterRef   = useRef(null)

  useEffect(() => {
    api.getVerbTenses(language).then(data => {
      const sorted = sortTenses(language, data)
      const moods = [...new Set(sorted.map(t => t.mood))]
      setAllMoods(moods)
    }).catch(() => {})
  }, [language])

  useEffect(() => {
    if (!query.trim()) return
    const t = setTimeout(() => {
      api.searchVerbs(language, query).then(setSuggestions).catch(() => {})
    }, 280)
    return () => clearTimeout(t)
  }, [query, language])

  useEffect(() => {
    function handler(e) {
      if (filterRef.current && !filterRef.current.contains(e.target)) setFilterOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  async function lookup(verb) {
    setQuery(verb); setSuggestions([]); setError(null); setLoading(true)
    try {
      const moodsParam = selectedMoods.length ? selectedMoods.join(',') : null
      const data = await api.getVerbTable(language, verb, moodsParam)
      setTable(data)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  function toggleMood(mood) {
    setSelectedMoods(prev => prev.includes(mood) ? prev.filter(m => m !== mood) : [...prev, mood])
  }

  const labels = PERSON_LABELS[language] || {}

  return (
    <div>
      <div style={s.searchRow}>
        <div style={{ position: 'relative', flex: 1 }}>
          <input
            style={s.input}
            value={query}
            onChange={e => setQuery(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && query.trim() && lookup(query.trim())}
            placeholder="Type a verb and press Enter…"
          />
          {query.trim() && suggestions.length > 0 && (
            <ul style={s.suggestions}>
              {suggestions.map(v => (
                <li key={v} style={s.suggestionItem} onMouseDown={() => lookup(v)}>{v}</li>
              ))}
            </ul>
          )}
        </div>

        <div ref={filterRef} style={{ position: 'relative' }}>
          <button style={s.filterBtn} onClick={() => setFilterOpen(o => !o)}>
            {selectedMoods.length ? `${selectedMoods.length} mood(s) ▲` : 'Filter ▼'}
          </button>
          {filterOpen && (
            <div style={s.filterDropdown}>
              <p style={s.filterLabel}>Show moods:</p>
              {allMoods.map(mood => (
                <label key={mood} style={s.checkLabel}>
                  <input type="checkbox" checked={selectedMoods.includes(mood)} onChange={() => toggleMood(mood)} />
                  {' '}{mood}
                </label>
              ))}
              {selectedMoods.length > 0 && (
                <button style={s.clearBtn} onClick={() => setSelectedMoods([])}>Clear filter</button>
              )}
            </div>
          )}
        </div>

        <button style={s.lookupBtn} disabled={!query.trim() || loading} onClick={() => lookup(query.trim())}>
          {loading ? '…' : 'Look up'}
        </button>
      </div>

      {error && <p style={s.error}>{error}</p>}

      {table && (
        <div style={s.tableWrap}>
          <h3 style={s.infinitiveTitle}>{table.infinitive}</h3>
          {sortedTable(language, table.table).map(({ mood, tenses }) => (
            <div key={mood} style={s.moodBlock}>
              <h4 style={s.moodTitle}>{mood}</h4>
              <div style={s.tenseGrid}>
                {tenses.map(({ tense, forms }) => (
                  <div key={tense} style={s.tenseBlock}>
                    <p style={s.tenseLabel}>{tenseLabel(language, mood, tense)}</p>
                    <table style={s.conjTable}>
                      <tbody>
                        {forms.map(({ person, form, alternates = [] }) => (
                          <tr key={person}>
                            <td style={s.personCell}>{labels[person] || person}</td>
                            <td style={s.formCell}>
                              <div>{form}</div>
                              {alternates.map(alt => (
                                <div key={alt} style={s.altForm}>/ {alt}</div>
                              ))}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

const s = {
  searchRow: { display: 'flex', gap: '0.5rem', alignItems: 'flex-start' },
  input: { width: '100%', padding: '0.6rem 0.85rem', border: '2px solid #d1d5db', borderRadius: 8, fontSize: '1rem', boxSizing: 'border-box' },
  suggestions: { position: 'absolute', top: '100%', left: 0, right: 0, background: '#fff', border: '1px solid #d1d5db', borderRadius: 8, margin: 0, padding: 0, listStyle: 'none', zIndex: 10, boxShadow: '0 4px 12px rgba(0,0,0,0.1)', maxHeight: 220, overflowY: 'auto' },
  suggestionItem: { padding: '0.5rem 0.85rem', cursor: 'pointer', fontSize: '0.95rem' },
  filterBtn: { whiteSpace: 'nowrap', padding: '0.6rem 0.9rem', border: '2px solid #d1d5db', borderRadius: 8, background: '#fff', cursor: 'pointer', fontSize: '0.9rem' },
  filterDropdown: { position: 'absolute', right: 0, top: '110%', background: '#fff', border: '1px solid #d1d5db', borderRadius: 10, padding: '0.75rem 1rem', zIndex: 20, boxShadow: '0 4px 16px rgba(0,0,0,0.12)', minWidth: 200 },
  filterLabel: { margin: '0 0 0.5rem', fontWeight: 600, fontSize: '0.85rem', color: '#555' },
  checkLabel: { display: 'block', marginBottom: '0.35rem', fontSize: '0.9rem', cursor: 'pointer' },
  clearBtn: { marginTop: '0.5rem', background: 'none', border: 'none', color: '#ef4444', cursor: 'pointer', fontSize: '0.85rem', padding: 0 },
  lookupBtn: { whiteSpace: 'nowrap', padding: '0.6rem 1.25rem', background: '#4f46e5', color: '#fff', border: 'none', borderRadius: 8, fontWeight: 600, cursor: 'pointer', fontSize: '0.9rem' },
  error: { color: '#dc2626', fontSize: '0.9rem', marginTop: '0.5rem' },
  tableWrap: { marginTop: '1.5rem' },
  infinitiveTitle: { fontSize: '1.4rem', fontWeight: 700, marginBottom: '1rem', color: '#1e1b4b' },
  moodBlock: { marginBottom: '1.5rem' },
  moodTitle: { fontSize: '1rem', fontWeight: 700, color: '#4f46e5', borderBottom: '2px solid #e0e7ff', paddingBottom: '0.25rem', marginBottom: '0.75rem' },
  tenseGrid: { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))', gap: '0.75rem' },
  tenseBlock: { background: '#f8f9fa', borderRadius: 8, padding: '0.75rem' },
  tenseLabel: { margin: '0 0 0.5rem', fontWeight: 600, fontSize: '0.8rem', color: '#6b7280', textTransform: 'uppercase', letterSpacing: '0.04em' },
  conjTable: { borderCollapse: 'collapse', width: '100%' },
  personCell: { fontSize: '0.8rem', color: '#9ca3af', paddingRight: '0.5rem', paddingTop: '0.3rem', whiteSpace: 'nowrap', verticalAlign: 'top' },
  formCell: { fontSize: '0.92rem', color: '#111', fontWeight: 500, paddingTop: '0.3rem', lineHeight: 1.35 },
  altForm: { fontSize: '0.82rem', color: '#6b7280', fontWeight: 400 },
}
