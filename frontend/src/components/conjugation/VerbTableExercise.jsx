import { useState, useEffect, useMemo } from 'react'
import { api } from '../../api'
import { PERSONS, PERSON_LABELS, sortTenses, displayTenseName, isFormCorrect } from '../../utils/conjugationUtils'
import CharPicker from './CharPicker'

const VERB_ENDINGS = { french: ['-er', '-ir', '-re'], spanish: ['-ar', '-er', '-ir'], english: [] }

// ── Setup screen ──────────────────────────────────────────────────────────────
function Setup({ language, onStart }) {
  const [count, setCount]             = useState(3)
  const [mode, setMode]               = useState('random')
  const [endings, setEndings]         = useState([])
  const [customQuery, setCustomQuery] = useState('')
  const [suggestions, setSuggestions] = useState([])
  const [customVerbs, setCustomVerbs] = useState([])
  const [subjects, setSubjects]       = useState([...PERSONS])
  const [availTenses, setAvailTenses] = useState([])
  const [selTenses, setSelTenses]     = useState([])
  const [loading, setLoading]         = useState(false)
  const [error, setError]             = useState(null)

  const availableEndings = VERB_ENDINGS[language] || []

  useEffect(() => {
    api.getVerbTenses(language).then(data => {
      const sorted = sortTenses(language, data)
      setAvailTenses(sorted)
      setSelTenses(sorted.slice(0, 3).map(t => `${t.mood}||${t.tense}`))
    }).catch(() => {})
  }, [language])

  useEffect(() => {
    if (!customQuery.trim() || mode !== 'custom') return
    const t = setTimeout(() => api.searchVerbs(language, customQuery).then(setSuggestions).catch(() => {}), 280)
    return () => clearTimeout(t)
  }, [customQuery, language, mode])

  function addCustomVerb(v) {
    if (!customVerbs.includes(v)) setCustomVerbs([...customVerbs, v])
    setCustomQuery(''); setSuggestions([])
  }

  function toggleSubject(p) {
    setSubjects(prev => prev.includes(p) ? prev.filter(x => x !== p) : [...prev, p])
  }

  function toggleTense(key) {
    setSelTenses(prev => prev.includes(key) ? prev.filter(k => k !== key) : [...prev, key])
  }

  async function handleStart() {
    if (subjects.length === 0) { setError('Select at least one subject.'); return }
    if (selTenses.length === 0) { setError('Select at least one tense.'); return }
    setError(null); setLoading(true)
    try {
      let verbs
      if (mode === 'custom') {
        verbs = customVerbs.slice(0, 10)
        if (!verbs.length) { setError('Add at least one verb.'); setLoading(false); return }
      } else {
        const endingsParam = mode === 'endings' ? endings.map(e => e.replace('-', '')).join(',') : null
        verbs = await api.getRandomVerbs(language, count, mode === 'endings' ? 'endings' : mode, endingsParam)
      }
      const tenseFilters = selTenses.map(k => {
        const [mood, tense] = k.split('||')
        return { mood, tense }
      })
      const verbTables = await Promise.all(verbs.map(v => api.getVerbTable(language, v)))
      onStart({ verbTables, subjects, tenseFilters, language })
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  const labels = PERSON_LABELS[language] || {}

  return (
    <div>
      <h3 style={s.sectionTitle}>Verb Table — Setup</h3>

      {mode !== 'custom' && (
        <div style={s.field}>
          <label style={s.label}>Number of verbs</label>
          <div style={s.chips}>
            {[1,2,3,4,5,6,7,8,9,10].map(n => (
              <button key={n} style={n === count ? {...s.chip,...s.chipOn} : s.chip} onClick={() => setCount(n)}>{n}</button>
            ))}
          </div>
        </div>
      )}

      <div style={s.field}>
        <label style={s.label}>Verb selection</label>
        <div style={s.chips}>
          {[['random','Random'],['irregular','Irregular'],
            ...(availableEndings.length ? [['endings','By ending']] : []),
            ['custom','Custom']].map(([val, lbl]) => (
            <button key={val} style={mode === val ? {...s.chip,...s.chipOn} : s.chip} onClick={() => setMode(val)}>{lbl}</button>
          ))}
        </div>
        {mode === 'endings' && availableEndings.length > 0 && (
          <div style={{ marginTop: '0.5rem' }}>
            <p style={s.hint}>Select endings to include:</p>
            <div style={s.chips}>
              {availableEndings.map(e => (
                <button key={e}
                  style={endings.includes(e) ? {...s.chip,...s.chipOn} : s.chip}
                  onClick={() => setEndings(prev => prev.includes(e) ? prev.filter(x => x !== e) : [...prev, e])}>
                  {e}
                </button>
              ))}
            </div>
          </div>
        )}
        {mode === 'custom' && (
          <div style={{ marginTop: '0.5rem', position: 'relative' }}>
            <input
              style={s.input}
              value={customQuery}
              onChange={e => setCustomQuery(e.target.value)}
              placeholder="Type a verb to add…"
            />
            {customQuery.trim() && suggestions.length > 0 && (
              <ul style={s.suggestions}>
                {suggestions.map(v => (
                  <li key={v} style={s.suggItem} onMouseDown={() => addCustomVerb(v)}>{v}</li>
                ))}
              </ul>
            )}
            {customVerbs.length > 0 && (
              <div style={{ marginTop: '0.5rem', display: 'flex', flexWrap: 'wrap', gap: '0.4rem' }}>
                {customVerbs.map(v => (
                  <span key={v} style={s.verbTag}>
                    {v} <button style={s.removeBtn} onClick={() => setCustomVerbs(customVerbs.filter(x => x !== v))}>×</button>
                  </span>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      <div style={s.field}>
        <label style={s.label}>Subjects</label>
        <div style={s.chips}>
          {PERSONS.map(p => (
            <button key={p} style={subjects.includes(p) ? {...s.chip,...s.chipOn} : s.chip} onClick={() => toggleSubject(p)}>
              {labels[p] || p}
            </button>
          ))}
        </div>
        <button style={s.textBtn} onClick={() => setSubjects([...PERSONS])}>Select all</button>
      </div>

      <div style={s.field}>
        <label style={s.label}>Tenses</label>
        <div style={s.chips}>
          {availTenses.map(t => {
            const key = `${t.mood}||${t.tense}`
            return (
              <button key={key} style={selTenses.includes(key) ? {...s.chip,...s.chipOn} : s.chip} onClick={() => toggleTense(key)}>
                {displayTenseName(t.mood, t.tense)}
              </button>
            )
          })}
        </div>
      </div>

      {error && <p style={s.error}>{error}</p>}
      <button style={s.startBtn} onClick={handleStart} disabled={loading}>
        {loading ? 'Loading…' : 'Start exercise →'}
      </button>
    </div>
  )
}

// ── Exercise screen ───────────────────────────────────────────────────────────
function Exercise({ verbTables, subjects, tenseFilters, language, onReset }) {
  const labels = PERSON_LABELS[language] || {}

  const cells = useMemo(() => {
    const list = []
    const tenseKeys = new Set(tenseFilters.map(t => `${t.mood.toLowerCase()}||${t.tense.toLowerCase()}`))
    for (const vt of verbTables) {
      for (const [mood, tenses] of Object.entries(vt.table)) {
        for (const [tense, forms] of Object.entries(tenses)) {
          if (!tenseKeys.has(`${mood.toLowerCase()}||${tense.toLowerCase()}`)) continue
          for (const { person, form, alternates = [] } of forms) {
            if (!subjects.includes(person)) continue
            list.push({ verb: vt.infinitive, mood, tense, person, correct: form, alternates })
          }
        }
      }
    }
    return list
  }, [verbTables, subjects, tenseFilters])

  const [answers, setAnswers]     = useState({})
  const [submitted, setSubmitted] = useState(false)
  const [results, setResults]     = useState({})

  const key = (c) => `${c.verb}||${c.mood}||${c.tense}||${c.person}`

  function submit() {
    const res = {}
    cells.forEach(c => {
      res[key(c)] = isFormCorrect(answers[key(c)] || '', c.correct, c.alternates)
    })
    setResults(res)
    setSubmitted(true)
  }

  const verbs = [...new Set(cells.map(c => c.verb))]

  // Sort tense columns by language-specific order
  const tenseCols = useMemo(() => {
    const seen = new Map()
    for (const c of cells) {
      const k = `${c.mood}||${c.tense}`
      if (!seen.has(k)) seen.set(k, { mood: c.mood, tense: c.tense })
    }
    return sortTenses(language, [...seen.values()])
  }, [cells, language])

  const score = submitted ? Object.values(results).filter(Boolean).length : 0

  return (
    <div>
      {submitted && (
        <div style={{ ...s.banner, background: score === cells.length ? '#d1fae5' : '#fef3c7' }}>
          {score}/{cells.length} correct
          <button style={s.resetBtn} onClick={onReset}>Try again</button>
        </div>
      )}

      {!submitted && <CharPicker language={language} style={s.charPicker} />}

      {verbs.map(verb => {
        // Sort persons in canonical order
        const verbPersonSet = new Set(cells.filter(c => c.verb === verb).map(c => c.person))
        const verbPersons = PERSONS.filter(p => verbPersonSet.has(p))
        return (
          <div key={verb} style={s.verbBlock}>
            <h4 style={s.verbTitle}>{verb}</h4>
            <div style={{ overflowX: 'auto' }}>
              <table style={s.table}>
                <thead>
                  <tr>
                    <th style={s.th}></th>
                    {tenseCols.map(tc => (
                      <th key={`${tc.mood}||${tc.tense}`} style={s.th}>
                        {displayTenseName(tc.mood, tc.tense)}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {verbPersons.map(person => (
                    <tr key={person}>
                      <td style={s.personTd}>{labels[person] || person}</td>
                      {tenseCols.map(tc => {
                        const cell = cells.find(c => c.verb === verb && c.mood === tc.mood && c.tense === tc.tense && c.person === person)
                        if (!cell) return <td key={`${tc.mood}||${tc.tense}`} style={s.td}>—</td>
                        const k = key(cell)
                        const correct = results[k]
                        return (
                          <td key={k} style={{
                            ...s.td,
                            background: submitted ? (correct ? '#d1fae5' : '#fee2e2') : undefined,
                          }}>
                            {submitted ? (
                              <span>
                                {answers[k] || '—'}
                                {!correct && (
                                  <span style={s.correction}>
                                    {' → '}{[cell.correct, ...cell.alternates].join(' / ')}
                                  </span>
                                )}
                              </span>
                            ) : (
                              <input
                                style={s.cellInput}
                                value={answers[k] || ''}
                                onChange={e => setAnswers({ ...answers, [k]: e.target.value })}
                                autoComplete="off"
                              />
                            )}
                          </td>
                        )
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )
      })}

      {!submitted && (
        <button style={s.startBtn} onClick={submit}>Check answers</button>
      )}
    </div>
  )
}

export default function VerbTableExercise({ language, onBack }) {
  const [phase, setPhase] = useState('setup')
  const [exerciseData, setExerciseData] = useState(null)

  function handleStart(data) { setExerciseData(data); setPhase('exercise') }
  function handleReset()     { setPhase('setup') }

  return (
    <div>
      <button style={s.backLink} onClick={onBack}>← Back</button>
      {phase === 'setup'    && <Setup language={language} onStart={handleStart} />}
      {phase === 'exercise' && <Exercise {...exerciseData} onReset={handleReset} />}
    </div>
  )
}

const s = {
  sectionTitle: { fontSize: '1.1rem', fontWeight: 700, marginBottom: '1.25rem' },
  field: { marginBottom: '1.25rem' },
  label: { display: 'block', fontWeight: 600, fontSize: '0.85rem', textTransform: 'uppercase', letterSpacing: '0.05em', color: '#555', marginBottom: '0.5rem' },
  chips: { display: 'flex', flexWrap: 'wrap', gap: '0.4rem' },
  chip: { padding: '0.35rem 0.85rem', borderRadius: 20, border: '2px solid #ddd', background: '#fff', cursor: 'pointer', fontSize: '0.88rem' },
  chipOn: { borderColor: '#4f46e5', background: '#4f46e5', color: '#fff' },
  hint: { fontSize: '0.82rem', color: '#6b7280', margin: '0 0 0.35rem' },
  input: { width: '100%', padding: '0.5rem 0.75rem', border: '2px solid #d1d5db', borderRadius: 8, fontSize: '0.95rem', boxSizing: 'border-box' },
  suggestions: { position: 'absolute', top: '100%', left: 0, right: 0, background: '#fff', border: '1px solid #d1d5db', borderRadius: 8, listStyle: 'none', margin: 0, padding: 0, zIndex: 10, boxShadow: '0 4px 12px rgba(0,0,0,0.1)', maxHeight: 200, overflowY: 'auto' },
  suggItem: { padding: '0.45rem 0.75rem', cursor: 'pointer', fontSize: '0.9rem' },
  verbTag: { background: '#e0e7ff', color: '#3730a3', padding: '0.2rem 0.6rem', borderRadius: 12, fontSize: '0.85rem', display: 'inline-flex', alignItems: 'center', gap: '0.3rem' },
  removeBtn: { background: 'none', border: 'none', cursor: 'pointer', color: '#6366f1', fontWeight: 700, padding: 0 },
  textBtn: { background: 'none', border: 'none', color: '#4f46e5', cursor: 'pointer', fontSize: '0.82rem', padding: '0.2rem 0', marginTop: '0.35rem' },
  error: { color: '#dc2626', fontSize: '0.9rem' },
  startBtn: { marginTop: '1rem', padding: '0.7rem 1.75rem', background: '#4f46e5', color: '#fff', border: 'none', borderRadius: 8, fontWeight: 600, cursor: 'pointer', fontSize: '0.95rem' },
  backLink: { background: 'none', border: 'none', color: '#4f46e5', cursor: 'pointer', fontSize: '0.9rem', padding: 0, marginBottom: '1.25rem' },
  charPicker: { position: 'sticky', top: 0, zIndex: 5, boxShadow: '0 2px 6px rgba(0,0,0,0.06)' },
  banner: { padding: '0.75rem 1rem', borderRadius: 8, marginBottom: '1rem', fontWeight: 600, display: 'flex', alignItems: 'center', justifyContent: 'space-between' },
  resetBtn: { background: '#4f46e5', color: '#fff', border: 'none', borderRadius: 6, padding: '0.3rem 0.85rem', cursor: 'pointer', fontSize: '0.85rem' },
  verbBlock: { marginBottom: '2rem' },
  verbTitle: { fontSize: '1.1rem', fontWeight: 700, color: '#1e1b4b', marginBottom: '0.5rem' },
  table: { borderCollapse: 'collapse', width: '100%' },
  th: { background: '#f3f4f6', padding: '0.5rem 0.75rem', fontSize: '0.8rem', fontWeight: 600, color: '#374151', textAlign: 'left', border: '1px solid #e5e7eb', whiteSpace: 'nowrap' },
  td: { padding: '0.4rem 0.5rem', border: '1px solid #e5e7eb', verticalAlign: 'middle' },
  personTd: { padding: '0.4rem 0.75rem', border: '1px solid #e5e7eb', fontWeight: 600, fontSize: '0.85rem', color: '#6b7280', whiteSpace: 'nowrap', background: '#f9fafb' },
  cellInput: { width: '100%', border: '1px solid #d1d5db', borderRadius: 5, padding: '0.3rem 0.45rem', fontSize: '0.9rem', minWidth: 80 },
  correction: { color: '#16a34a', fontWeight: 600, fontSize: '0.85rem' },
}
