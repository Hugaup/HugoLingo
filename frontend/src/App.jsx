import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import AuthProvider from './auth/AuthProvider'
import RequireAuth from './components/RequireAuth'
import Auth from './pages/Auth'
import Welcome from './pages/Welcome'
import Practice from './pages/Practice'
import Exercise from './pages/Exercise'
import Conjugation from './pages/Conjugation'
import Settings from './pages/Settings'

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<Auth key="login" mode="login" />} />
          <Route path="/signup" element={<Auth key="signup" mode="signup" />} />
          <Route element={<RequireAuth />}>
            <Route path="/" element={<Welcome />} />
            <Route path="/practice/:language" element={<Practice />} />
            <Route path="/practice/:language/conjugation" element={<Conjugation />} />
            <Route path="/exercise" element={<Exercise />} />
            <Route path="/settings" element={<Settings />} />
          </Route>
          <Route path="*" element={<Navigate to="/" />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  )
}
