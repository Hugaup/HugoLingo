import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth/AuthContext'
import { LEVELS as DIFFICULTIES } from '../constants'
import WorkOnThis from '../components/WorkOnThis'

const COUNTS = [1, 5, 10, 20]

const TYPE_CARDS = [
  {
    id: 'conjugation',
    icon: '🔤',
    title: 'Conjugation',
    desc: 'Master verb tables, tense rules, and sentence completion with AI feedback.',
  },
  {
    id: 'vocabulary',
    icon: '📚',
    title: 'Vocabulary',
    desc: 'Everyday words and phrases with flashcards, quizzes and spaced review.',
    // Its own page, like conjugation
    path: 'vocabulary',
  },
  {
    id: 'conversation',
    icon: '💬',
    title: 'Conversation',
    desc: 'Role-play everyday situations with the AI; your mistakes are corrected as you go.',
    path: 'conversation',
  },
  {
    id: 'grammar',
    icon: '✏️',
    title: 'Grammar',
    desc: 'Spot and fix errors in sentences to build your grammatical instincts.',
  },
  {
    id: 'reading',
    icon: '📖',
    title: 'Reading',
    desc: 'Read short passages and answer comprehension questions.',
  },
]

export default function Practice() {
  const { language } = useParams()
  const navigate = useNavigate()
  const { user } = useAuth()
  const [selectedType, setSelectedType] = useState(null)
  const [difficulty, setDifficulty]     = useState(user.level)
  const [count, setCount]               = useState(5)
  const [loading, setLoading]           = useState(false)
  const [error, setError]               = useState(null)

  async function startExercise() {
    setError(null); setLoading(true)
    try {
      const exercise = await api.generateExercise(selectedType, language, difficulty)
      navigate('/exercise', {
        state: { exercise, settings: { type: selectedType, language, difficulty }, remaining: count - 1, total: count },
      })
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  const cap = str => str.charAt(0).toUpperCase() + str.slice(1)

  return (
    <div style={s.page}>
      <button style={s.back} onClick={() => navigate('/')}>← Change language</button>
      <h1 style={s.title}>{cap(language)} Practice</h1>
      {selectedType === null && <WorkOnThis language={language} />}

      {selectedType === null ? (
        <div style={s.typeGrid}>
          {TYPE_CARDS.map(t => (
            <button
              key={t.id}
              style={s.typeCard}
              onClick={() =>
                t.id === 'conjugation' || t.path
                  ? navigate(`/practice/${language}/${t.path ?? 'conjugation'}`)
                  : setSelectedType(t.id)
              }
            >
              <span style={s.typeIcon}>{t.icon}</span>
              <span style={s.typeTitle}>{t.title}</span>
              <span style={s.typeDesc}>{t.desc}</span>
            </button>
          ))}
        </div>
      ) : (
        <div style={s.setupCard}>
          <button style={s.backSm} onClick={() => setSelectedType(null)}>← Back</button>
          <h2 style={s.setupTitle}>{cap(selectedType)}</h2>

          <label style={s.label}>Difficulty</label>
          <select style={s.select} value={difficulty} onChange={e => setDifficulty(Number(e.target.value))}>
            {DIFFICULTIES.map(d => <option key={d.value} value={d.value}>{d.label}</option>)}
          </select>

          <label style={s.label}>Number of exercises</label>
          <div style={s.chips}>
            {COUNTS.map(c => (
              <button
                key={c}
                style={c === count ? { ...s.chip, ...s.chipOn } : s.chip}
                onClick={() => setCount(c)}
              >
                {c}
              </button>
            ))}
          </div>

          {error && <p style={s.error}>{error}</p>}
          <button style={s.startBtn} onClick={startExercise} disabled={loading}>
            {loading ? 'Generating…' : 'Start →'}
          </button>
        </div>
      )}
    </div>
  )
}

const s = {
  page: { maxWidth: 700, margin: '0 auto', padding: '2rem 1.5rem', fontFamily: 'system-ui, sans-serif' },
  back: { background: 'none', border: 'none', color: '#4f46e5', cursor: 'pointer', fontSize: '0.9rem', padding: 0, marginBottom: '1rem', display: 'block' },
  title: { fontSize: '2rem', fontWeight: 800, color: '#1e1b4b', marginBottom: '1.75rem' },
  typeGrid: { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1rem' },
  typeCard: { display: 'flex', flexDirection: 'column', gap: '0.5rem', background: '#fff', border: '2px solid #e5e7eb', borderRadius: 14, padding: '1.75rem 1.5rem', cursor: 'pointer', textAlign: 'left', fontFamily: 'inherit', transition: 'border-color 0.15s' },
  typeIcon: { fontSize: '2rem' },
  typeTitle: { fontWeight: 700, fontSize: '1.1rem', color: '#1e1b4b' },
  typeDesc: { fontSize: '0.85rem', color: '#6b7280', lineHeight: 1.5 },
  setupCard: { background: '#f8f9fa', borderRadius: 12, padding: '1.5rem' },
  backSm: { background: 'none', border: 'none', color: '#4f46e5', cursor: 'pointer', fontSize: '0.9rem', padding: 0, marginBottom: '1rem', display: 'block' },
  setupTitle: { fontSize: '1.3rem', fontWeight: 700, marginBottom: '1rem', color: '#1e1b4b' },
  label: { display: 'block', fontWeight: 600, marginBottom: '0.5rem', marginTop: '1rem', fontSize: '0.85rem', textTransform: 'uppercase', letterSpacing: '0.05em', color: '#555' },
  select: { width: '100%', padding: '0.5rem', borderRadius: 8, border: '2px solid #ddd', fontSize: '0.95rem' },
  chips: { display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginBottom: '0.5rem' },
  chip: { padding: '0.4rem 1rem', borderRadius: 20, border: '2px solid #ddd', background: '#fff', cursor: 'pointer', fontSize: '0.9rem' },
  chipOn: { borderColor: '#4f46e5', background: '#4f46e5', color: '#fff' },
  startBtn: { marginTop: '1.5rem', width: '100%', padding: '0.75rem', borderRadius: 8, background: '#4f46e5', color: '#fff', border: 'none', fontSize: '1rem', fontWeight: 600, cursor: 'pointer' },
  error: { color: '#dc2626', fontSize: '0.9rem', marginTop: '0.5rem' },
}
