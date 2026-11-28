import { useState } from 'react'

import Alert from '../../shared/components/Alert'
import { inputClass, primaryButtonClass, secondaryButtonClass } from '../../shared/forms/styles'
import { getErrorMessage } from '../../shared/utils/apiError'
import { EVIDENCE_LABELS, GRADING_PERIODS, METHOD_RULES } from './constants'

const todayIn = (period) => {
  const d = new Date()
  let iso = new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10)
  if (period?.end && iso > period.end) iso = period.end
  if (period?.start && iso < period.start) iso = period.start
  return iso
}

function clientCheck(kind, goal, form) {
  const errors = {}
  if (kind === 'grade') {
    if (!form.subject.trim()) errors.subject = 'Enter the subject.'
    if (!form.grading_period) errors.grading_period = 'Choose the grading period.'
    const v = Number(form.value)
    if (form.value === '' || v < 0 || v > 100) errors.value = 'Enter a grade from 0 to 100.'
    return errors
  }
  if (kind === 'observation' && !form.note.trim()) errors.note = 'Describe what was observed.'
  const needsValue = kind !== 'observation' || form.value !== '' || (form.correct !== '' && form.total !== '')
  if (!goal || !needsValue) return errors
  const rule = METHOD_RULES[goal.measurement_method]
  if (!rule) return errors
  const usingCT = rule.allowCorrectTotal && form.mode === 'ct'
  if (usingCT) {
    const c = Number(form.correct)
    const t = Number(form.total)
    if (form.correct === '' || form.total === '' || t <= 0) errors.correct = 'Enter correct answers and the total.'
    else if (c < 0 || c > t) errors.correct = 'Correct answers must be between 0 and the total.'
    return errors
  }
  const v = Number(form.value)
  if (form.value === '') errors.value = 'Enter the measured value.'
  else if ((rule.exclusiveMin ? v <= rule.min : v < rule.min) || v > rule.max) errors.value = `Enter a value ${rule.exclusiveMin ? '>' : '≥'} ${rule.min} and ≤ ${rule.max}.`
  else if (rule.integer && !Number.isInteger(v)) errors.value = 'Enter a whole number.'
  if (rule.needsOutOf) {
    const o = Number(form.out_of)
    if (form.out_of === '' || o <= 0) errors.out_of = 'Enter how many trials were given.'
    else if (v > o) errors.value = 'Successful trials cannot exceed the number of trials.'
  }
  return errors
}

/**
 * Add evidence. `kind` = probe | work_sample | test (measured, needs a goal) | observation | grade.
 * The value fields follow the chosen goal's measurement method.
 */
