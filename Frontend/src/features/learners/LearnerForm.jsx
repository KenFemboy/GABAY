import { useState } from 'react'

import Alert from '../../shared/components/Alert'
import FormField from '../../shared/forms/FormField'
import { inputClass, primaryButtonClass, secondaryButtonClass } from '../../shared/forms/styles'
import { getErrorMessage, getFieldErrors } from '../../shared/utils/apiError'
import { currentSchoolYear, GRADE_LEVELS, SEX_OPTIONS, STATUS_OPTIONS } from './constants'

const FIELDS = [
  'learner_code',
  'first_name',
  'middle_name',
  'last_name',
  'birth_date',
  'sex',
  'grade_level',
  'section',
  'school_year',
  'status',
]

const today = () => new Date().toISOString().slice(0, 10)

/**
 * Create mode (no `learner`) or edit mode. In edit mode only changed fields are
 * sent; status can only be changed when editing (learners are never deleted).
 */
export default function LearnerForm({ learner, onSubmit, onCancel }) {
  const editing = Boolean(learner)
  const [form, setForm] = useState(() =>
    Object.fromEntries(
      FIELDS.map((key) => {
        const defaults = { school_year: currentSchoolYear(), status: 'active' }
        return [key, learner?.[key] ?? defaults[key] ?? '']
      }),
    ),
  )
  const [errors, setErrors] = useState({})
  const [formError, setFormError] = useState(null)
  const [submitting, setSubmitting] = useState(false)

  const update = (field) => (e) => setForm((f) => ({ ...f, [field]: e.target.value }))

  const handleSubmit = async (event) => {
    event.preventDefault()
    if (submitting) return
    setErrors({})
    setFormError(null)

    // Blank middle name means "none".
    const values = { ...form, middle_name: form.middle_name.trim() || null }

    let payload
    if (editing) {
      payload = {}
      for (const key of FIELDS) {
        if (values[key] !== (learner[key] ?? null)) payload[key] = values[key]
      }
      if (Object.keys(payload).length === 0) {
        onCancel()
        return
      }
    } else {
      payload = Object.fromEntries(FIELDS.filter((k) => k !== 'status').map((k) => [k, values[k]]))
      // Let the backend report empty required fields with its own message.
      for (const key of Object.keys(payload)) {
        if (payload[key] === '') delete payload[key]
      }
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

  const id = (name) => `learner-${learner?.id ?? 'new'}-${name}`

  const text = (name, label, props = {}) => (
    <FormField error={errors[name]} hint={props.hint} htmlFor={id(name)} label={label}>
      <input
        autoComplete="off"
        className={inputClass}
        id={id(name)}
        onChange={update(name)}
        value={form[name]}
        {...props.input}
      />
    </FormField>
  )

  const select = (name, label, options, placeholder) => (
    <FormField error={errors[name]} htmlFor={id(name)} label={label}>
      <select className={inputClass} id={id(name)} onChange={update(name)} value={form[name]}>
        {placeholder && <option value="">{placeholder}</option>}
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </FormField>
  )

  return (
    <form className="space-y-4" noValidate onSubmit={handleSubmit}>
      {formError && <Alert>{formError}</Alert>}
      <div className="grid gap-4 sm:grid-cols-3">
        {text('learner_code', 'Learner code', { hint: 'Letters, digits and dashes. Must be unique.' })}
        {text('school_year', 'School year', { hint: 'For example 2025-2026.' })}
        {select('grade_level', 'Grade level', GRADE_LEVELS, 'Select grade')}
        {text('first_name', 'First name')}
        {text('middle_name', 'Middle name (optional)')}
        {text('last_name', 'Last name')}
        {text('birth_date', 'Birth date', { input: { type: 'date', max: today() } })}
        {select('sex', 'Sex', SEX_OPTIONS, 'Select sex')}
        {text('section', 'Section')}
        {editing && select('status', 'Status', STATUS_OPTIONS)}
      </div>
      {editing && form.status !== 'active' && form.status !== learner.status && (
        <Alert tone="info">
          Learner records are never deleted. Changing the status keeps all history and hides the
          learner from &ldquo;Active&rdquo; lists.
        </Alert>
      )}
      <div className="flex gap-3">
        <button className={primaryButtonClass} disabled={submitting} type="submit">
          {submitting ? 'Saving…' : editing ? 'Save changes' : 'Create learner'}
        </button>
        <button className={secondaryButtonClass} disabled={submitting} onClick={onCancel} type="button">
          Cancel
        </button>
      </div>
    </form>
  )
}
