import { createContext, useContext } from 'react'

export const AuthContext = createContext(null)

// { user, loading, login, signup, logout, setUser } — see AuthProvider
export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>')
  return ctx
}
