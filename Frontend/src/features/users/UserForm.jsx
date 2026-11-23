import { useState } from 'react'

import { ALL_ROLES, ROLE_LABELS } from '../../auth/roles'
import Alert from '../../shared/components/Alert'
import FormField from '../../shared/forms/FormField'
import { inputClass, primaryButtonClass, secondaryButtonClass } from '../../shared/forms/styles'
import { getErrorMessage, getFieldErrors } from '../../shared/utils/apiError'

/**
 * Create mode (no `user`): name, email, role, initial password.
 * Edit mode: name, email, role, status, optional password reset.
 * `isSelf` locks role/status so admins cannot lock themselves out.
 */
export default function UserForm({ user, isSelf = false, onSubmit, onCancel }) {
  const editing = Boolean(user)
  const [form, setForm] = useState({
    name: user?.name ?? '',
    email: user?.email ?? '',
    role: user?.role ?? 'teacher',
    status: user?.status ?? 'active',
    password: '',
  })
  const [errors, setErrors] = useState({})
  const [formError, setFormError] = useState(null)
  const [submitting, setSubmitting] = useState(false)

  const update = (field) => (e) => setForm((f) => ({ ...f, [field]: e.target.value }))

  const handleSubmit = async (event) => {
    event.preventDefault()
    if (submitting) return
    setErrors({})
    setFormError(null)

    let payload
    if (editing) {
      payload = {}
      for (const key of ['name', 'email', 'role', 'status']) {
        if (form[key] !== user[key]) payload[key] = form[key]
      }
      if (form.password) payload.password = form.password
      if (Object.keys(payload).length === 0) {
        onCancel()
        return
      }
    } else {
      payload = { name: form.name, email: form.email, role: form.role, password: form.password }
    }

    setSubmitting(true)
    try {
      await onSubmit(payload)
    } catch (err) {
      setErrors(getFieldErrors(err))
      setFormError(getErrorMessage(err))
      setSubmitting(false)
    }
  }

  const id = (name) => `user-${user?.id ?? 'new'}-${name}`

  return (
    <form className="space-y-4" noValidate onSubmit={handleSubmit}>
      {formError && <Alert>{formError}</Alert>}
      <div className="grid gap-4 sm:grid-cols-2">
        <FormField error={errors.name} htmlFor={id('name')} label="Full name">
          <input className={inputClass} id={id('name')} onChange={update('name')} value={form.name} />
        </FormField>
        <FormField error={errors.email} htmlFor={id('email')} label="Email">
          <input autoComplete="off" className={inputClass} id={id('email')} onChange={update('email')} type="email" value={form.email} />
        </FormField>
        <FormField
          error={errors.role}
          hint={isSelf ? 'You cannot change your own role.' : undefined}
          htmlFor={id('role')}
          label="Role"
        >
          <select className={inputClass} disabled={isSelf} id={id('role')} onChange={update('role')} value={form.role}>
            {ALL_ROLES.map((role) => (
              <option key={role} value={role}>
                {ROLE_LABELS[role]}
              </option>
            ))}
          </select>
        </FormField>
        {editing && (
          <FormField
            error={errors.status}
            hint={isSelf ? 'You cannot deactivate your own account.' : undefined}
            htmlFor={id('status')}
            label="Status"
          >
            <select className={inputClass} disabled={isSelf} id={id('status')} onChange={update('status')} value={form.status}>
              <option value="active">Active</option>
              <option value="inactive">Inactive</option>
            </select>
          </FormField>
        )}
        <FormField
          error={errors.password}
          hint={editing ? 'Leave blank to keep the current password. Resetting signs the user out.' : 'At least 10 characters. Share it with the user securely.'}
          htmlFor={id('password')}
          label={editing ? 'Reset password' : 'Initial password'}
        >
          <input autoComplete="new-password" className={inputClass} id={id('password')} onChange={update('password')} type="password" value={form.password} />
        </FormField>
      </div>
      <div className="flex gap-3">
        <button className={primaryButtonClass} disabled={submitting} type="submit">
          {submitting ? 'Saving…' : editing ? 'Save changes' : 'Create user'}
        </button>
        <button className={secondaryButtonClass} disabled={submitting} onClick={onCancel} type="button">
          Cancel
        </button>
      </div>
    </form>
  )
}
