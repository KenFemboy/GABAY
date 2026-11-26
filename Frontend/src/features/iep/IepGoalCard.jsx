import { useState } from 'react'

import Alert from '../../shared/components/Alert'
import { inputClass, primaryButtonClass, secondaryButtonClass } from '../../shared/forms/styles'
import { getErrorMessage } from '../../shared/utils/apiError'
import { DOMAIN_LABELS } from '../assessments/constants'
import { MEASUREMENT_METHODS, TARGET_UNITS } from '../goals/constants'
import { GOAL_SOURCE_LABELS, quarterlyDates } from './constants'

const FIELDS = ['statement', 'baseline', 'baseline_value', 'measurement_method', 'target_value', 'target_unit',
  'criterion', 'responsible_staff', 'start_date', 'target_date', 'review_dates', 'addresses_finding_id']

function toForm(goal) {
  return Object.fromEntries(FIELDS.map((f) => {
    const v = goal[f]
    if (f === 'review_dates') return [f, [...(v ?? [])]]
    return [f, v == null ? '' : String(v)]
  }))
}

function toPayload(form) {
  const num = (v) => (v === '' ? null : Number(v))
  return {
    statement: form.statement,
    baseline: form.baseline || null,
    baseline_value: num(form.baseline_value),
    measurement_method: form.measurement_method || null,
    target_value: num(form.target_value),
    target_unit: form.target_unit || null,
    criterion: form.criterion || null,
    responsible_staff: form.responsible_staff || null,
    start_date: form.start_date || null,
    target_date: form.target_date || null,
    review_dates: form.review_dates.filter(Boolean),
    addresses_finding_id: form.addresses_finding_id === '' ? null : Number(form.addresses_finding_id),
  }
}

function Field({ label, children, issue, className = '' }) {
  return (
    <label className={`block text-xs font-medium text-slate-600 ${className}`}>
      {label}
      {children}
      {issue && <span className="mt-0.5 block font-normal text-red-600">{issue}</span>}
    </label>
  )
}

