import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth/AuthContext'
import WorkOnThis from '../components/WorkOnThis'
import { LANGUAGES, isOffered, learningLanguage } from '../constants'
import { color, radius, ui } from '../theme'

// Home page. First visit: pick the language you're learning (only when there's
// more than one to choose from). After that: today's goal and streak, a
// "Continue" button, what's due, and shortcuts to each area.
export default function Dashboard() {
  const { user, setUser } = useAuth()
  const [error, setError] = useState(null)
  const choosing = LANGUAGES.length > 1 && !isOffered(user.target_language)
  const language = learningLanguage(user)
  // No language saved yet = a brand-new account, even once Spanish gets saved below
  const [firstVisit] = useState(!user.target_language)

  // Nothing to choose: save the only language as the user's (this also moves
  // anyone who had picked a language that's no longer offered)
  useEffect(() => {
    if (choosing || user.target_language === language) return
    api.updateSettings({ target_language: language }).then(setUser).catch(() => {})
  }, [choosing, language, user.target_language, setUser])

  async function chooseLanguage(code) {
    setError(null)
    try {
      setUser(await api.updateSettings({ target_language: code }))
    } catch (e) {
      setError(e.message)
    }
  }

  if (choosing) {
    return <LanguagePicker username={user.username} onPick={chooseLanguage} error={error} />
  }
  return <Today key={language} user={user} language={language} firstVisit={firstVisit} onSwitch={chooseLanguage} error={error} />
}

function LanguagePicker({ username, onPick, error }) {
  return (
    <div style={{ ...ui.page, maxWidth: 580, textAlign: 'center', paddingTop: '4rem' }}>
      <h1 style={s.welcome}>Welcome, {username}</h1>
      <p style={s.subtitle}>Which language would you like to learn?</p>
      {error && <p style={ui.error}>{error}</p>}
      <div style={s.languages}>
        {LANGUAGES.map(l => (
          <button key={l.code} className="hl-tile" style={s.language} onClick={() => onPick(l.code)}>
            <span style={s.flag}>{l.flag}</span>
            <span style={s.languageName}>{l.label}</span>
            <span style={s.native}>{l.native}</span>
          </button>
        ))}
      </div>
      <p style={s.hint}>You can switch any time.</p>
    </div>
  )
}

const SHORTCUTS = [
  { path: 'vocabulary', icon: '📚', title: 'Vocabulary', desc: 'Words and everyday phrases' },
  { path: 'conversation', icon: '💬', title: 'Conversation', desc: 'Role-play with the AI' },
  { path: 'conjugation', icon: '🔤', title: 'Conjugation', desc: 'Verb tables and sentences' },
  { path: 'review', icon: '🔁', title: 'Review', desc: 'Your weak spots' },
]

