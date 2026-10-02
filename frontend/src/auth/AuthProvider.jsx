import { useCallback, useEffect, useMemo, useState } from 'react'
import { api, setUnauthorizedHandler } from '../api'
import { AuthContext } from './AuthContext'

export default function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    // Any 401 anywhere in the app (expired session) logs the user out locally
    setUnauthorizedHandler(() => setUser(null))
    api.me()
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setLoading(false))
    return () => setUnauthorizedHandler(null)
  }, [])

  const login = useCallback(async (username, password) => {
    const me = await api.login(username, password)
    setUser(me)
    return me
  }, [])

  const signup = useCallback(async (username, password) => {
    const me = await api.signup(username, password)
    setUser(me)
    return me
  }, [])

  const logout = useCallback(async () => {
    try {
      await api.logout()
    } finally {
      setUser(null)
    }
  }, [])

  const value = useMemo(
    () => ({ user, loading, login, signup, logout, setUser }),
    [user, loading, login, signup, logout],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
