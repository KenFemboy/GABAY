import { useState } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'

import useAuth from '../../auth/useAuth'
import Alert from '../../shared/components/Alert'
import FormField from '../../shared/forms/FormField'
import { inputClass, primaryButtonClass } from '../../shared/forms/styles'
import { getErrorMessage } from '../../shared/utils/apiError'

export default function LoginPage() {
  const { user, login, notice } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const redirectTo = location.state?.from?.pathname || '/dashboard'

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [submitting, setSubmitting] = useState(false)

  if (user) return <Navigate replace to={redirectTo} />

  const handleSubmit = async (event) => {
    event.preventDefault()
    if (submitting) return
    setError(null)
    setSubmitting(true)
    try {
      await login(email, password)
      navigate(redirectTo, { replace: true })
    } catch (err) {
      setError(getErrorMessage(err, 'Unable to sign in.'))
      setSubmitting(false)
    }
  }

  return (
    <section className="w-full max-w-md rounded-xl bg-white p-8 shadow">
      <h1 className="text-2xl font-bold text-slate-900">Sign in to GABAY</h1>
      <p className="mt-1 text-sm text-slate-600">Use the account provided by your System Administrator.</p>

      <form className="mt-6 space-y-4" noValidate onSubmit={handleSubmit}>
        {notice && !error && <Alert tone="info">{notice}</Alert>}
        {error && <Alert>{error}</Alert>}

        <FormField htmlFor="email" label="Email">
          <input
            autoComplete="username"
            autoFocus
            className={inputClass}
            id="email"
            onChange={(e) => setEmail(e.target.value)}
            required
            type="email"
            value={email}
          />
        </FormField>

        <FormField htmlFor="password" label="Password">
          <input
            autoComplete="current-password"
            className={inputClass}
            id="password"
            onChange={(e) => setPassword(e.target.value)}
            required
            type="password"
            value={password}
          />
        </FormField>

        <button
          className={`w-full ${primaryButtonClass}`}
          disabled={submitting || !email || !password}
          type="submit"
        >
          {submitting ? 'Signing in…' : 'Sign in'}
        </button>
      </form>
    </section>
  )
}