/** One IEP goal: read view, or an edit form on drafts. `issues` maps field -> message. */
export default function IepGoalCard({ goal, number, needs, period, readOnly, issues, onSave, onDelete, onMove, isFirst, isLast }) {
  const [editing, setEditing] = useState(false)
  const [form, setForm] = useState(() => toForm(goal))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }))
  const need = needs.find((n) => n.id === goal.addresses_finding_id)
  const hasIssues = Object.keys(issues).length > 0

  const save = async () => {
    setBusy(true)
    setError(null)
    try {
      await onSave(goal.id, toPayload(form))
      setEditing(false)
    } catch (err) {
      setError(getErrorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  const row = (label, value) => (
    <div className="grid grid-cols-[9rem_1fr] gap-2 py-1 text-sm">
      <dt className="text-slate-500">{label}</dt>
      <dd className="text-slate-900">{value || <span className="text-slate-400">—</span>}</dd>
    </div>
  )

  return (
    <li className={`rounded-xl border p-4 ${hasIssues && !readOnly ? 'border-amber-300 bg-amber-50/30' : 'border-slate-200 bg-white'}`} id={`goal-${goal.id}`}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span className="text-sm font-semibold text-slate-900">Goal {number}</span>
          {goal.goal_code && <span className="font-mono text-slate-600">{goal.goal_code}</span>}
          <span className="rounded-full bg-slate-100 px-2 py-0.5 text-slate-600">{GOAL_SOURCE_LABELS[goal.source]}{goal.match_score != null ? ` · ${Math.round(goal.match_score * 100)}% match` : ''}</span>
          {goal.domain && <span className="rounded-full bg-indigo-50 px-2 py-0.5 text-indigo-700">{DOMAIN_LABELS[goal.domain]}{goal.skill_name ? ` – ${goal.skill_name}` : ''}</span>}
        </div>
        {!readOnly && !editing && (
          <div className="flex gap-1">
            <button aria-label="Move up" className={`${secondaryButtonClass} px-2 py-0.5 text-xs`} disabled={isFirst} onClick={() => onMove(goal.id, -1)} type="button">↑</button>
            <button aria-label="Move down" className={`${secondaryButtonClass} px-2 py-0.5 text-xs`} disabled={isLast} onClick={() => onMove(goal.id, 1)} type="button">↓</button>
            <button className={`${secondaryButtonClass} px-2 py-0.5 text-xs`} onClick={() => { setForm(toForm(goal)); setEditing(true) }} type="button">Edit</button>
            <button className="px-2 text-xs font-medium text-red-600 hover:underline" onClick={() => { if (window.confirm('Remove this goal from the IEP?')) onDelete(goal.id) }} type="button">Remove</button>
          </div>
        )}
      </div>

      {!editing ? (
        <>
          <p className="mt-2 text-sm text-slate-900">{goal.statement}</p>
          <dl className="mt-2 divide-y divide-slate-100">
            {row('Need addressed', need?.text)}
            {row('Baseline', goal.baseline)}
            {row('Target', goal.target_value != null ? `${goal.target_value} ${TARGET_UNITS.find((u) => u.value === goal.target_unit)?.label ?? ''}${goal.criterion ? ` ${goal.criterion}` : ''}` : null)}
            {row('Measurement', MEASUREMENT_METHODS.find((m) => m.value === goal.measurement_method)?.label)}
            {row('Responsible staff', goal.responsible_staff)}
            {row('Start → target', goal.start_date || goal.target_date ? `${goal.start_date ?? '—'} → ${goal.target_date ?? '—'}` : null)}
            {row('Review dates', goal.review_dates.join(', '))}
          </dl>
          {hasIssues && !readOnly && (
            <ul className="mt-2 list-disc pl-5 text-xs text-amber-800">
              {Object.values(issues).map((m) => <li key={m}>{m}</li>)}
            </ul>
          )}
        </>
      ) : (
        <div className="mt-3 space-y-3">
          <Field issue={issues.statement} label="Goal statement">
            <textarea className={`${inputClass} min-h-20 text-sm`} maxLength={2000} onChange={set('statement')} value={form.statement} />
          </Field>
          <Field label="Need addressed">
            <select className={`${inputClass} text-sm`} onChange={set('addresses_finding_id')} value={form.addresses_finding_id}>
              <option value="">— none —</option>
              {needs.map((n) => <option key={n.id} value={n.id}>{n.text.slice(0, 100)}</option>)}
            </select>
          </Field>
          <div className="grid gap-3 sm:grid-cols-[1fr_8rem]">
            <Field issue={issues.baseline} label="Baseline (current performance)">
              <textarea className={`${inputClass} min-h-16 text-sm`} maxLength={2000} onChange={set('baseline')} value={form.baseline} />
            </Field>
            <Field label="Baseline value">
              <input className={`${inputClass} text-sm`} min="0" onChange={set('baseline_value')} step="any" type="number" value={form.baseline_value} />
            </Field>
          </div>
          <div className="grid gap-3 sm:grid-cols-4">
            <Field issue={issues.measurement_method} label="Measurement">
              <select className={`${inputClass} text-sm`} onChange={set('measurement_method')} value={form.measurement_method}>
                <option value="">Choose…</option>
                {MEASUREMENT_METHODS.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
              </select>
            </Field>
            <Field issue={issues.target_value} label="Target">
              <input className={`${inputClass} text-sm`} min="0" onChange={set('target_value')} step="any" type="number" value={form.target_value} />
            </Field>
            <Field label="Unit">
              <select className={`${inputClass} text-sm`} onChange={set('target_unit')} value={form.target_unit}>
                <option value="">Choose…</option>
                {TARGET_UNITS.map((u) => <option key={u.value} value={u.value}>{u.label}</option>)}
              </select>
            </Field>
            <Field label="Criterion">
              <input className={`${inputClass} text-sm`} maxLength={300} onChange={set('criterion')} placeholder="in 4 of 5 trials" value={form.criterion} />
            </Field>
          </div>
          <Field issue={issues.responsible_staff} label="Responsible staff">
            <input className={`${inputClass} text-sm`} maxLength={500} onChange={set('responsible_staff')} placeholder="e.g. Ms. Reyes (SPED teacher); parent" value={form.responsible_staff} />
          </Field>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field issue={issues.start_date} label="Start date">
              <input className={`${inputClass} text-sm`} onChange={set('start_date')} type="date" value={form.start_date} />
            </Field>
            <Field issue={issues.target_date} label="Target date">
              <input className={`${inputClass} text-sm`} onChange={set('target_date')} type="date" value={form.target_date} />
            </Field>
          </div>
          <div>
            <span className="text-xs font-medium text-slate-600">Progress review dates</span>
            {issues.review_dates && <span className="block text-xs text-red-600">{issues.review_dates}</span>}
            <div className="mt-1 flex flex-wrap gap-2">
              {form.review_dates.map((d, i) => (
                <span className="inline-flex items-center gap-1" key={i}>
                  <input aria-label={`Review date ${i + 1}`} className={`${inputClass} mt-0 w-40 py-1 text-sm`} onChange={(e) => setForm((f) => ({ ...f, review_dates: f.review_dates.map((x, j) => (j === i ? e.target.value : x)) }))} type="date" value={d} />
                  <button aria-label={`Remove review date ${i + 1}`} className="text-xs text-red-600" onClick={() => setForm((f) => ({ ...f, review_dates: f.review_dates.filter((_, j) => j !== i) }))} type="button">×</button>
                </span>
              ))}
              {form.review_dates.length < 12 && (
                <button className={`${secondaryButtonClass} px-2 py-1 text-xs`} onClick={() => setForm((f) => ({ ...f, review_dates: [...f.review_dates, ''] }))} type="button">+ Date</button>
              )}
              <button
                className={`${secondaryButtonClass} px-2 py-1 text-xs`}
                onClick={() => setForm((f) => ({ ...f, review_dates: quarterlyDates(f.start_date || period.start, f.target_date || period.end) }))}
                type="button"
              >
                Quarterly dates
              </button>
            </div>
          </div>
          {error && <Alert>{error}</Alert>}
          <div className="flex gap-2">
            <button className={`${primaryButtonClass} px-3 py-1 text-sm`} disabled={busy || form.statement.trim().length < 10} onClick={save} type="button">{busy ? 'Saving…' : 'Save goal'}</button>
            <button className={`${secondaryButtonClass} px-3 py-1 text-sm`} onClick={() => setEditing(false)} type="button">Cancel</button>
          </div>
        </div>
      )}
    </li>
  )
}
