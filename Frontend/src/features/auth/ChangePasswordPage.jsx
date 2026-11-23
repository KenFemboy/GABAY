import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { changePassword } from '../../api/authApi'
import useAuth from '../../auth/useAuth'
import Alert from '../../shared/components/Alert'
import FormField from '../../shared/forms/FormField'
import { inputClass, primaryButtonClass } from '../../shared/forms/styles'
import { getErrorMessage, getFieldErrors } from '../../shared/utils/apiError'

const MIN_LENGTH = 10

export default function ChangePasswordPage() {
  const { logout } = useAuth()
  const navigate = useNavigate()
  const [form, setForm] = useState({ current: '', next: '', confirm: '' })
  const [errors, setErrors] = useState({})
  const [formError, setFormError] = useState(null)
  const [submitting, setSubmitting] = useState(false)

  const update = (field) => (e) => setForm((f) => ({ ...f, [field]: e.target.value }))

  const handleSubmit = async (event) => {
    event.preventDefault()
    if (submitting) return
    const clientErrors = {}
    if (form.next.length < MIN_LENGTH) clientErrors.next = `Use at least ${MIN_LENGTH} characters.`
    if (form.next !== form.confirm) clientErrors.confirm = 'Passwords do not match.'
    setErrors(clientErrors)
    setFormError(null)
    if (Object.keys(clientErrors).length) return

    setSubmitting(true)
    try {
      await changePassword(form.current, form.next)
      // The server invalidates existing tokens on password change; sign in again.
      await logout({
        callServer: false,
        notice: 'Password changed. Please sign in with your new password.',
      })
      navigate('/login', { replace: true })
    } catch (err) {
      const fields = getFieldErrors(err)
      setErrors({ next: fields.new_password, current: fields.current_password })
      setFormError(getErrorMessage(err))
      setSubmitting(false)
    }
  }

  return (
    <section className="max-w-lg rounded-xl bg-white p-8 shadow">
      <h1 className="text-2xl font-bold text-slate-900">Change password</h1>
      <p className="mt-1 text-sm text-slate-600">You will be asked to sign in again afterwards.</p>

      <form className="mt-6 space-y-4" noValidate onSubmit={handleSubmit}>
        {formError && <Alert>{formError}</Alert>}
        <FormField error={errors.current} htmlFor="current" label="Current password">
          <input autoComplete="current-password" className={inputClass} id="current" onChange={update('current')} type="password" value={form.current} />
        </FormField>
        <FormField error={errors.next} hint={`At least ${MIN_LENGTH} characters.`} htmlFor="next" label="New password">
          <input autoComplete="new-password" className={inputClass} id="next" onChange={update('next')} type="password" value={form.next} />
        </FormField>
        <FormField error={errors.confirm} htmlFor="confirm" label="Confirm new password">
          <input autoComplete="new-password" className={inputClass} id="confirm" onChange={update('confirm')} type="password" value={form.confirm} />
        </FormField>
        <button className={primaryButtonClass} disabled={submitting || !form.current} type="submit">
          {submitting ? 'Saving…' : 'Change password'}
        </button>
      </form>
    </section>
  )
}
