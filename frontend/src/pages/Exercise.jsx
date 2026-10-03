import { useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { api } from '../api'
import FeedbackPanel from '../components/FeedbackPanel'
import CharPicker from '../components/conjugation/CharPicker'
import SessionSummary from '../components/SessionSummary'
import ClickableText from '../components/reading/ClickableText'
import { ui } from '../theme'

// "Next exercise" navigates to this same route, so React would keep the previous
// exercise's answer and result; keying by exercise id starts each one fresh.
export default function Exercise() {
  const { state } = useLocation()
  return <ExerciseRun key={state?.exercise?.id} />
}

function ExerciseRun() {
  const { state } = useLocation()
  const navigate = useNavigate()
  const exercise = state?.exercise
  const settings = state?.settings
  const remaining = state?.remaining ?? 0
  const total = state?.total ?? 1
  const log = state?.log ?? []  // earlier answers in this session, for the end summary

  const [answer, setAnswer] = useState('')
  const [result, setResult] = useState(null)
  const [entry, setEntry] = useState(null)
  const [finished, setFinished] = useState(false)
  const [loading, setLoading] = useState(false)
  const [nextLoading, setNextLoading] = useState(false)
  const [error, setError] = useState(null)

  if (!exercise) {
    navigate('/')
    return null
  }

  const { type, language, content } = exercise
  const current = total - remaining
  const isLastExercise = remaining === 0

  async function submitAnswer() {
    if (!answer.trim()) return
    setLoading(true)
    setError(null)
    try {
      const res = await api.checkAnswer(exercise.id, answer.trim())
      setResult(res)
      setEntry({
        label: summaryLabel(type, content),
        answer: answer.trim(),
        expected: res.correct_answer,
        result: res.is_correct ? 'correct' : res.almost ? 'almost' : 'wrong',
      })
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  const sessionLog = entry ? [...log, entry] : log

  async function goNext() {
    if (isLastExercise) {
      setFinished(true)
      return
    }
    setNextLoading(true)
    try {
      const next = await api.generateExercise(settings.type, settings.language, settings.difficulty)
      navigate('/exercise', {
        state: { exercise: next, settings, remaining: remaining - 1, total, log: sessionLog },
      })
    } catch (e) {
      setError(e.message)
      setNextLoading(false)
    }
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !result) submitAnswer()
  }

  if (finished) {
    return (
      <div style={styles.page}>
        {/* Old-flow answers carry no DB tense, so they don't feed the review drill */}
        <SessionSummary language={language} results={sessionLog} showReviewLink={false} />
      </div>
    )
  }

  return (
    <div style={styles.page}>
      <div style={styles.topRow}>
        <button style={styles.back} onClick={() => navigate(settings?.language ? `/practice/${settings.language}` : '/')}>← Back</button>
        {total > 1 && <span style={styles.progress}>{current} / {total}</span>}
      </div>

      <div style={styles.meta}>
        <span style={styles.badge}>{language}</span>
        <span style={styles.badge}>{type}</span>
      </div>

      <div style={styles.card}>
        <ExerciseBody type={type} content={content} language={language} />

        {!result && (
          <div>
          <div style={styles.inputRow}>
            <input
              style={styles.input}
              value={answer}
              onChange={(e) => setAnswer(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={inputPlaceholder(type)}
              autoFocus
              disabled={loading}
            />
            <button style={styles.submitBtn} onClick={submitAnswer} disabled={loading || !answer.trim()}>
              {loading ? '...' : 'Check'}
            </button>
          </div>
            <CharPicker language={language} style={{ marginTop: '0.5rem' }} />
          </div>
        )}

        {error && <p style={styles.error}>{error}</p>}
        <FeedbackPanel result={result} />

        {result && (
          <button style={styles.nextBtn} onClick={goNext} disabled={nextLoading}>
            {nextLoading ? 'Loading...' : isLastExercise ? 'Finish' : 'Next exercise →'}
          </button>
        )}
      </div>
    </div>
  )
}

function ExerciseBody({ type, content, language }) {
  if (type === 'conjugation') {
    return (
      <div>
        <p style={styles.prompt}>{content.sentence}</p>
        <p style={styles.hint}>Infinitive: <em>{content.verb_infinitive}</em> &nbsp;|&nbsp; Tense: <em>{content.tense}</em></p>
      </div>
    )
  }
  if (type === 'grammar') {
    return (
      <div>
        <p style={styles.instruct}>Find and correct the grammar error in this sentence:</p>
        <p style={styles.prompt}>{content.sentence_with_error}</p>
        <p style={styles.hint}>Type the full corrected sentence.</p>
      </div>
    )
  }
  if (type === 'reading') {
    const q = content.questions?.[0]
    return (
      <div>
        <p style={styles.tip}>Tip: click any word to see what it means and save it.</p>
        <ClickableText text={content.passage} language={language} style={styles.passage} />
        {q && <p style={styles.prompt}>{q.question}</p>}
      </div>
    )
  }
  return null
}

function summaryLabel(type, content) {
  const text = type === 'conjugation' ? `${content.verb_infinitive} · ${content.tense}`
    : type === 'grammar' ? content.sentence_with_error
    : content.questions?.[0]?.question ?? 'Reading'
  return text.length > 60 ? `${text.slice(0, 57)}…` : text
}

function inputPlaceholder(type) {
  if (type === 'conjugation') return 'Type the conjugated verb...'
  if (type === 'grammar') return 'Type the corrected sentence...'
  return 'Type your answer...'
}

const styles = {
  page: { ...ui.page, maxWidth: 680 },
  topRow: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' },
  back: ui.back,
  progress: { fontSize: '0.9rem', fontWeight: 600, color: '#6b7280' },
  meta: { display: 'flex', gap: '0.5rem', marginBottom: '1rem', marginTop: 0 },
  badge: { background: '#e0e7ff', color: '#3730a3', padding: '0.2rem 0.75rem', borderRadius: 12, fontSize: '0.8rem', fontWeight: 600, textTransform: 'capitalize' },
  card: ui.panel,
  instruct: { color: '#555', marginBottom: '0.75rem', fontSize: '0.95rem' },
  prompt: { fontSize: '1.25rem', fontWeight: 500, lineHeight: 1.6, marginBottom: '0.5rem' },
  tip: { fontSize: '0.8rem', color: '#9ca3af', margin: '0 0 0.4rem' },
  passage: { fontSize: '1rem', lineHeight: 1.8, background: 'white', borderRadius: 8, padding: '1rem', marginBottom: '1rem', border: '1px solid #e5e7eb' },
  hint: { fontSize: '0.85rem', color: '#6b7280', marginBottom: '1rem' },
  inputRow: { display: 'flex', gap: '0.5rem', marginTop: '1rem' },
  input: { flex: 1, padding: '0.6rem 0.9rem', borderRadius: 8, border: '2px solid #ddd', fontSize: '1rem', outline: 'none' },
  submitBtn: { padding: '0.6rem 1.25rem', borderRadius: 8, background: '#4f46e5', color: 'white', border: 'none', fontWeight: 600, cursor: 'pointer', fontSize: '1rem' },
  nextBtn: { ...ui.primary, marginTop: '1.25rem', width: '100%', padding: '0.7rem', fontSize: '1rem' },
  error: { color: '#dc2626', fontSize: '0.9rem', marginTop: '0.5rem' },
}
