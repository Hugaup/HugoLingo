import { useState, useEffect } from 'react'
import { api } from '../../api'
import ChatPanel from './ChatPanel'
import { sortTenses, displayTenseName } from '../../utils/conjugationUtils'
import CharPicker from './CharPicker'

const SKIP_MOODS = ['infinitive', 'infinitivo', 'infinitif', 'gerundio', 'participo', 'participe']

// ── Setup ─────────────────────────────────────────────────────────────────────
function Setup({ language, onStart }) {
  const [count, setCount]           = useState(3)
  const [availTenses, setAvailTenses] = useState([])
  const [selTenses, setSelTenses]   = useState([])
  const [loading, setLoading]       = useState(false)
  const [error, setError]           = useState(null)

  useEffect(() => {
    api.getVerbTenses(language).then(data => {
      const meaningful = data.filter(t =>
        !SKIP_MOODS.some(skip => t.mood.toLowerCase().includes(skip))
      )
      setAvailTenses(sortTenses(language, meaningful))
      setSelTenses([])
    }).catch(() => {})
  }, [language])

  function tenseKey(t) { return `${t.mood}||${t.tense}` }

  function toggleTense(t) {
    const k = tenseKey(t)
    setSelTenses(prev => prev.includes(k) ? prev.filter(x => x !== k) : [...prev, k])
  }

  async function handleStart() {
    setError(null); setLoading(true)
    try {
      const tenses = selTenses.map(k => {
        const [mood, tense] = k.split('||')
        return { mood, tense }
      })
      const items = await api.generateSentences(language, tenses, count)
      onStart(items, language)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div>
      <h3 style={s.sectionTitle}>Sentence Completion — Setup</h3>

      <div style={s.field}>
        <label style={s.label}>Number of sentences</label>
        <div style={s.chips}>
          {[1,2,3,5,7,10].map(n => (
            <button key={n} style={n === count ? {...s.chip,...s.chipOn} : s.chip} onClick={() => setCount(n)}>{n}</button>
          ))}
        </div>
      </div>

      <div style={s.field}>
        <label style={s.label}>Tenses to be tested <span style={s.optional}>(default: all)</span></label>
        <div style={s.chips}>
          {availTenses.map(t => {
            const k = tenseKey(t)
            return (
              <button key={k} style={selTenses.includes(k) ? {...s.chip,...s.chipOn} : s.chip} onClick={() => toggleTense(t)}>
                {displayTenseName(t.mood, t.tense)}
              </button>
            )
          })}
        </div>
        {selTenses.length > 0 && (
          <button style={s.textBtn} onClick={() => setSelTenses([])}>Clear — use all tenses</button>
        )}
      </div>

      {error && <p style={s.error}>{error}</p>}
      <button style={s.startBtn} onClick={handleStart} disabled={loading}>
        {loading ? 'Generating sentences…' : 'Start →'}
      </button>
    </div>
  )
}

// ── Exercise ──────────────────────────────────────────────────────────────────
function Exercise({ items, language, onReset }) {
  const [idx, setIdx]               = useState(0)
  const [userForm, setUserForm]     = useState('')
  const [userTense, setUserTense]   = useState('')
  const [checking, setChecking]     = useState(false)
  const [result, setResult]         = useState(null)
  const [availTenses, setAvailTenses] = useState([])

  const item = items[idx]

  useEffect(() => {
    api.getVerbTenses(language).then(data => {
      const meaningful = data.filter(t =>
        !SKIP_MOODS.some(skip => t.mood.toLowerCase().includes(skip))
      )
      setAvailTenses(sortTenses(language, meaningful))
    }).catch(() => {})
  }, [language])

  async function handleCheck() {
    if (!userForm.trim() || !userTense) return
    setChecking(true)
    try {
      const [mood, tense] = userTense.split('||')
      const res = await api.checkSentence(item, userForm.trim(), mood, tense, language)
      setResult(res)
    } catch (e) {
      setResult({ form_correct: false, tense_correct: false, explanation: e.message })
    } finally {
      setChecking(false)
    }
  }

  function next() {
    setIdx(idx + 1)
    setUserForm(''); setUserTense(''); setResult(null)
  }

  const isLast = idx === items.length - 1

  const chatSystemPrompt = result
    ? `You are a language teacher helping a student understand ${language} conjugation.
The sentence was: "${item.sentence.replace('___', item.correct_form)}"
The verb is "${item.verb_infinitive}" conjugated as "${item.correct_form}" (${item.mood} — ${item.tense}, person ${item.person}).
The student answered: form="${userForm}", tense="${userTense}".
Answer any follow-up questions clearly with examples.`
    : null

  const chatInitial = result ? [{ role: 'assistant', content: result.explanation }] : []

  return (
    <div>
      <div style={s.progress}>{idx + 1} / {items.length}</div>

      <div style={s.sentenceCard}>
        <p style={s.sentence}>{item.sentence}</p>
        <p style={s.hint}>Subject: <strong>{item.subject_hint}</strong> · Verb: <em>{item.verb_infinitive}</em></p>
      </div>

      {!result ? (
        <div style={s.answerArea}>
          <div style={s.field}>
            <label style={s.label}>Your conjugated form</label>
            <input
              style={s.input}
              value={userForm}
              onChange={e => setUserForm(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleCheck()}
              placeholder="Type the conjugated verb…"
              autoFocus
            />
            <CharPicker language={language} style={{ marginTop: '0.4rem' }} />
          </div>
          <div style={s.field}>
            <label style={s.label}>Tense</label>
            <select style={s.select} value={userTense} onChange={e => setUserTense(e.target.value)}>
              <option value="">— Select tense —</option>
              {availTenses.map(t => {
                const k = `${t.mood}||${t.tense}`
                return (
                  <option key={k} value={k}>
                    {t.mood} — {displayTenseName(t.mood, t.tense)}
                  </option>
                )
              })}
            </select>
          </div>
          <button style={s.startBtn} onClick={handleCheck} disabled={checking || !userForm.trim() || !userTense}>
            {checking ? 'Checking…' : 'Check'}
          </button>
        </div>
      ) : (
        <div>
          <div style={{ ...s.resultBanner, background: (result.form_correct && result.tense_correct) ? '#d1fae5' : result.form_correct ? '#fef3c7' : '#fee2e2' }}>
            <span>{result.form_correct ? '✓ Form correct' : `✗ Form incorrect — correct: ${item.correct_form}`}</span>
            <span style={{ marginLeft: '1rem' }}>{result.tense_correct ? '✓ Tense correct' : `✗ Tense — correct: ${item.mood} — ${displayTenseName(item.mood, item.tense)}`}</span>
          </div>

          <div style={{ marginTop: '1rem' }}>
            <ChatPanel
              initialMessages={chatInitial}
              systemPrompt={chatSystemPrompt}
              placeholder="Ask a follow-up question about this conjugation…"
            />
          </div>

          <div style={{ marginTop: '1rem', display: 'flex', gap: '0.75rem' }}>
            {!isLast ? (
              <button style={s.startBtn} onClick={next}>Next sentence →</button>
            ) : (
              <button style={s.startBtn} onClick={onReset}>Finish — new exercise</button>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

export default function SentenceCompletion({ language, onBack }) {
  const [phase, setPhase]   = useState('setup')
  const [items, setItems]   = useState([])
  const [lang, setLang]     = useState(language)

  function handleStart(newItems, l) { setItems(newItems); setLang(l); setPhase('exercise') }
  function handleReset()            { setPhase('setup') }

  return (
    <div>
      <button style={s.backLink} onClick={onBack}>← Back</button>
      {phase === 'setup'    && <Setup language={language} onStart={handleStart} />}
      {phase === 'exercise' && <Exercise items={items} language={lang} onReset={handleReset} />}
    </div>
  )
}

const s = {
  sectionTitle: { fontSize: '1.1rem', fontWeight: 700, marginBottom: '1.25rem' },
  field: { marginBottom: '1.25rem' },
  label: { display: 'block', fontWeight: 600, fontSize: '0.85rem', textTransform: 'uppercase', letterSpacing: '0.05em', color: '#555', marginBottom: '0.5rem' },
  optional: { fontWeight: 400, fontSize: '0.8rem', color: '#9ca3af', textTransform: 'none' },
  chips: { display: 'flex', flexWrap: 'wrap', gap: '0.4rem' },
  chip: { padding: '0.35rem 0.85rem', borderRadius: 20, border: '2px solid #ddd', background: '#fff', cursor: 'pointer', fontSize: '0.85rem' },
  chipOn: { borderColor: '#4f46e5', background: '#4f46e5', color: '#fff' },
  textBtn: { background: 'none', border: 'none', color: '#4f46e5', cursor: 'pointer', fontSize: '0.82rem', padding: '0.2rem 0', marginTop: '0.35rem' },
  error: { color: '#dc2626', fontSize: '0.9rem' },
  startBtn: { padding: '0.7rem 1.75rem', background: '#4f46e5', color: '#fff', border: 'none', borderRadius: 8, fontWeight: 600, cursor: 'pointer', fontSize: '0.95rem' },
  backLink: { background: 'none', border: 'none', color: '#4f46e5', cursor: 'pointer', fontSize: '0.9rem', padding: 0, marginBottom: '1.25rem' },
  progress: { fontSize: '0.85rem', color: '#6b7280', marginBottom: '0.75rem', fontWeight: 600 },
  sentenceCard: { background: '#f8f9fa', borderRadius: 10, padding: '1.25rem', marginBottom: '1.25rem' },
  sentence: { fontSize: '1.15rem', margin: '0 0 0.5rem', lineHeight: 1.6 },
  hint: { margin: 0, fontSize: '0.88rem', color: '#6b7280' },
  answerArea: {},
  input: { width: '100%', padding: '0.6rem 0.85rem', border: '2px solid #d1d5db', borderRadius: 8, fontSize: '1rem', boxSizing: 'border-box' },
  select: { width: '100%', padding: '0.6rem 0.85rem', border: '2px solid #d1d5db', borderRadius: 8, fontSize: '0.95rem', background: '#fff' },
  resultBanner: { padding: '0.75rem 1rem', borderRadius: 8, fontSize: '0.9rem', fontWeight: 600, display: 'flex', flexWrap: 'wrap', gap: '0.5rem' },
}
