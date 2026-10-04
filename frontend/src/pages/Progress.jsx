import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth/AuthContext'
import { LANGUAGES } from '../constants'
import MyMistakes from '../components/MyMistakes'
import WorkOnThis from '../components/WorkOnThis'
import ActivityChart from '../components/charts/ActivityChart'
import AccuracyGrid from '../components/charts/AccuracyGrid'
import { ui } from '../theme'

const VIEWS = [
  { code: 'overview', label: 'Overview' },
  { code: 'mistakes', label: 'My mistakes' },
]

// Language and view live in the URL (?language=&view=mistakes), so other pages
// can link straight to "My mistakes".
export default function Progress() {
  const { user } = useAuth()
  const [params, setParams] = useSearchParams()
  const asked = params.get('language')
  const language = LANGUAGES.some(l => l.code === asked) ? asked : (user.target_language || LANGUAGES[0].code)
  const view = params.get('view') === 'mistakes' ? 'mistakes' : 'overview'
  const go = (changes) => setParams({ language, view, ...changes }, { replace: true })
  const setLanguage = code => go({ language: code })

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
      <div style={s.views} role="tablist" aria-label="View">
        {VIEWS.map(v => (
          <button
            key={v.code}
            role="tab"
            aria-selected={v.code === view}
            style={v.code === view ? { ...s.view, ...s.viewOn } : s.view}
            onClick={() => go({ view: v.code })}
          >
            {v.label}
          </button>
        ))}
      </div>
      {view === 'mistakes'
        ? <MyMistakes key={language} language={language} />
        : <ProgressBody key={language} language={language} dailyGoal={user.daily_goal}
            onShowHistory={() => go({ view: 'mistakes' })} />}
    </div>
  )
}

function ProgressBody({ language, dailyGoal, onShowHistory }) {
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

      <WorkOnThis language={language} limit={6} onShowHistory={onShowHistory} />

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
  page: ui.page,
  title: { ...ui.h1, margin: '0.5rem 0 1rem' },
  tabs: { display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginBottom: '1rem' },
  views: { display: 'flex', gap: '1.25rem', borderBottom: '1px solid #e5e7eb', marginBottom: '1.5rem' },
  view: { background: 'none', borderWidth: '0 0 2px', borderStyle: 'solid', borderColor: 'transparent', padding: '0.4rem 0', marginBottom: -1, color: '#6b7280', cursor: 'pointer', fontSize: '0.95rem', fontFamily: 'inherit' },
  viewOn: { borderColor: '#4f46e5', color: '#4f46e5', fontWeight: 600 },
  chip: ui.chip,
  chipActive: ui.chipOn,
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
