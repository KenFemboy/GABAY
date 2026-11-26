import { useState } from 'react'

import Alert from '../../shared/components/Alert'
import FormField from '../../shared/forms/FormField'
import { inputClass, primaryButtonClass, secondaryButtonClass } from '../../shared/forms/styles'
import { getErrorMessage } from '../../shared/utils/apiError'
import { GRADE_BANDS, MEASUREMENT_METHODS, measurabilityHints, TARGET_UNITS } from './constants'

const EMPTY = {
  domain_id: '',
  skill_id: '',
  statement: '',
  measurement_method: 'percent_accuracy',
  target_value: '',
  target_unit: 'percent',
  criterion: '',
  grade_band: 'any',
  change_note: '',
}

function fromGoal(goal) {
  if (!goal) return EMPTY
  const v = goal.current_version
  return {
    domain_id: String(v.domain.id),
    skill_id: String(v.skill.id),
    statement: v.statement,
    measurement_method: v.measurement_method,
    target_value: String(v.target_value),
    target_unit: v.target_unit,
    criterion: v.criterion ?? '',
    grade_band: v.grade_band,
    change_note: '',
  }
}

/** Create or edit a goal. `goal` is the goal detail when editing. */
export default function GoalForm({ goal, taxonomy, onCancel, onSubmit }) {
  const [form, setForm] = useState(() => fromGoal(goal))
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)
  const [fieldErrors, setFieldErrors] = useState({})

  const domains = taxonomy.filter((d) => d.is_active || String(d.id) === form.domain_id)
  const domain = taxonomy.find((d) => String(d.id) === form.domain_id)
  const skills = (domain?.skills ?? []).filter((s) => s.is_active || String(s.id) === form.skill_id)
  const hints = measurabilityHints(form.statement)
  const inUse = goal?.in_use

  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }))

  const submit = async (e) => {
    e.preventDefault()
    setError(null)
    setFieldErrors({})
    setSaving(true)
    const payload = {
      domain_id: Number(form.domain_id),
      skill_id: Number(form.skill_id),
      statement: form.statement,
      measurement_method: form.measurement_method,
      target_value: Number(form.target_value),
      target_unit: form.target_unit,
      criterion: form.criterion || null,
      grade_band: form.grade_band,
      change_note: form.change_note || null,
    }
    try {
      await onSubmit(payload)
    } catch (err) {
      const details = err?.response?.data?.error?.details ?? []
      setFieldErrors(Object.fromEntries(details.map((d) => [d.field, d.message])))
      setError(getErrorMessage(err))
      setSaving(false)
    }
  }

  return (
    <form className="space-y-4" onSubmit={submit}>
      {inUse && (
        <Alert tone="info">
          This goal is used (for example in an IEP). Saving changes creates version {goal.current_version.version_number + 1};
          places that use version {goal.current_version.version_number} keep the old wording.
        </Alert>
      )}
      <div className="grid gap-4 sm:grid-cols-2">
        <FormField error={fieldErrors.domain_id} htmlFor="g-domain" label="Domain">
          <select
            className={inputClass}
            id="g-domain"
            onChange={(e) => setForm((f) => ({ ...f, domain_id: e.target.value, skill_id: '' }))}
            required
            value={form.domain_id}
          >
            <option value="">Choose a domain</option>
            {domains.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
          </select>
        </FormField>
        <FormField error={fieldErrors.skill_id} htmlFor="g-skill" label="Skill">
          <select className={inputClass} disabled={!domain} id="g-skill" onChange={set('skill_id')} required value={form.skill_id}>
            <option value="">Choose a skill</option>
            {skills.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        </FormField>
      </div>

      <FormField
        error={fieldErrors.statement}
        hint="Condition + behavior + criterion, e.g. “Given 20 CVC words, the learner will decode them with 80% accuracy in 3 consecutive probes.”"
        htmlFor="g-statement"
        label="Goal statement"
      >
        <textarea className={`${inputClass} min-h-24`} id="g-statement" maxLength={2000} onChange={set('statement')} required value={form.statement} />
      </FormField>
      {hints.length > 0 && (
        <ul className="list-disc space-y-0.5 pl-5 text-xs text-amber-700">
          {hints.map((h) => <li key={h}>{h}</li>)}
        </ul>
      )}

      <div className="grid gap-4 sm:grid-cols-3">
        <FormField error={fieldErrors.measurement_method} htmlFor="g-method" label="Measurement method">
          <select className={inputClass} id="g-method" onChange={set('measurement_method')} value={form.measurement_method}>
            {MEASUREMENT_METHODS.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
          </select>
        </FormField>
        <FormField error={fieldErrors.target_value} htmlFor="g-target" label="Target">
          <input className={inputClass} id="g-target" min="0" onChange={set('target_value')} required step="any" type="number" value={form.target_value} />
        </FormField>
        <FormField error={fieldErrors.target_unit} htmlFor="g-unit" label="Unit">
          <select className={inputClass} id="g-unit" onChange={set('target_unit')} value={form.target_unit}>
            {TARGET_UNITS.map((u) => <option key={u.value} value={u.value}>{u.label}</option>)}
          </select>
        </FormField>
      </div>

      <div className="grid gap-4 sm:grid-cols-[2fr_1fr]">
        <FormField error={fieldErrors.criterion} hint="e.g. “in 4 of 5 trials across 3 sessions”" htmlFor="g-criterion" label="Criterion (optional)">
          <input className={inputClass} id="g-criterion" maxLength={300} onChange={set('criterion')} value={form.criterion} />
        </FormField>
        <FormField error={fieldErrors.grade_band} htmlFor="g-band" label="Grade band">
          <select className={inputClass} id="g-band" onChange={set('grade_band')} value={form.grade_band}>
            {GRADE_BANDS.map((g) => <option key={g.value} value={g.value}>{g.label}</option>)}
          </select>
        </FormField>
      </div>

      <FormField error={fieldErrors.change_note} htmlFor="g-note" label="Change note (optional)">
        <input className={inputClass} id="g-note" maxLength={300} onChange={set('change_note')} placeholder={goal ? 'Why is this goal changing?' : ''} value={form.change_note} />
      </FormField>

      {error && <Alert>{error}</Alert>}
      <div className="flex gap-2">
        <button className={primaryButtonClass} disabled={saving} type="submit">{saving ? 'Saving…' : goal ? 'Save changes' : 'Create draft goal'}</button>
        <button className={secondaryButtonClass} onClick={onCancel} type="button">Cancel</button>
      </div>
    </form>
  )
}
