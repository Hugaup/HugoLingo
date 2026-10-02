import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'

export default function TopBar() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  async function handleLogout() {
    await logout()
    navigate('/login', { replace: true })
  }

  return (
    <header style={s.bar}>
      <Link to="/" style={s.brand}>HugoLingo</Link>
      <nav style={s.nav}>
        <span style={s.user}>{user.username}</span>
        <Link to="/settings" style={s.link}>Settings</Link>
        <button style={s.logout} onClick={handleLogout}>Log out</button>
      </nav>
    </header>
  )
}

const s = {
  bar: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '0.75rem 1.5rem', borderBottom: '1px solid #e5e7eb', fontFamily: 'system-ui, sans-serif' },
  brand: { fontWeight: 800, color: '#4f46e5', textDecoration: 'none', fontSize: '1.1rem' },
  nav: { display: 'flex', alignItems: 'center', gap: '1rem', fontSize: '0.9rem' },
  user: { color: '#1e1b4b', fontWeight: 600 },
  link: { color: '#4f46e5', textDecoration: 'none' },
  logout: { background: 'none', border: '1px solid #e5e7eb', borderRadius: 8, padding: '0.35rem 0.75rem', cursor: 'pointer', fontFamily: 'inherit', color: '#374151' },
}
