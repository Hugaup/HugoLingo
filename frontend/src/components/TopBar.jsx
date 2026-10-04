import { Link, NavLink, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { learningLanguage } from '../constants'
import { color, font } from '../theme'

export default function TopBar() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  async function handleLogout() {
    await logout()
    navigate('/login', { replace: true })
  }

  const practice = `/practice/${learningLanguage(user)}`
  const link = ({ isActive }) => (isActive ? { ...s.link, ...s.linkOn } : s.link)

  return (
    <header style={s.bar}>
      <Link to="/" style={s.brand}>HugoLingo</Link>
      <nav style={s.nav} aria-label="Main">
        <NavLink to={practice} style={link} end={practice === '/'}>Practice</NavLink>
        <NavLink to="/progress" style={link}>Progress</NavLink>
        <NavLink to="/settings" style={link}>Settings</NavLink>
        <span className="hl-wide-only" style={s.user}>{user.username}</span>
        <button className="hl-wide-only" style={s.logout} onClick={handleLogout}>Log out</button>
      </nav>
    </header>
  )
}

const s = {
  bar: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '0.75rem', padding: '0.7rem 1rem', borderBottom: `1px solid ${color.border}`, fontFamily: font, background: '#fff' },
  brand: { fontWeight: 800, color: color.primary, textDecoration: 'none', fontSize: '1.1rem' },
  nav: { display: 'flex', alignItems: 'center', gap: '0.25rem', fontSize: '0.9rem' },
  link: { color: color.body, textDecoration: 'none', padding: '0.35rem 0.6rem', borderRadius: 8, whiteSpace: 'nowrap' },
  linkOn: { color: color.primary, background: color.primarySoft, fontWeight: 600 },
  user: { color: color.ink, fontWeight: 600, margin: '0 0.4rem 0 0.75rem' },
  logout: { background: 'none', borderWidth: 1, borderStyle: 'solid', borderColor: color.border, borderRadius: 8, padding: '0.35rem 0.75rem', cursor: 'pointer', fontFamily: 'inherit', color: color.body },
}
