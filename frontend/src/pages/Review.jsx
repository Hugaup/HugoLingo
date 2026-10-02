import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api } from '../api'
import CharPicker from '../components/conjugation/CharPicker'
import MistakeExplanation from '../components/MistakeExplanation'
import SessionSummary from '../components/SessionSummary'
import { PERSON_LABELS, tenseWithMood } from '../utils/conjugationUtils'

const DRILL_LENGTH = 10

// Focused review: due spaced-repetition items and weak spots, one prompt at a
// time, graded server-side against verb_conjugations.
export default function Review() {
  const { language } = useParams()
  const navigate = useNavigate()
  // Bumping the round remounts the drill, which fetches a fresh set of prompts
  const [round, setRound] = useState(0)
  const cap = str => str.charAt(0).toUpperCase() + str.slice(1)

  return (
    <div style={s.page}>
      <button style={s.back} onClick={() => navigate(`/practice/${language}`)}>← Practice</button>
      <h1 style={s.title}>Review — {cap(language)}</h1>
      <Drill key={`${language}-${round}`} language={language} onRestart={() => setRound(r => r + 1)} />
    </div>
  )
}

function Drill({ language, onRestart }) {
  const navigate = useNavigate()
  const [prompts, setPrompts]   = useState(null)  // null while loading
  const [loadError, setLoadError] = useState(null)
  const [index, setIndex]       = useState(0)
  const [answer, setAnswer]     = useState('')
  const [result, setResult]     = useState(null)
  const [checking, setChecking] = useState(false)
  const [checkError, setCheckError] = useState(null)
  const [log, setLog]           = useState([])
  const inputRef = useRef(null)
  const nextRef  = useRef(null)

  useEffect(() => {
    api.getDrill(language, DRILL_LENGTH)
      .then(setPrompts)
      .catch(e => { setLoadError(e.message); setPrompts([]) })
  }, [language])

  // Keyboard flow: type → Enter checks → Enter again goes to the next prompt
  useEffect(() => {
    if (result) nextRef.current?.focus()
    else inputRef.current?.focus()
  }, [result, index, prompts])

  if (prompts === null) return <p style={s.muted}>Loading…</p>
  if (loadError) return <p style={s.error}>{loadError}</p>
  if (!prompts.length) {
    return (
      <div style={s.card}>
        <p style={s.emptyTitle}>Nothing to review yet</p>
        <p style={s.muted}>Practise some conjugations first — anything you get wrong will come back here.</p>
        <button style={s.primary} onClick={() => navigate(`/practice/${language}/conjugation`)}>Go to conjugation practice</button>
      </div>
    )
  }

  if (index >= prompts.length) {
    return (
      <SessionSummary
        language={language}
        results={log.map(({ prompt, answer, result }) => ({
          label: [prompt.verb_infinitive, tenseWithMood(language, prompt.mood, prompt.tense), personLabel(language, prompt.person)]
            .filter(Boolean).join(' · '),
          answer,
          expected: result.expected,
          result: result.result,
        }))}
        onRestart={onRestart}
        restartLabel="Review again"
        showReviewLink={false}
      />
    )
  }

  const prompt = prompts[index]
  const person = personLabel(language, prompt.person)

  async function check(e) {
    e.preventDefault()
    const given = answer.trim()
    if (!given || checking) return
    setChecking(true)
    setCheckError(null)
    try {
      const res = await api.checkDrill(language, prompt, given)
      setResult(res)
      setLog(l => [...l, { prompt, answer: given, result: res }])
    } catch (err) {
      setCheckError(err.message)
    } finally {
      setChecking(false)
    }
  }

  function next() {
    setIndex(i => i + 1)
    setAnswer('')
    setResult(null)
  }

  return (
    <div style={s.card}>
      <p style={s.progress}>{index + 1} / {prompts.length}</p>
      <p style={s.verb}>{prompt.verb_infinitive}</p>
      <p style={s.tense}>{tenseWithMood(language, prompt.mood, prompt.tense)}</p>

      <form style={s.answerRow} onSubmit={check}>
        <label htmlFor="drill-answer" style={s.person}>{person || 'Answer'}</label>
        <input
          id="drill-answer" ref={inputRef} style={s.input} autoComplete="off" autoCapitalize="off" spellCheck={false}
          value={answer} onChange={e => setAnswer(e.target.value)} disabled={!!result}
        />
        {!result && <button type="submit" style={s.primary} disabled={checking || !answer.trim()}>Check</button>}
      </form>
      {!result && <CharPicker language={language} />}
      {checkError && <p style={s.error}>{checkError}</p>}

      {result && (
        <>
          <div style={s.feedbackRow}>
            <p role="status" style={FEEDBACK_STYLE[result.result]}>
              {result.result === 'correct' && '✓ Correct'}
              {result.result === 'almost' && <>≈ Almost — check the accents: <strong>{result.expected}</strong></>}
              {result.result === 'wrong' && <>✗ Correct answer: <strong>{result.expected}</strong>
                {result.alternates.length > 0 && <> (also {result.alternates.join(', ')})</>}</>}
            </p>
            <button ref={nextRef} style={s.primary} onClick={next}>
              {index + 1 === prompts.length ? 'See results' : 'Next →'}
            </button>
          </div>
          {/* The almost-line already says it all; explain only real mistakes */}
          {result.result === 'wrong' && (
            <MistakeExplanation explanation={result.explanation} language={language} person={prompt.person} />
          )}
        </>
      )}
    </div>
  )
}

