import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import CharPicker from '../components/conjugation/CharPicker'
import MistakeExplanation from '../components/MistakeExplanation'
import SessionSummary from '../components/SessionSummary'
import SpeakButton from '../components/SpeakButton'
import StatusBadge from '../components/StatusBadge'
import { PERSON_LABELS, tenseWithMood } from '../utils/conjugationUtils'
import { checkUpLabel } from '../utils/reviewStatus'
import { color, ui } from '../theme'

const DRILL_LENGTH = 10

// Focused review: what's due (things that need work, then check-ups), one
// prompt at a time, graded server-side against verb_conjugations. With
// ?verb=&mood=&tense= (from "My mistakes") it drills that one verb+tense.
export default function Review() {
  const { language } = useParams()
  const [params] = useSearchParams()
  const navigate = useNavigate()
  // Bumping the round remounts the drill, which fetches a fresh set of prompts
  const [round, setRound] = useState(0)
  const cap = str => str.charAt(0).toUpperCase() + str.slice(1)

  const [verb, mood, tense] = ['verb', 'mood', 'tense'].map(k => params.get(k))
  const only = verb && mood && tense ? { verb_infinitive: verb, mood, tense } : null

  return (
    <div style={s.page}>
      {only
        ? <button style={s.back} onClick={() => navigate(`/progress?view=mistakes&language=${language}`)}>← My mistakes</button>
        : <button style={s.back} onClick={() => navigate(`/practice/${language}`)}>← Practice</button>}
      <h1 style={s.title}>Review — {cap(language)}</h1>
      <Drill
        key={`${language}-${verb}-${mood}-${tense}-${round}`}
        language={language}
        only={only}
        onRestart={() => setRound(r => r + 1)}
      />
    </div>
  )
}

function Drill({ language, only, onRestart }) {
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
    api.getDrill(language, DRILL_LENGTH, only)
      .then(setPrompts)
      .catch(e => { setLoadError(e.message); setPrompts([]) })
  }, [language]) // eslint-disable-line react-hooks/exhaustive-deps -- `only` is fixed for this mount (keyed)

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
        <p style={s.emptyTitle}>Nothing to review right now</p>
        <p style={s.muted}>Anything you get wrong comes back here, and so does each check-up once it's due.</p>
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
      >
        <StatusRecap language={language} log={log} />
      </SessionSummary>
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
              <SpeakButton text={result.expected} language={language} />
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

// Where each drilled verb+tense stands now: the status after its last answer
// (needs work / getting there + next check-up / fixed). Things never got wrong
// have no status and aren't listed.
function StatusRecap({ language, log }) {
  const latest = new Map()
  for (const { prompt, result } of log) {
    latest.set(`${prompt.verb_infinitive}|${prompt.mood}|${prompt.tense}`, { prompt, result })
  }
  const rows = [...latest.entries()].filter(([, { result }]) => result.status)
  if (!rows.length) return null

  return (
    <section style={s.recap} aria-labelledby="where-you-stand">
      <h2 id="where-you-stand" style={s.recapTitle}>Where you stand</h2>
      <ul style={s.recapList}>
        {rows.map(([key, { prompt, result }]) => (
          <li key={key} style={s.recapItem}>
            <span style={s.recapWhat}>
              <strong>{prompt.verb_infinitive}</strong> · {tenseWithMood(language, prompt.mood, prompt.tense)}
            </span>
            <span style={s.recapState}>
              {result.status === 'getting_there' && result.due_at && <span style={s.checkUp}>{checkUpLabel(result.due_at)}</span>}
              <StatusBadge status={result.status} />
            </span>
          </li>
        ))}
      </ul>
    </section>
  )
}

// Non-personal forms (gerund, infinitive…) are stored with person "—"
function personLabel(language, person) {
  if (person === '—') return ''
  return PERSON_LABELS[language]?.[person] ?? person
}

const s = {
  page: { ...ui.page, maxWidth: 560 },
  back: ui.back,
  title: ui.h1,
  card: ui.panel,
  muted: { color: '#6b7280', margin: '0 0 1rem' },
  error: { color: '#b91c1c', margin: '0.5rem 0' },
  emptyTitle: { fontWeight: 700, color: '#1e1b4b', margin: '0 0 0.4rem' },
  progress: { fontSize: '0.8rem', color: '#9ca3af', margin: '0 0 0.75rem' },
  verb: { fontSize: '1.9rem', fontWeight: 800, color: '#1e1b4b', margin: 0 },
  tense: { color: '#4f46e5', fontWeight: 600, margin: '0.2rem 0 1.25rem' },
  answerRow: { display: 'flex', alignItems: 'center', gap: '0.6rem', marginBottom: '0.75rem' },
  person: { fontWeight: 600, color: '#374151', minWidth: '4.5rem' },
  input: { flex: 1, minWidth: 0, padding: '0.6rem 0.75rem', border: '1px solid #d1d5db', borderRadius: 8, fontSize: '1.05rem', fontFamily: 'inherit' },
  primary: ui.primary,
  secondary: ui.secondary,
  feedbackRow: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '1rem', flexWrap: 'wrap' },
  recap: { margin: '0.75rem 0 1rem' },
  recapTitle: { fontSize: '0.95rem', fontWeight: 700, color: color.ink, margin: '0 0 0.35rem' },
  recapList: { listStyle: 'none', padding: 0, margin: 0 },
  recapItem: { display: 'flex', alignItems: 'baseline', flexWrap: 'wrap', gap: '0.25rem 0.75rem', padding: '0.35rem 0', borderBottom: '1px solid #eceef1', fontSize: '0.9rem' },
  recapWhat: { color: color.body, flex: '1 1 12rem', minWidth: 0 },
  recapState: { display: 'flex', alignItems: 'baseline', gap: '0.5rem', marginLeft: 'auto' },
  checkUp: { color: color.muted, fontSize: '0.8rem' },
}

const FEEDBACK_STYLE = {
  correct: { color: '#15803d', fontWeight: 600, margin: 0 },
  almost: { color: '#92400e', margin: 0 },
  wrong: { color: '#b91c1c', margin: 0 },
}
