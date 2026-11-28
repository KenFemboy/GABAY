import { useState } from 'react'

import Alert from '../../shared/components/Alert'
import FormField from '../../shared/forms/FormField'
import { inputClass, primaryButtonClass, secondaryButtonClass } from '../../shared/forms/styles'
import { getErrorMessage } from '../../shared/utils/apiError'

const today = () => {
  const d = new Date()
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10)
}

function fromEntry(entry, period) {
  if (entry) {
    return {
      activity_date: entry.activity_date, title: entry.title, description: entry.description,
      materials: entry.materials ?? '', learner_response: entry.learner_response ?? '',
      duration_minutes: entry.duration_minutes ?? '', notes: entry.notes ?? '',
    }
  }
  // Default to today, clipped into the IEP period.
  let date = today()
  if (period?.end && date > period.end) date = period.end
  if (period?.start && date < period.start) date = period.start
  return { activity_date: date, title: '', description: '', materials: '', learner_response: '', duration_minutes: '', notes: '' }
}

/** Create or edit an ILAW activity entry. */
export default function IlawEntryForm({ entry, period, onSubmit, onCancel }) {
  const [form, setForm] = useState(() => fromEntry(entry, period))
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)
  const [fieldErrors, setFieldErrors] = useState({})
  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }))

  const submit = async (e) => {
    e.preventDefault()
    setSaving(true)
    setError(null)
    setFieldErrors({})
    try {
      await onSubmit({
        activity_date: form.activity_date,
        title: form.title,
        description: form.description,
        materials: form.materials || null,
        learner_response: form.learner_response || null,
        duration_minutes: form.duration_minutes === '' ? null : Number(form.duration_minutes),
        notes: form.notes || null,
      })
    } catch (err) {
      const details = err?.response?.data?.error?.details ?? []
      setFieldErrors(Object.fromEntries(details.map((d) => [d.field, d.message])))
      setError(getErrorMessage(err))
      setSaving(false)
    }
  }

  return (
    <form className="space-y-3" onSubmit={submit}>
      <div className="grid gap-3 sm:grid-cols-[10rem_1fr_8rem]">
        <FormField error={fieldErrors.activity_date} htmlFor="ilaw-date" label="Date">
          <input className={inputClass} id="ilaw-date" max={period?.end && period.end < today() ? period.end : today()} min={period?.start ?? undefined} onChange={set('activity_date')} required type="date" value={form.activity_date} />
        </FormField>
        <FormField error={fieldErrors.title} htmlFor="ilaw-title" label="Activity title">
          <input className={inputClass} id="ilaw-title" maxLength={150} onChange={set('title')} placeholder="e.g. Subtraction with counters" required value={form.title} />
        </FormField>
        <FormField error={fieldErrors.duration_minutes} htmlFor="ilaw-duration" label="Minutes">
          <input className={inputClass} id="ilaw-duration" max="480" min="1" onChange={set('duration_minutes')} type="number" value={form.duration_minutes} />
        </FormField>
      </div>
      <FormField error={fieldErrors.description} hint="What was done? The goal suggestions are based on the title and this description." htmlFor="ilaw-desc" label="Activity description">
        <textarea className={`${inputClass} min-h-20`} id="ilaw-desc" maxLength={5000} onChange={set('description')} required value={form.description} />
      </FormField>
      <div className="grid gap-3 sm:grid-cols-2">
        <FormField htmlFor="ilaw-response" label="Learner's response / performance">
          <textarea className={`${inputClass} min-h-16`} id="ilaw-response" maxLength={5000} onChange={set('learner_response')} placeholder="e.g. Solved 6 of 10 with prompts" value={form.learner_response} />
        </FormField>
        <FormField htmlFor="ilaw-materials" label="Materials">
          <textarea className={`${inputClass} min-h-16`} id="ilaw-materials" maxLength={2000} onChange={set('materials')} value={form.materials} />
        </FormField>
      </div>
      <FormField htmlFor="ilaw-notes" label="Notes">
        <textarea className={`${inputClass} min-h-12`} id="ilaw-notes" maxLength={5000} onChange={set('notes')} value={form.notes} />
      </FormField>
      {error && <Alert>{error}</Alert>}
      <div className="flex gap-2">
        <button className={primaryButtonClass} disabled={saving} type="submit">{saving ? 'Saving…' : entry ? 'Save changes' : 'Log activity'}</button>
        <button className={secondaryButtonClass} onClick={onCancel} type="button">Cancel</button>
      </div>
    </form>
  )
}
