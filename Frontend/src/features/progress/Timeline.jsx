import { useEffect, useState } from 'react'

import { getTimeline } from '../../api/progressApi'
import Alert from '../../shared/components/Alert'
import { inputClass } from '../../shared/forms/styles'
import { getErrorMessage } from '../../shared/utils/apiError'
import { EVIDENCE_LABELS } from './constants'

const KINDS = ['ilaw', 'probe', 'work_sample', 'test', 'observation', 'grade']
const ICONS = { ilaw: '📘', probe: '📈', work_sample: '📝', test: '🧪', observation: '👁', grade: '🎓' }
const UNIT = { percent: '%', trials: ' trials', count: '', minutes: ' min', wpm: ' wpm', level: '', grade: '' }

function valueText(item) {
  if (item.value == null) return null
  const v = Number.isInteger(item.value) ? item.value : item.value.toFixed(1)
  return `${v}${UNIT[item.unit] ?? ''}${item.out_of ? ` of ${item.out_of}` : ''}`
}

/** Combined, filterable timeline of ILAW activities, measurements, observations and grades. */
export default function Timeline({ learnerId, goals, refreshKey }) {
  const [types, setTypes] = useState(new Set(KINDS))
  const [range, setRange] = useState({ from: '', to: '' })
  const [items, setItems] = useState(null)
  const [error, setError] = useState(null)
  const goalNumber = Object.fromEntries(goals.map((g) => [g.goal.id, g.goal.number]))

  useEffect(() => {
    let active = true
    const params = { types: [...types].join(',') }
    if (range.from) params.from = range.from
    if (range.to) params.to = range.to
    getTimeline(learnerId, params)
      .then(({ data }) => { if (active) setItems(data.items) })
      .catch((err) => { if (active) setError(getErrorMessage(err)) })
    return () => { active = false }
  }, [learnerId, types, range, refreshKey])

  const toggle = (kind) => setTypes((prev) => {
    const next = new Set(prev)
    if (next.has(kind)) next.delete(kind)
    else next.add(kind)
    return next.size ? next : new Set(KINDS)
  })

  const byMonth = []
  for (const item of items ?? []) {
    const label = new Date(`${item.date}T00:00:00`).toLocaleDateString(undefined, { month: 'long', year: 'numeric' })
    if (!byMonth.length || byMonth.at(-1).label !== label) byMonth.push({ label, items: [] })
    byMonth.at(-1).items.push(item)
  }

  return (
    <section className="space-y-3">
      <h2 className="font-semibold text-slate-900">Timeline</h2>
      <div className="flex flex-wrap items-end gap-2">
        {KINDS.map((k) => (
          <button
            aria-pressed={types.has(k)}
            className={`rounded-full border px-2.5 py-1 text-xs ${types.has(k) ? 'border-indigo-300 bg-indigo-50 text-indigo-800' : 'border-slate-200 text-slate-500'}`}
            key={k}
            onClick={() => toggle(k)}
            type="button"
          >
            <span aria-hidden="true">{ICONS[k]}</span> {EVIDENCE_LABELS[k]}
          </button>
        ))}
        <label className="text-xs text-slate-600">From<input className={`${inputClass} mt-0 py-1 text-xs`} onChange={(e) => setRange((r) => ({ ...r, from: e.target.value }))} type="date" value={range.from} /></label>
        <label className="text-xs text-slate-600">To<input className={`${inputClass} mt-0 py-1 text-xs`} onChange={(e) => setRange((r) => ({ ...r, to: e.target.value }))} type="date" value={range.to} /></label>
      </div>
      {error && <Alert>{error}</Alert>}
      {items && items.length === 0 && <p className="text-sm text-slate-500">Nothing recorded for these filters.</p>}
      {byMonth.map((month) => (
        <div key={month.label}>
          <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">{month.label}</h3>
          <ol className="space-y-1 border-l-2 border-slate-200 pl-4">
            {month.items.map((item) => (
              <li className="relative text-sm" key={`${item.kind}-${item.id}`}>
                <span aria-hidden="true" className="absolute -left-[1.4rem] top-0.5 text-xs">{ICONS[item.kind]}</span>
                <div className="flex flex-wrap items-baseline gap-x-2">
                  <span className="text-xs tabular-nums text-slate-500">{new Date(`${item.date}T00:00:00`).toLocaleDateString(undefined, { day: 'numeric', month: 'short' })}</span>
                  <span className="text-xs font-medium text-slate-600">{EVIDENCE_LABELS[item.kind]}</span>
                  {item.title && <span className="font-medium text-slate-900">{item.title}{item.grading_period ? ` (${item.grading_period})` : ''}</span>}
                  {valueText(item) && <span className="font-semibold tabular-nums text-slate-900">{valueText(item)}</span>}
                  {item.goal_ids.length > 0 && (
                    <span className="text-xs text-indigo-700">{item.goal_ids.map((id) => (goalNumber[id] ? `Goal ${goalNumber[id]}` : 'Earlier goal')).join(', ')}</span>
                  )}
                  <span className="text-xs text-slate-400">· {item.created_by_name}</span>
                </div>
                {item.summary && <p className="text-slate-700">{item.summary}</p>}
              </li>
            ))}
          </ol>
        </div>
      ))}
    </section>
  )
}
