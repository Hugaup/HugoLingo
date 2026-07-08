import { useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { api } from '../api'
import FeedbackPanel from '../components/FeedbackPanel'
import CharPicker from '../components/conjugation/CharPicker'

export default function Exercise() {
  const { state } = useLocation()
  const navigate = useNavigate()
  const exercise = state?.exercise
  const settings = state?.settings
  const remaining = state?.remaining ?? 0
  const total = state?.total ?? 1

  const [answer, setAnswer] = useState('')
  const [result, setResult] = useState(null)
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
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  async function goNext() {
    if (isLastExercise) {
      navigate(settings?.language ? `/practice/${settings.language}` : '/')
      return
    }
    setNextLoading(true)
    try {
      const next = await api.generateExercise(settings.type, settings.language, settings.difficulty)
      navigate('/exercise', {
        state: { exercise: next, settings, remaining: remaining - 1, total },
      })
    } catch (e) {
      setError(e.message)
      setNextLoading(false)
    }
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !result) submitAnswer()
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
        <ExerciseBody type={type} content={content} />

        {!result && (
          <div>
            <CharPicker language={language} style={{ marginBottom: '0.5rem' }} />
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

function ExerciseBody({ type, content }) {
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
        <p style={styles.passage}>{content.passage}</p>
        {q && <p style={styles.prompt}>{q.question}</p>}
      </div>
    )
  }
  return null
}

function inputPlaceholder(type) {
  if (type === 'conjugation') return 'Type the conjugated verb...'
  if (type === 'grammar') return 'Type the corrected sentence...'
  return 'Type your answer...'
}

const styles = {
  page: { maxWidth: 680, margin: '0 auto', padding: '2rem 1rem', fontFamily: 'system-ui, sans-serif' },
  topRow: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' },
  back: { background: 'none', border: 'none', color: '#4f46e5', cursor: 'pointer', fontSize: '0.95rem', padding: 0 },
  progress: { fontSize: '0.9rem', fontWeight: 600, color: '#6b7280' },
  meta: { display: 'flex', gap: '0.5rem', marginBottom: '1rem', marginTop: 0 },
  badge: { background: '#e0e7ff', color: '#3730a3', padding: '0.2rem 0.75rem', borderRadius: 12, fontSize: '0.8rem', fontWeight: 600, textTransform: 'capitalize' },
  card: { background: '#f8f9fa', borderRadius: 12, padding: '1.5rem' },
  instruct: { color: '#555', marginBottom: '0.75rem', fontSize: '0.95rem' },
  prompt: { fontSize: '1.25rem', fontWeight: 500, lineHeight: 1.6, marginBottom: '0.5rem' },
  passage: { fontSize: '1rem', lineHeight: 1.8, background: 'white', borderRadius: 8, padding: '1rem', marginBottom: '1rem', border: '1px solid #e5e7eb' },
  hint: { fontSize: '0.85rem', color: '#6b7280', marginBottom: '1rem' },
  inputRow: { display: 'flex', gap: '0.5rem', marginTop: '1rem' },
  input: { flex: 1, padding: '0.6rem 0.9rem', borderRadius: 8, border: '2px solid #ddd', fontSize: '1rem', outline: 'none' },
  submitBtn: { padding: '0.6rem 1.25rem', borderRadius: 8, background: '#4f46e5', color: 'white', border: 'none', fontWeight: 600, cursor: 'pointer', fontSize: '1rem' },
  nextBtn: { marginTop: '1.25rem', width: '100%', padding: '0.7rem', borderRadius: 8, background: '#4f46e5', color: 'white', border: 'none', fontSize: '1rem', fontWeight: 600, cursor: 'pointer' },
  error: { color: '#dc2626', fontSize: '0.9rem', marginTop: '0.5rem' },
}
