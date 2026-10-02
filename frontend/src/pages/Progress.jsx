import { useEffect, useState } from 'react'
import { api } from '../api'
import { useAuth } from '../auth/AuthContext'
import { LANGUAGES } from '../constants'
import WorkOnThis from '../components/WorkOnThis'
import ActivityChart from '../components/charts/ActivityChart'
import AccuracyGrid from '../components/charts/AccuracyGrid'

export default function Progress() {
  const { user } = useAuth()
  const [language, setLanguage] = useState(user.target_language || LANGUAGES[0].code)

  return (
    <div style={s.page}>
      <h1 style={s.title}>Your progress</h1>
      <div style={s.tabs} role="tablist" aria-label="Language">
        {LANGUAGES.map(l => (
          <button
            key={l.code}
            role="tab"
            aria-selected={l.code === language}
            style={l.code === language ? { ...s.chip, ...s.chipActive } : s.chip}
            onClick={() => setLanguage(l.code)}
          >
            {l.flag} {l.label}
          </button>
        ))}
      </div>
      <ProgressBody key={language} language={language} dailyGoal={user.daily_goal} />
    </div>
  )
}

function ProgressBody({ language, dailyGoal }) {
  const [stats, setStats] = useState(null)
  const [grid, setGrid]   = useState(null)
  const [vocab, setVocab] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    Promise.all([api.getStats(language), api.getGrid(language)])
      .then(([st, gr]) => { setStats(st); setGrid(gr) })
      .catch(e => setError(e.message))
    // Optional extra: the page still works if vocabulary can't be loaded
    api.getVocabOverview(language).then(setVocab).catch(() => {})
  }, [language])

  if (error) return <p style={s.error}>{error}</p>
  if (!stats) return <p style={s.muted}>Loading…</p>

  const goalShare = Math.min(1, stats.today_count / dailyGoal)

  return (
    <>
      <div style={s.tiles}>
        <Tile label="Answers" value={stats.total} />
        <Tile label="Accuracy" value={stats.total ? `${stats.accuracy}%` : '—'} />
        {vocab?.available && <Tile label="Words learned" value={`${vocab.learned} / ${vocab.total}`} />}
        <Tile label="Streak" value={`${stats.streak_days} ${stats.streak_days === 1 ? 'day' : 'days'}`} note="all languages" />
        <Tile label="Today" value={`${stats.today_count} / ${dailyGoal}`} note="all languages">
          <div
            style={s.meter}
            role="meter"
            aria-label="Daily goal"
            aria-valuemin={0}
            aria-valuemax={dailyGoal}
            aria-valuenow={Math.min(stats.today_count, dailyGoal)}
          >
            <div style={{ ...s.meterFill, width: `${goalShare * 100}%` }} />
          </div>
        </Tile>
      </div>

      <section style={s.section}>
        <h2 style={s.sectionTitle}>Answers, last 30 days</h2>
        <ActivityChart daily={stats.daily} />
      </section>

      <WorkOnThis language={language} limit={6} />

      <section style={s.section}>
        <h2 style={s.sectionTitle}>Verbs × tenses</h2>
        {grid.rows.length
          ? <AccuracyGrid language={language} grid={grid} />
          : <p style={s.muted}>Your accuracy for each verb and tense will appear here once you've practised.</p>}
      </section>
    </>
  )
}

function Tile({ label, value, note, children }) {
  return (
    <div style={s.tile}>
      <span style={s.tileLabel}>{label}</span>
      <span style={s.tileValue}>{value}</span>
      {children}
      {note && <span style={s.tileNote}>{note}</span>}
    </div>
  )
}

const s = {
  page: { maxWidth: 820, margin: '0 auto', padding: '2rem 1.5rem 3rem', fontFamily: 'system-ui, sans-serif' },
  title: { fontSize: '1.75rem', fontWeight: 800, color: '#1e1b4b', margin: '0 0 1rem' },
  tabs: { display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginBottom: '1.5rem' },
  chip: { padding: '0.4rem 0.9rem', borderRadius: 999, border: '1px solid #d1d5db', background: '#fff', cursor: 'pointer', fontSize: '0.9rem', fontFamily: 'inherit', color: '#374151' },
  chipActive: { border: '1px solid #4f46e5', background: '#4f46e5', color: '#fff' },
  tiles: { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: '0.75rem', marginBottom: '1.5rem' },
  tile: { display: 'flex', flexDirection: 'column', gap: '0.25rem', background: '#f8f9fa', borderRadius: 12, padding: '0.9rem 1rem' },
  tileLabel: { fontSize: '0.8rem', color: '#52514e' },
  tileValue: { fontSize: '1.6rem', fontWeight: 700, color: '#0b0b0b' },
  tileNote: { fontSize: '0.7rem', color: '#898781' },
  meter: { height: 6, borderRadius: 3, background: '#e0e7ff', overflow: 'hidden' },
  meterFill: { height: '100%', background: '#4f46e5', borderRadius: 3 },
  section: { background: '#f8f9fa', borderRadius: 12, padding: '1.25rem', marginBottom: '1.5rem' },
  sectionTitle: { fontSize: '1rem', fontWeight: 700, color: '#1e1b4b', margin: '0 0 1.25rem' },
  muted: { color: '#6b7280', margin: 0 },
  error: { color: '#b91c1c' },
}
