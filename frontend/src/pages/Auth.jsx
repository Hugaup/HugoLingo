import { useState } from 'react'
import { Link, Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { ui } from '../theme'

// Mirrors the backend rules in schemas.py (SignupRequest) for instant feedback
const USERNAME_RE = /^[A-Za-z0-9_.-]{3,32}$/
const PASSWORD_MIN = 4

function validate(isSignup, username, password, confirm) {
  if (!username.trim() || !password) return 'Please enter a username and password.'
  if (!isSignup) return null
  if (!USERNAME_RE.test(username)) return 'Username must be 3–32 characters: letters, numbers, _ . or -'
  if (password.length < PASSWORD_MIN) return `Password must be at least ${PASSWORD_MIN} characters.`
  if (password !== confirm) return "Passwords don't match."
  return null
}

export default function Auth({ mode }) {
  const isSignup = mode === 'signup'
  const { user, login, signup } = useAuth()
  const location = useLocation()
  const from = location.state?.from

  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState(null)
  const [submitting, setSubmitting] = useState(false)

  // Once logged in, go back to wherever the user was heading
  if (user) return <Navigate to={from?.pathname ?? '/'} state={from?.state} replace />

  async function handleSubmit(e) {
    e.preventDefault()
    const problem = validate(isSignup, username, password, confirm)
    if (problem) {
      setError(problem)
      return
    }
    setError(null)
    setSubmitting(true)
    try {
      await (isSignup ? signup : login)(username.trim(), password)
    } catch (err) {
      setError(err.message)
      setSubmitting(false)
    }
  }

  return (
    <div style={s.page}>
      <h1 style={s.brand}>HugoLingo</h1>
      <form style={s.card} onSubmit={handleSubmit} noValidate>
        <h2 style={s.title}>{isSignup ? 'Create an account' : 'Log in'}</h2>

        <label style={s.label} htmlFor="username">Username</label>
        <input
          id="username" style={s.input} autoComplete="username" autoFocus
          value={username} onChange={e => setUsername(e.target.value)}
        />

        <label style={s.label} htmlFor="password">Password</label>
        <input
          id="password" type="password" style={s.input}
          autoComplete={isSignup ? 'new-password' : 'current-password'}
          value={password} onChange={e => setPassword(e.target.value)}
        />

        {isSignup && (
          <>
            <label style={s.label} htmlFor="confirm">Confirm password</label>
            <input
              id="confirm" type="password" style={s.input} autoComplete="new-password"
              value={confirm} onChange={e => setConfirm(e.target.value)}
            />
          </>
        )}

        {error && <p style={s.error} role="alert">{error}</p>}

        <button type="submit" style={s.submit} disabled={submitting}>
          {submitting ? '…' : isSignup ? 'Create account' : 'Log in'}
        </button>

        <p style={s.switch}>
          {isSignup ? 'Already have an account? ' : 'No account yet? '}
          <Link to={isSignup ? '/login' : '/signup'} state={location.state} style={s.link}>
            {isSignup ? 'Log in' : 'Create one'}
          </Link>
        </p>
      </form>
    </div>
  )
}

const s = {
  page: { ...ui.page, maxWidth: 400, paddingTop: '5rem' },
  brand: { textAlign: 'center', fontSize: '2.25rem', fontWeight: 800, color: '#4f46e5', margin: '0 0 2rem' },
  card: { ...ui.panel, display: 'flex', flexDirection: 'column', padding: '1.75rem' },
  title: { fontSize: '1.25rem', fontWeight: 700, color: '#1e1b4b', margin: '0 0 1.25rem' },
  label: { fontSize: '0.85rem', fontWeight: 600, color: '#374151', marginBottom: '0.35rem' },
  input: { padding: '0.6rem 0.75rem', border: '1px solid #d1d5db', borderRadius: 8, fontSize: '1rem', fontFamily: 'inherit', marginBottom: '1rem' },
  error: { color: '#b91c1c', background: '#fef2f2', borderRadius: 8, padding: '0.6rem 0.75rem', fontSize: '0.9rem', margin: '0 0 1rem' },
  submit: { ...ui.primary, padding: '0.7rem', fontSize: '1rem' },
  switch: { textAlign: 'center', fontSize: '0.9rem', color: '#6b7280', margin: '1.25rem 0 0' },
  link: { color: '#4f46e5', fontWeight: 600, textDecoration: 'none' },
}