export default function ProgressEntryForm({ kind: initialKind, goals, fixedGoalId, period, ilawEntries = [], onSubmit, onCancel }) {
  const [kind, setKind] = useState(initialKind)
  const [form, setForm] = useState({
    iep_goal_id: fixedGoalId ? String(fixedGoalId) : '',
    recorded_on: todayIn(period), value: '', out_of: '', correct: '', total: '', mode: 'value',
    note: '', subject: '', grading_period: '', ilaw_entry_id: '',
  })
  const [errors, setErrors] = useState({})
  const [serverError, setServerError] = useState(null)
  const [saving, setSaving] = useState(false)
  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }))
  const goal = goals.find((g) => String(g.goal.id) === form.iep_goal_id)?.goal
  const rule = goal ? METHOD_RULES[goal.measurement_method] : null
  const measured = ['probe', 'work_sample', 'test'].includes(kind)

  const submit = async (e) => {
    e.preventDefault()
    const found = clientCheck(kind, goal, form)
    if (measured && !goal) found.iep_goal_id = 'Choose the goal this evidence measures.'
    setErrors(found)
    if (Object.keys(found).length) return
    setSaving(true)
    setServerError(null)
    const num = (v) => (v === '' ? null : Number(v))
    const payload = {
      evidence_type: kind,
      recorded_on: form.recorded_on,
      iep_goal_id: form.iep_goal_id ? Number(form.iep_goal_id) : null,
      ilaw_entry_id: form.ilaw_entry_id ? Number(form.ilaw_entry_id) : null,
      note: form.note || null,
    }
    if (kind === 'grade') Object.assign(payload, { subject: form.subject, grading_period: form.grading_period, value: num(form.value) })
    else if (rule?.allowCorrectTotal && form.mode === 'ct') Object.assign(payload, { correct: num(form.correct), total: num(form.total) })
    else Object.assign(payload, { value: num(form.value), out_of: rule?.needsOutOf ? num(form.out_of) : null })
    try {
      await onSubmit(payload)
    } catch (err) {
      const details = err?.response?.data?.error?.details ?? []
      setErrors(Object.fromEntries(details.map((d) => [d.field, d.message])))
      setServerError(getErrorMessage(err))
      setSaving(false)
    }
  }

  const field = (label, name, input, hint) => (
    <label className="block text-xs font-medium text-slate-600">
      {label}
      {input}
      {hint && !errors[name] && <span className="mt-0.5 block font-normal text-slate-500">{hint}</span>}
      {errors[name] && <span className="mt-0.5 block font-normal text-red-600">{errors[name]}</span>}
    </label>
  )

  return (
    <form className="space-y-3 rounded-lg border border-indigo-200 bg-indigo-50/30 p-3" onSubmit={submit}>
      {!fixedGoalId && kind !== 'grade' && kind !== 'observation' && (
        <div className="flex flex-wrap gap-1">
          {['probe', 'work_sample', 'test'].map((k) => (
            <button className={`${k === kind ? primaryButtonClass : secondaryButtonClass} px-2 py-1 text-xs`} key={k} onClick={() => setKind(k)} type="button">{EVIDENCE_LABELS[k]}</button>
          ))}
        </div>
      )}
      {fixedGoalId && (
        <select aria-label="Evidence type" className={`${inputClass} mt-0 w-auto py-1 text-sm`} onChange={(e) => setKind(e.target.value)} value={kind}>
          {['probe', 'work_sample', 'test', 'observation'].map((k) => <option key={k} value={k}>{EVIDENCE_LABELS[k]}</option>)}
        </select>
      )}
      <div className="grid gap-3 sm:grid-cols-[10rem_1fr]">
        {field('Date', 'recorded_on', <input className={`${inputClass} text-sm`} max={todayIn(period)} min={period?.start} onChange={set('recorded_on')} required type="date" value={form.recorded_on} />)}
        {!fixedGoalId && field(kind === 'grade' || kind === 'observation' ? 'IEP goal (optional)' : 'IEP goal', 'iep_goal_id',
          <select className={`${inputClass} text-sm`} onChange={set('iep_goal_id')} value={form.iep_goal_id}>
            <option value="">{measured ? 'Choose a goal…' : 'Not linked to a goal'}</option>
            {goals.map((g) => <option key={g.goal.id} value={g.goal.id}>Goal {g.goal.number}: {g.goal.statement.slice(0, 90)}</option>)}
          </select>)}
      </div>

      {kind === 'grade' ? (
        <div className="grid gap-3 sm:grid-cols-3">
          {field('Subject', 'subject', <input className={`${inputClass} text-sm`} maxLength={60} onChange={set('subject')} placeholder="e.g. Mathematics" value={form.subject} />)}
          {field('Grading period', 'grading_period',
            <select className={`${inputClass} text-sm`} onChange={set('grading_period')} value={form.grading_period}>
              <option value="">Choose…</option>
              {GRADING_PERIODS.map((p) => <option key={p} value={p}>{p === 'final' ? 'Final' : p}</option>)}
            </select>)}
          {field('Grade (0–100)', 'value', <input className={`${inputClass} text-sm`} max="100" min="0" onChange={set('value')} step="any" type="number" value={form.value} />)}
        </div>
      ) : goal && rule ? (
        <div className="space-y-2">
          {rule.allowCorrectTotal && (
            <div className="flex gap-3 text-xs text-slate-600">
              <label className="flex items-center gap-1"><input checked={form.mode === 'value'} onChange={() => setForm((f) => ({ ...f, mode: 'value' }))} type="radio" />Enter a percent</label>
              <label className="flex items-center gap-1"><input checked={form.mode === 'ct'} onChange={() => setForm((f) => ({ ...f, mode: 'ct' }))} type="radio" />Correct / total</label>
            </div>
          )}
          {rule.allowCorrectTotal && form.mode === 'ct' ? (
            <div className="grid gap-3 sm:grid-cols-2">
              {field('Correct', 'correct', <input className={`${inputClass} text-sm`} min="0" onChange={set('correct')} step="1" type="number" value={form.correct} />)}
              {field('Total', 'total', <input className={`${inputClass} text-sm`} min="1" onChange={set('total')} step="1" type="number" value={form.total} />, 'Saved as a percentage.')}
            </div>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2">
              {field(`${rule.label}${kind === 'observation' ? ' (optional)' : ''}`, 'value',
                <input className={`${inputClass} text-sm`} max={rule.max} min={rule.min} onChange={set('value')} step={rule.step} type="number" value={form.value} />,
                `Goal target: ${goals.find((g) => g.goal.id === goal.id)?.target_value ?? '—'} (${goal.target_unit})`)}
              {rule.needsOutOf && field('Out of (trials given)', 'out_of', <input className={`${inputClass} text-sm`} max="50" min="1" onChange={set('out_of')} step="1" type="number" value={form.out_of} />)}
            </div>
          )}
        </div>
      ) : measured ? (
        <p className="text-xs text-slate-500">Choose a goal to enter its measured value.</p>
      ) : null}

      {ilawEntries.length > 0 && kind !== 'grade' && field('From an ILAW activity (optional)', 'ilaw_entry_id',
        <select className={`${inputClass} text-sm`} onChange={set('ilaw_entry_id')} value={form.ilaw_entry_id}>
          <option value="">—</option>
          {ilawEntries.map((e) => <option key={e.id} value={e.id}>{e.activity_date} · {e.title}</option>)}
        </select>)}
      {field(kind === 'observation' ? 'What was observed' : 'Note (optional)', 'note',
        <textarea className={`${inputClass} min-h-14 text-sm`} maxLength={5000} onChange={set('note')} value={form.note} />)}
      {serverError && <Alert>{serverError}</Alert>}
      <div className="flex gap-2">
        <button className={`${primaryButtonClass} px-3 py-1 text-sm`} disabled={saving} type="submit">{saving ? 'Saving…' : 'Save'}</button>
        <button className={`${secondaryButtonClass} px-3 py-1 text-sm`} onClick={onCancel} type="button">Cancel</button>
      </div>
    </form>
  )
}
