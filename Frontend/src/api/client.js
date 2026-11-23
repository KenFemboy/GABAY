import axios from 'axios'

// sessionStorage: the token is dropped when the browser tab closes, which suits
// shared school computers. Backend authorization remains the real boundary.
const TOKEN_KEY = 'gabay.accessToken'
export const SESSION_EXPIRED_EVENT = 'gabay:session-expired'

export function getToken() {
  try {
    return sessionStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}

export function setToken(token) {
  sessionStorage.setItem(TOKEN_KEY, token)
}

export function clearToken() {
  try {
    sessionStorage.removeItem(TOKEN_KEY)
  } catch {
    // storage unavailable; nothing to clear
  }
}

const client = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api',
  headers: { 'Content-Type': 'application/json' },
})

client.interceptors.request.use((config) => {
  const token = getToken()
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

client.interceptors.response.use(
  (response) => response,
  (error) => {
    const sentToken = Boolean(error.config?.headers?.Authorization)
    if (error.response?.status === 401 && sentToken) {
      clearToken()
      const apiError = error.response.data?.error
      window.dispatchEvent(
        new CustomEvent(SESSION_EXPIRED_EVENT, {
          detail: {
            code: apiError?.code,
            message: apiError?.message || 'Your session has ended. Please sign in again.',
          },
        }),
      )
    }
    return Promise.reject(error)
  },
)

export default client
