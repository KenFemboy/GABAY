import { useState } from 'react'

import Alert from '../../shared/components/Alert'
import FormField from '../../shared/forms/FormField'
import { inputClass, primaryButtonClass, secondaryButtonClass } from '../../shared/forms/styles'
import { getErrorMessage, getFieldErrors } from '../../shared/utils/apiError'
import { ASSESSMENT_TYPES } from './constants'

const today = () => new Date().toISOString().slice(0, 10)

export default function AssessmentForm({ learnerId, onSubmit, onCancel }) {
  const [form, setForm] = useState({ assessment_type: '', assessment_date: today(), assessor: '', notes: '' })
  const [errors, setErrors] = useState({})
  const [formError, setFormError] = useState(null)
  const [submitting, setSubmitting] = useState(false)

  const update = (field) => (e) => setForm((f) => ({ ...f, [field]: e.target.value }))

  const handleSubmit = async (event) => {
    event.preventDefault()
    if (submitting) return
    setErrors({})
    setFormError(null)
    const payload = { learner_id: learnerId, ...form, notes: form.notes.trim() || null }
    for (const key of ['assessment_type', 'assessment_date']) {
      if (!payload[key]) delete payload[key] // backend reports "This field is required."
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

  return (
    <form className="space-y-4" noValidate onSubmit={handleSubmit}>
      {formError && <Alert>{formError}</Alert>}
      <div className="grid gap-4 sm:grid-cols-3">
        <FormField error={errors.assessment_type} htmlFor="assessment-type" label="Type">
          <select className={inputClass} id="assessment-type" onChange={update('assessment_type')} value={form.assessment_type}>
            <option value="">Select type</option>
            {ASSESSMENT_TYPES.map((t) => (
              <option key={t.value} value={t.value}>{t.label}</option>
            ))}
          </select>
        </FormField>
        <FormField error={errors.assessment_date} htmlFor="assessment-date" label="Assessment date">
          <input className={inputClass} id="assessment-date" max={today()} onChange={update('assessment_date')} type="date" value={form.assessment_date} />
        </FormField>
        <FormField error={errors.assessor} htmlFor="assessment-assessor" label="Assessor">
          <input autoComplete="off" className={inputClass} id="assessment-assessor" onChange={update('assessor')} placeholder="Name of adviser or psychologist" value={form.assessor} />
        </FormField>
      </div>
      <FormField error={errors.notes} htmlFor="assessment-notes" label="Notes (optional)">
        <textarea className={inputClass} id="assessment-notes" maxLength={5000} onChange={update('notes')} rows={3} value={form.notes} />
      </FormField>
      <div className="flex gap-3">
        <button className={primaryButtonClass} disabled={submitting} type="submit">
          {submitting ? 'Saving…' : 'Create assessment'}
        </button>
        <button className={secondaryButtonClass} disabled={submitting} onClick={onCancel} type="button">
          Cancel
        </button>
      </div>
    </form>
  )
}
