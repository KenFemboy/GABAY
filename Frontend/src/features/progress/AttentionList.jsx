import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { getAttention } from '../../api/progressApi'
import Alert from '../../shared/components/Alert'
import { getErrorMessage } from '../../shared/utils/apiError'
import { StatusBadge } from './ProgressTab'
import { STATUS } from './constants'

const FILTERS = ['below_aim', 'no_recent_data', 'no_data', 'no_baseline']
const UNIT = { percent: '%', trials: ' trials', count: '', minutes: ' min', wpm: ' wpm', level: '' }
const fmt = (v, unit) => (v == null ? '—' : `${Number.isInteger(v) ? v : v.toFixed(1)}${UNIT[unit] ?? ''}`)

/** Goals of active IEPs that are behind the aim line or missing data (Coordinator / School Head). */
export default function AttentionList({ compact = false }) {
  const [selected, setSelected] = useState(new Set(FILTERS))
  const [rows, setRows] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    let active = true
    getAttention({ status: [...selected].join(',') })
      .then(({ data }) => { if (active) setRows(data.items) })
      .catch((err) => { if (active) setError(getErrorMessage(err)) })
    return () => { active = false }
  }, [selected])

  const toggle = (s) => setSelected((prev) => {
    const next = new Set(prev)
    if (next.has(s)) next.delete(s)
    else next.add(s)
    return next.size ? next : new Set(FILTERS)
  })
  const shown = compact ? (rows ?? []).slice(0, 8) : rows ?? []

  return (
    <section className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-lg font-semibold text-slate-900">Goals needing attention</h2>
        {compact && <Link className="text-sm text-indigo-600 hover:underline" to="/progress/attention">See all</Link>}
      </div>
      <div className="flex flex-wrap gap-1">
        {FILTERS.map((s) => (
          <button
            aria-pressed={selected.has(s)}
            className={`rounded-full border px-2.5 py-1 text-xs ${selected.has(s) ? 'border-indigo-300 bg-indigo-50 text-indigo-800' : 'border-slate-200 text-slate-500'}`}
            key={s}
            onClick={() => toggle(s)}
            type="button"
          >
            <span aria-hidden="true">{STATUS[s].icon}</span> {STATUS[s].label}
          </button>
        ))}
      </div>
      {error && <Alert>{error}</Alert>}
      {rows && rows.length === 0 && <p className="text-sm text-slate-500">No goals need attention right now.</p>}
      {shown.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
          <table className="min-w-full text-left text-sm">
            <thead className="bg-slate-50 text-xs text-slate-600">
              <tr>
                <th className="px-3 py-2 font-medium">Learner</th>
                <th className="px-3 py-2 font-medium">Goal</th>
                <th className="px-3 py-2 font-medium">Status</th>
                <th className="px-3 py-2 text-right font-medium">Latest</th>
                <th className="px-3 py-2 text-right font-medium">Aim</th>
                <th className="px-3 py-2 text-right font-medium">Target</th>
                <th className="px-3 py-2 font-medium">Last data</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {shown.map((r) => {
                const p = r.progress
                const unit = p.goal.target_unit
                return (
                  <tr key={`${r.learner_id}-${p.goal.id}`}>
                    <td className="px-3 py-2">
                      <Link className="font-medium text-indigo-700 hover:underline" to={`/learners/${r.learner_id}?tab=progress`}>{r.learner_name}</Link>
                      <div className="text-xs text-slate-500">{r.learner_code} · Grade {r.grade_level} {r.section}</div>
                    </td>
                    <td className="max-w-md px-3 py-2"><span className="font-medium">Goal {p.goal.number}:</span> <span className="text-slate-700">{p.goal.statement.slice(0, 110)}{p.goal.statement.length > 110 ? '…' : ''}</span></td>
                    <td className="px-3 py-2"><StatusBadge status={p.status.status} /></td>
                    <td className="px-3 py-2 text-right tabular-nums">{fmt(p.status.latest, unit)}</td>
                    <td className="px-3 py-2 text-right tabular-nums">{fmt(p.status.expected, unit)}</td>
                    <td className="px-3 py-2 text-right tabular-nums">{fmt(p.target_value, unit)}</td>
                    <td className="px-3 py-2 text-xs text-slate-600">{p.status.last_recorded_on ?? '—'}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
