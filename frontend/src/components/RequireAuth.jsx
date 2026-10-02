import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import TopBar from './TopBar'

// Layout route: everything nested under it needs a logged-in user
export default function RequireAuth() {
  const { user, loading } = useAuth()
  const location = useLocation()

  if (loading) return <p style={s.loading}>Loading…</p>
  if (!user) return <Navigate to="/login" replace state={{ from: location }} />

  return (
    <>
      <TopBar />
      <Outlet />
    </>
  )
}

const s = {
  loading: { textAlign: 'center', marginTop: '5rem', color: '#6b7280', fontFamily: 'system-ui, sans-serif' },
}
