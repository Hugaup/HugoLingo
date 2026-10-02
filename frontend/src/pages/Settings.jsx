import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth/AuthContext'
import { LANGUAGES, LEVELS } from '../constants'

const PASSWORD_MIN = 4

export default function Settings() {
  const { user, setUser } = useAuth()

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
    </div>
  )
}

const s = {
  page: { maxWidth: 480, margin: '0 auto', padding: '2rem 1.5rem', fontFamily: 'system-ui, sans-serif' },
  back: { color: '#6b7280', textDecoration: 'none', fontSize: '0.9rem' },
  title: { fontSize: '1.75rem', fontWeight: 800, color: '#1e1b4b', margin: '0.75rem 0 1.5rem' },
  card: { display: 'flex', flexDirection: 'column', background: '#f8f9fa', borderRadius: 12, padding: '1.5rem', marginBottom: '1.5rem' },
  section: { fontSize: '1.05rem', fontWeight: 700, color: '#1e1b4b', margin: '0 0 1rem' },
  label: { fontSize: '0.85rem', fontWeight: 600, color: '#374151', marginBottom: '0.35rem' },
  input: { padding: '0.55rem 0.75rem', border: '1px solid #d1d5db', borderRadius: 8, fontSize: '1rem', fontFamily: 'inherit', marginBottom: '1rem', background: '#fff' },
  ok: { color: '#15803d', fontSize: '0.9rem', margin: '0 0 1rem' },
  error: { color: '#b91c1c', fontSize: '0.9rem', margin: '0 0 1rem' },
  submit: { alignSelf: 'flex-start', background: '#4f46e5', color: '#fff', border: 'none', borderRadius: 8, padding: '0.6rem 1.25rem', fontSize: '0.95rem', fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' },
}