// Non-personal forms (gerund, infinitive…) are stored with person "—"
function personLabel(language, person) {
  if (person === '—') return ''
  return PERSON_LABELS[language]?.[person] ?? person
}

const s = {
  page: { maxWidth: 560, margin: '0 auto', padding: '2rem 1.5rem', fontFamily: 'system-ui, sans-serif' },
  back: { background: 'none', border: 'none', color: '#6b7280', cursor: 'pointer', padding: 0, fontSize: '0.9rem', fontFamily: 'inherit' },
  title: { fontSize: '1.6rem', fontWeight: 800, color: '#1e1b4b', margin: '0.75rem 0 1.25rem' },
  card: { background: '#f8f9fa', borderRadius: 12, padding: '1.5rem' },
  muted: { color: '#6b7280', margin: '0 0 1rem' },
  error: { color: '#b91c1c', margin: '0.5rem 0' },
  emptyTitle: { fontWeight: 700, color: '#1e1b4b', margin: '0 0 0.4rem' },
  progress: { fontSize: '0.8rem', color: '#9ca3af', margin: '0 0 0.75rem' },
  verb: { fontSize: '1.9rem', fontWeight: 800, color: '#1e1b4b', margin: 0 },
  tense: { color: '#4f46e5', fontWeight: 600, margin: '0.2rem 0 1.25rem' },
  answerRow: { display: 'flex', alignItems: 'center', gap: '0.6rem', marginBottom: '0.75rem' },
  person: { fontWeight: 600, color: '#374151', minWidth: '4.5rem' },
  input: { flex: 1, minWidth: 0, padding: '0.6rem 0.75rem', border: '1px solid #d1d5db', borderRadius: 8, fontSize: '1.05rem', fontFamily: 'inherit' },
  primary: { background: '#4f46e5', color: '#fff', border: 'none', borderRadius: 8, padding: '0.6rem 1.1rem', fontSize: '0.95rem', fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit', whiteSpace: 'nowrap' },
  secondary: { background: '#fff', color: '#374151', border: '1px solid #d1d5db', borderRadius: 8, padding: '0.6rem 1.1rem', fontSize: '0.95rem', cursor: 'pointer', fontFamily: 'inherit' },
  feedbackRow: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '1rem', flexWrap: 'wrap' },
}

const FEEDBACK_STYLE = {
  correct: { color: '#15803d', fontWeight: 600, margin: 0 },
  almost: { color: '#92400e', margin: 0 },
  wrong: { color: '#b91c1c', margin: 0 },
}
