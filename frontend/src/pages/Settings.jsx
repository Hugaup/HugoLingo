import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth/AuthContext'
import { LANGUAGES, LEVELS } from '../constants'
import { color, ui } from '../theme'

const PASSWORD_MIN = 4

export default function Settings() {
  const { user, setUser, logout } = useAuth()
  const navigate = useNavigate()

  const [targetLanguage, setTargetLanguage] = useState(user.target_language ?? '')
  const [level, setLevel]                   = useState(user.level)
  const [dailyGoal, setDailyGoal]           = useState(user.daily_goal)
  const [prefsStatus, setPrefsStatus]       = useState(null)
  const [savingPrefs, setSavingPrefs]       = useState(false)

  const [currentPw, setCurrentPw] = useState('')
  const [newPw, setNewPw]         = useState('')
  const [confirmPw, setConfirmPw] = useState('')
  const [pwStatus, setPwStatus]   = useState(null)
  const [savingPw, setSavingPw]   = useState(false)

  async function savePrefs(e) {
    e.preventDefault()
    setSavingPrefs(true)
    setPrefsStatus(null)
    try {
      const updated = await api.updateSettings({
        target_language: targetLanguage || null,
        level: Number(level),
        daily_goal: Number(dailyGoal),
      })
      setUser(updated)
      setPrefsStatus({ ok: true, text: 'Saved.' })
    } catch (err) {
      setPrefsStatus({ ok: false, text: err.message })
    } finally {
      setSavingPrefs(false)
    }
  }

  async function savePassword(e) {
    e.preventDefault()
    if (newPw.length < PASSWORD_MIN) {
      setPwStatus({ ok: false, text: `New password must be at least ${PASSWORD_MIN} characters.` })
      return
    }
    if (newPw !== confirmPw) {
      setPwStatus({ ok: false, text: "New passwords don't match." })
      return
    }
    setSavingPw(true)
    setPwStatus(null)
    try {
      await api.changePassword(currentPw, newPw)
      setCurrentPw(''); setNewPw(''); setConfirmPw('')
      setPwStatus({ ok: true, text: 'Password changed. Other devices have been logged out.' })
    } catch (err) {
      setPwStatus({ ok: false, text: err.message })
    } finally {
      setSavingPw(false)
    }
  }

  return (
    <div style={s.page}>
      <Link to="/" style={s.back}>← Back</Link>
      <h1 style={s.title}>Settings</h1>

      <form style={s.card} onSubmit={savePrefs}>
        <h2 style={s.section}>Learning</h2>

        <label style={s.label} htmlFor="target-language">Language I'm learning</label>
        <select id="target-language" style={s.input} value={targetLanguage} onChange={e => setTargetLanguage(e.target.value)}>
          <option value="">Not set</option>
          {LANGUAGES.map(l => <option key={l.code} value={l.code}>{l.flag} {l.label}</option>)}
        </select>

        <label style={s.label} htmlFor="level">Level</label>
        <select id="level" style={s.input} value={level} onChange={e => setLevel(e.target.value)}>
          {LEVELS.map(l => <option key={l.value} value={l.value}>{l.label}</option>)}
        </select>

        <label style={s.label} htmlFor="daily-goal">Daily goal (answers per day)</label>
        <input
          id="daily-goal" type="number" min={1} max={500} style={s.input}
          value={dailyGoal} onChange={e => setDailyGoal(e.target.value)}
        />

        {prefsStatus && <p style={prefsStatus.ok ? s.ok : s.error} role="status">{prefsStatus.text}</p>}
        <button type="submit" style={s.submit} disabled={savingPrefs}>{savingPrefs ? 'Saving…' : 'Save'}</button>
      </form>

      <form style={s.card} onSubmit={savePassword}>
        <h2 style={s.section}>Change password</h2>

        <label style={s.label} htmlFor="current-password">Current password</label>
        <input id="current-password" type="password" autoComplete="current-password" style={s.input}
          value={currentPw} onChange={e => setCurrentPw(e.target.value)} />

        <label style={s.label} htmlFor="new-password">New password</label>
        <input id="new-password" type="password" autoComplete="new-password" style={s.input}
          value={newPw} onChange={e => setNewPw(e.target.value)} />

        <label style={s.label} htmlFor="confirm-new-password">Confirm new password</label>
        <input id="confirm-new-password" type="password" autoComplete="new-password" style={s.input}
          value={confirmPw} onChange={e => setConfirmPw(e.target.value)} />

        {pwStatus && <p style={pwStatus.ok ? s.ok : s.error} role="status">{pwStatus.text}</p>}
        <button type="submit" style={s.submit} disabled={savingPw}>{savingPw ? 'Saving…' : 'Change password'}</button>
      </form>

      <section style={{ ...s.card, ...s.account }} aria-label="Account">
        <span>Logged in as <strong>{user.username}</strong></span>
        <button style={ui.secondary} onClick={async () => { await logout(); navigate('/login', { replace: true }) }}>Log out</button>
      </section>
    </div>
  )
}

const s = {
  page: { ...ui.page, maxWidth: 480 },
  back: { ...ui.back, textDecoration: 'none' },
  title: ui.h1,
  card: { ...ui.panel, display: 'flex', flexDirection: 'column', marginBottom: '1.5rem' },
  account: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: '1rem', flexWrap: 'wrap', color: color.body },
  section: { ...ui.h2, marginBottom: '1rem' },
  label: { fontSize: '0.85rem', fontWeight: 600, color: color.body, marginBottom: '0.35rem' },
  input: { padding: '0.55rem 0.75rem', border: `1px solid ${color.borderStrong}`, borderRadius: 8, fontSize: '1rem', fontFamily: 'inherit', marginBottom: '1rem', background: '#fff' },
  ok: { color: color.success, fontSize: '0.9rem', margin: '0 0 1rem' },
  error: { color: color.danger, fontSize: '0.9rem', margin: '0 0 1rem' },
  submit: { ...ui.primary, alignSelf: 'flex-start' },
}
