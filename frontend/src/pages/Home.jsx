import { useState, useEffect } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { api } from '../api'

const LANGUAGES = ['french', 'spanish', 'english']
const EXERCISE_TYPES = ['conjugation', 'grammar', 'reading']
const DIFFICULTIES = [
  { value: 1, label: 'A1 — Beginner' },
  { value: 2, label: 'A2 — Elementary' },
  { value: 3, label: 'B1 — Intermediate' },
  { value: 4, label: 'B2 — Upper Intermediate' },
  { value: 5, label: 'C1 — Advanced' },
]
const COUNTS = [1, 5, 10, 20]

export default function Home() {
  const navigate = useNavigate()
  const [language, setLanguage] = useState('french')
  const [type, setType] = useState('conjugation')
  const [difficulty, setDifficulty] = useState(2)
  const [count, setCount] = useState(5)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [stats, setStats] = useState(null)

  useEffect(() => {
    api.getProgress(1).then(setStats).catch(() => {})
  }, [])

  async function startExercise() {
    setError(null)
    setLoading(true)
    try {
      const exercise = await api.generateExercise(type, language, difficulty)
      navigate('/exercise', {
        state: { exercise, settings: { type, language, difficulty }, remaining: count - 1, total: count },
      })
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={styles.page}>
      <h1 style={styles.title}>Language Practice</h1>

      <Link to="/conjugation" style={styles.conjugationLink}>
        📚 Conjugation — Lookup, Learn &amp; Practice
      </Link>

      <div style={styles.card}>
        <label style={styles.label}>Language</label>
        <div style={styles.group}>
          {LANGUAGES.map((l) => (
            <button
              key={l}
              style={language === l ? { ...styles.chip, ...styles.chipActive } : styles.chip}
              onClick={() => setLanguage(l)}
            >
              {l.charAt(0).toUpperCase() + l.slice(1)}
            </button>
          ))}
        </div>

        <label style={styles.label}>Exercise type</label>
        <div style={styles.group}>
          {EXERCISE_TYPES.map((t) => (
            <button
              key={t}
              style={type === t ? { ...styles.chip, ...styles.chipActive } : styles.chip}
              onClick={() => setType(t)}
            >
              {t.charAt(0).toUpperCase() + t.slice(1)}
            </button>
          ))}
        </div>

        <label style={styles.label}>Difficulty</label>
        <select
          style={styles.select}
          value={difficulty}
          onChange={(e) => setDifficulty(Number(e.target.value))}
        >
          {DIFFICULTIES.map((d) => (
            <option key={d.value} value={d.value}>{d.label}</option>
          ))}
        </select>

        <label style={styles.label}>Number of exercises</label>
        <div style={styles.group}>
          {COUNTS.map((c) => (
            <button
              key={c}
              style={count === c ? { ...styles.chip, ...styles.chipActive } : styles.chip}
              onClick={() => setCount(c)}
            >
              {c}
            </button>
          ))}
        </div>

        {error && <p style={styles.error}>{error}</p>}

        <button style={styles.startBtn} onClick={startExercise} disabled={loading}>
          {loading ? 'Generating exercise...' : 'Start'}
        </button>
      </div>

      {stats && stats.total > 0 && (
        <div style={styles.card}>
          <h2 style={styles.subtitle}>Your progress</h2>
          <p>Total exercises: <strong>{stats.total}</strong> &nbsp;|&nbsp; Accuracy: <strong>{stats.accuracy}%</strong></p>
          {Object.keys(stats.by_language).length > 0 && (
            <div>
              <p style={styles.statLabel}>By language:</p>
              <div style={styles.group}>
                {Object.entries(stats.by_language).map(([lang, s]) => (
                  <span key={lang} style={styles.statBadge}>
                    {lang}: {s.accuracy}% ({s.correct}/{s.total})
                  </span>
                ))}
              </div>
            </div>
          )}
          {Object.keys(stats.by_type).length > 0 && (
            <div>
              <p style={styles.statLabel}>By type:</p>
              <div style={styles.group}>
                {Object.entries(stats.by_type).map(([t, s]) => (
                  <span key={t} style={styles.statBadge}>
                    {t}: {s.accuracy}% ({s.correct}/{s.total})
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

const styles = {
  page: { maxWidth: 640, margin: '0 auto', padding: '2rem 1rem', fontFamily: 'system-ui, sans-serif' },
  title: { fontSize: '2rem', marginBottom: '1.5rem', textAlign: 'center' },
  subtitle: { fontSize: '1.1rem', marginBottom: '0.75rem' },
  card: { background: '#f8f9fa', borderRadius: 12, padding: '1.5rem', marginBottom: '1.5rem' },
  label: { display: 'block', fontWeight: 600, marginBottom: '0.5rem', marginTop: '1rem', fontSize: '0.9rem', textTransform: 'uppercase', letterSpacing: '0.05em', color: '#555' },
  group: { display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginBottom: '0.5rem' },
  chip: { padding: '0.4rem 1rem', borderRadius: 20, border: '2px solid #ddd', background: 'white', cursor: 'pointer', fontSize: '0.95rem' },
  chipActive: { borderColor: '#4f46e5', background: '#4f46e5', color: 'white' },
  select: { width: '100%', padding: '0.5rem', borderRadius: 8, border: '2px solid #ddd', fontSize: '0.95rem', marginBottom: '0.5rem' },
  startBtn: { marginTop: '1.5rem', width: '100%', padding: '0.75rem', borderRadius: 8, background: '#4f46e5', color: 'white', border: 'none', fontSize: '1rem', fontWeight: 600, cursor: 'pointer' },
  error: { color: '#dc2626', marginTop: '0.5rem', fontSize: '0.9rem' },
  statLabel: { fontWeight: 600, fontSize: '0.85rem', color: '#555', margin: '0.5rem 0 0.25rem' },
  statBadge: { background: '#e0e7ff', color: '#3730a3', padding: '0.25rem 0.75rem', borderRadius: 12, fontSize: '0.85rem' },
  conjugationLink: { display: 'block', background: '#4f46e5', color: 'white', borderRadius: 10, padding: '0.85rem 1.25rem', marginBottom: '1.25rem', textDecoration: 'none', fontWeight: 600, fontSize: '1rem', textAlign: 'center' },
}
