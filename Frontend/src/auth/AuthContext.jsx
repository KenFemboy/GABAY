import { useCallback, useEffect, useMemo, useState } from 'react'

import * as authApi from '../api/authApi'
import { SESSION_EXPIRED_EVENT, clearToken, getToken, setToken } from '../api/client'
import { AuthContext } from './context'

/**
 * status: 'loading'       – checking a stored token with GET /auth/me
 *         'authenticated' – user is set
 *         'anonymous'     – no valid session
 * notice: message shown on the login page (e.g. session expired)
 */
export function AuthProvider({ children }) {
  const [state, setState] = useState(() => ({
    user: null,
    status: getToken() ? 'loading' : 'anonymous',
    notice: null,
  }))

  useEffect(() => {
    if (!getToken()) return undefined
    let active = true
    authApi
      .getMe()
      .then(({ data }) => {
        if (active) setState({ user: data, status: 'authenticated', notice: null })
      })
      .catch(() => {
        if (!active) return
        clearToken()
        setState((prev) => ({ ...prev, user: null, status: 'anonymous' }))
      })
    return () => {
      active = false
    }
  }, [])

  useEffect(() => {
    const onExpired = (event) => {
      setState({ user: null, status: 'anonymous', notice: event.detail?.message ?? null })
    }
    window.addEventListener(SESSION_EXPIRED_EVENT, onExpired)
    return () => window.removeEventListener(SESSION_EXPIRED_EVENT, onExpired)
  }, [])

  const login = useCallback(async (email, password) => {
    const { data } = await authApi.login(email, password)
    setToken(data.access_token)
    setState({ user: data.user, status: 'authenticated', notice: null })
    return data.user
  }, [])

  /**
   * options.notice     – message to show on the login page afterwards
   * options.callServer – set false when the token is already known to be invalid
   */
  const logout = useCallback(async ({ notice = null, callServer = true } = {}) => {
    if (callServer) {
      try {
        await authApi.logout()
      } catch {
        // Token may already be invalid; logging out locally is what matters.
      }
    }
    clearToken()
    setState({ user: null, status: 'anonymous', notice })
  }, [])

  const hasRole = useCallback(
    (...roles) => Boolean(state.user && roles.includes(state.user.role)),
    [state.user],
  )

  const value = useMemo(
    () => ({ ...state, login, logout, hasRole }),
    [state, login, logout, hasRole],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