function Today({ user, language, firstVisit, onSwitch, error }) {
  const navigate = useNavigate()
  const meta = LANGUAGES.find(l => l.code === language) ?? { label: language, flag: '' }
  const [stats, setStats] = useState(null)
  const [due, setDue] = useState({ verbs: 0, words: 0 })

  useEffect(() => {
    api.getStats(null, 7).then(setStats).catch(() => {})
    api.getWeakSpots(language, 1).then(w => setDue(d => ({ ...d, verbs: w.due_count }))).catch(() => {})
    api.getVocabOverview(language).then(v => setDue(d => ({ ...d, words: v.available ? v.due : 0 }))).catch(() => {})
  }, [language])

  const go = path => navigate(`/practice/${language}${path ? `/${path}` : ''}`)
  const goal = user.daily_goal
  const done = stats?.today_count ?? 0
  const left = Math.max(0, goal - done)

  return (
    <div style={ui.page}>
      <div style={s.header}>
        <h1 style={{ ...ui.h1, margin: 0 }}>{firstVisit ? 'Welcome' : 'Welcome back'}, {user.username}</h1>
        {LANGUAGES.length > 1 && (
          <div style={s.switcher} role="radiogroup" aria-label="Language">
            {LANGUAGES.map(l => (
              <button
                key={l.code}
                role="radio"
                aria-checked={l.code === language}
                aria-label={l.label}
                title={l.label}
                style={l.code === language ? { ...ui.chip, ...ui.chipSoftOn } : ui.chip}
                onClick={() => l.code !== language && onSwitch(l.code)}
              >
                {l.flag}
              </button>
            ))}
          </div>
        )}
      </div>
      {error && <p style={ui.error}>{error}</p>}

      <div style={s.top}>
        <section style={s.today} aria-label="Today">
          <h2 style={ui.h2}>Today</h2>
          <p style={s.big}>{done} <span style={s.of}>/ {goal} answers</span></p>
          <div style={s.bar} role="progressbar" aria-label="Daily goal" aria-valuemin={0} aria-valuemax={goal} aria-valuenow={Math.min(done, goal)}>
            <div style={{ ...s.fill, width: `${Math.min(1, done / goal) * 100}%` }} />
          </div>
          <p style={s.note}>
            {left === 0 ? 'Goal reached — well done!' : `${left} more to reach your daily goal`}
            {stats?.streak_days > 0 && <> · 🔥 {stats.streak_days}-day streak</>}
          </p>
        </section>

        <section style={s.continue} aria-label="Continue">
          <h2 style={{ ...ui.h2, color: '#fff' }}>{meta.flag} {meta.label}</h2>
          <button style={s.continueBtn} onClick={() => go('')}>Continue practising →</button>
          <div style={s.dueList}>
            {due.words > 0 && (
              <button style={s.due} onClick={() => go('vocabulary')}>
                {due.words} {due.words === 1 ? 'word' : 'words'} to review
              </button>
            )}
            {due.verbs > 0 && (
              <button style={s.due} onClick={() => go('review')}>
                {due.verbs} verb {due.verbs === 1 ? 'tense' : 'tenses'} to review
              </button>
            )}
            {due.words === 0 && due.verbs === 0 && <span style={s.dueNone}>Nothing due — learn something new</span>}
          </div>
        </section>
      </div>

      <div style={s.shortcuts}>
        {SHORTCUTS.map(t => (
          <button key={t.path} className="hl-tile" style={ui.tile} onClick={() => go(t.path)}>
            <span style={s.icon}>{t.icon}</span>
            <span style={s.tileTitle}>{t.title}</span>
            <span style={s.tileDesc}>{t.desc}</span>
          </button>
        ))}
      </div>

      <section style={s.work} aria-label="Work on this">
        <WorkOnThis language={language} />
      </section>
    </div>
  )
}

const s = {
  welcome: { fontSize: '2.4rem', fontWeight: 800, color: color.ink, margin: '0 0 0.6rem', lineHeight: 1.15, overflowWrap: 'anywhere' },
  subtitle: { fontSize: '1.1rem', color: color.muted, margin: '0 0 2.5rem' },
  languages: { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: '0.9rem' },
  language: { ...ui.tile, alignItems: 'center', textAlign: 'center', padding: '1.75rem 1rem', borderRadius: radius.lg },
  flag: { fontSize: '2.5rem' },
  languageName: { fontWeight: 700, fontSize: '1.05rem', color: color.ink },
  native: { fontSize: '0.82rem', color: color.faint },
  hint: { color: color.faint, fontSize: '0.85rem', marginTop: '1.5rem' },

  header: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap', margin: '0.5rem 0 1.25rem' },
  switcher: { display: 'flex', gap: '0.35rem' },
  top: { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: '0.9rem', marginBottom: '0.9rem' },
  today: { ...ui.panel, padding: '1.25rem 1.35rem' },
  big: { fontSize: '2rem', fontWeight: 800, color: color.ink, margin: '0 0 0.6rem' },
  of: { fontSize: '1rem', fontWeight: 500, color: color.muted },
  bar: { height: 8, borderRadius: 4, background: color.primaryBorder, overflow: 'hidden' },
  fill: { height: '100%', background: color.primary, borderRadius: 4 },
  note: { fontSize: '0.85rem', color: color.muted, margin: '0.6rem 0 0' },
  continue: { background: color.primary, color: '#fff', borderRadius: radius.md, padding: '1.25rem 1.35rem', display: 'flex', flexDirection: 'column', gap: '0.75rem' },
  continueBtn: { ...ui.primary, background: '#fff', color: color.primary, borderColor: '#fff', alignSelf: 'flex-start', fontSize: '1rem', padding: '0.7rem 1.25rem' },
  dueList: { display: 'flex', flexWrap: 'wrap', gap: '0.4rem' },
  due: { background: 'rgba(255,255,255,0.16)', color: '#fff', border: 'none', borderRadius: radius.pill, padding: '0.35rem 0.8rem', fontSize: '0.85rem', cursor: 'pointer', fontFamily: 'inherit' },
  dueNone: { fontSize: '0.85rem', color: '#e0e7ff' },
  shortcuts: { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: '0.75rem', marginBottom: '1.5rem' },
  icon: { fontSize: '1.5rem' },
  tileTitle: { fontWeight: 700, color: color.ink },
  tileDesc: { fontSize: '0.82rem', color: color.muted },
  work: { marginTop: '0.5rem' },
}
