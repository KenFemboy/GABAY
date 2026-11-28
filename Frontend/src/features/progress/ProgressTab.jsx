import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { listEntries } from '../../api/ilawApi'
import { createProgress, deleteProgress, getGoalProgress } from '../../api/progressApi'
import useAuth from '../../auth/useAuth'
import ProgressChart from '../../shared/charts/ProgressChart'
import Alert from '../../shared/components/Alert'
import { primaryButtonClass, secondaryButtonClass } from '../../shared/forms/styles'
import { getErrorMessage } from '../../shared/utils/apiError'
import { DOMAIN_LABELS } from '../assessments/constants'
import { EVIDENCE_LABELS, PROGRESS_WRITER_ROLES, STATUS } from './constants'
import ProgressEntryForm from './ProgressEntryForm'
import Timeline from './Timeline'

const UNIT = { percent: '%', trials: ' trials', count: '', minutes: ' min', wpm: ' wpm', level: '' }
const fmt = (v, unit) => (v == null ? '—' : `${Number.isInteger(v) ? v : v.toFixed(1)}${UNIT[unit] ?? ''}`)

export function StatusBadge({ status }) {
  const info = STATUS[status] ?? { label: status, icon: '·', className: 'bg-slate-100 text-slate-700 border-slate-300' }
  return (
    <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium ${info.className}`}>
      <span aria-hidden="true">{info.icon}</span>{info.label}
    </span>
  )
}

function GoalCard({ gp, period, canWrite, ilawEntries, onSaved, onDelete }) {
  const [adding, setAdding] = useState(false)
  const s = gp.status
  const unit = gp.goal.target_unit
  return (
    <li className="space-y-3 rounded-xl border border-slate-200 bg-white p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
            <span className="text-sm font-semibold text-slate-900">Goal {gp.goal.number}</span>
            {gp.goal.goal_code && <span className="font-mono">{gp.goal.goal_code}</span>}
            {gp.goal.domain && <span>{DOMAIN_LABELS[gp.goal.domain]}</span>}
            <StatusBadge status={s.status} />
          </div>
          <p className="mt-1 text-sm text-slate-800">{gp.goal.statement}</p>
        </div>
        <dl className="grid grid-cols-3 gap-4 text-right text-xs">
          <div><dt className="text-slate-500">Latest</dt><dd className="text-base font-semibold text-slate-900">{fmt(s.latest, unit)}</dd></div>
          <div><dt className="text-slate-500">Aim now</dt><dd className="text-base font-semibold text-slate-900">{fmt(s.expected, unit)}</dd></div>
          <div><dt className="text-slate-500">Target</dt><dd className="text-base font-semibold text-slate-900">{fmt(gp.target_value, unit)}</dd></div>
        </dl>
      </div>
      {s.status === 'no_baseline' && (
        <p className="text-xs text-slate-500">This goal has no numeric baseline value in the IEP, so the aim line can't be drawn. Data points are still charted.</p>
      )}
      <ProgressChart data={gp} evidenceLabels={EVIDENCE_LABELS} />
      {gp.other.length > 0 && (
        <ul className="space-y-1 text-xs text-slate-600">
          {gp.other.map((r) => (
            <li key={r.id}>
              {r.recorded_on} · {EVIDENCE_LABELS[r.evidence_type]}
              {r.evidence_type === 'grade' && ` · ${r.subject} ${r.grading_period}: ${r.value}`}
              {r.note && ` · ${r.note}`}
            </li>
          ))}
        </ul>
      )}
      {canWrite && (adding ? (
        <ProgressEntryForm
          fixedGoalId={gp.goal.id}
          goals={[gp]}
          ilawEntries={ilawEntries}
          kind="probe"
          onCancel={() => setAdding(false)}
          onSubmit={async (payload) => { await onSaved(payload); setAdding(false) }}
          period={period}
        />
      ) : (
        <div className="flex flex-wrap gap-2">
          <button className={`${primaryButtonClass} px-3 py-1 text-sm`} onClick={() => setAdding(true)} type="button">Add data point</button>
          {gp.points.length > 0 && (
            <button
              className={`${secondaryButtonClass} px-3 py-1 text-xs`}
              onClick={() => { const last = gp.points.at(-1); if (window.confirm(`Delete the data point of ${last.recorded_on}?`)) onDelete(last.id) }}
              type="button"
            >
              Undo last point
            </button>
          )}
        </div>
      ))}
    </li>
  )
}

/** Learner profile → Progress tab. */
export default function ProgressTab({ learner, onChanged }) {
  const { user } = useAuth()
  const canWrite = PROGRESS_WRITER_ROLES.includes(user.role)
  const [data, setData] = useState(null)
  const [ilawEntries, setIlawEntries] = useState([])
  const [error, setError] = useState(null)
  const [message, setMessage] = useState(null)
  const [form, setForm] = useState(null) // 'grade' | 'observation' | null
  const [refreshKey, setRefreshKey] = useState(0)

  useEffect(() => {
    let active = true
    Promise.all([getGoalProgress(learner.id), listEntries(learner.id, { limit: 100 })])
      .then(([p, e]) => { if (active) { setData(p.data); setIlawEntries(e.data.items) } })
      .catch((err) => { if (active) setError(getErrorMessage(err)) })
    return () => { active = false }
  }, [learner.id, refreshKey])

  const refresh = useCallback(() => { setRefreshKey((k) => k + 1); onChanged?.() }, [onChanged])

  const save = async (payload) => {
    await createProgress(learner.id, payload)
    setMessage('Saved.')
    refresh()
  }

  if (error) return <div className="py-4"><Alert>{error}</Alert></div>
  if (!data) return <p className="py-4 text-slate-500">Loading…</p>

  if (!data.iep_id) {
    return (
      <div className="py-4">
        <Alert tone="info">
          This learner has no finalized IEP for {learner.school_year}. Finalize the IEP to start monitoring progress.{' '}
          <Link className="font-medium underline" to={`/learners/${learner.id}?tab=iep`}>Go to the IEP tab</Link>
        </Alert>
      </div>
    )
  }

  const first = data.goals[0]
  const period = first ? { start: first.start_date, end: first.target_date } : null
  const behind = data.goals.filter((g) => ['below_aim', 'no_recent_data', 'no_data'].includes(g.status.status)).length

  return (
    <div className="space-y-6 py-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-slate-600">
          Goals of the active IEP (v{data.iep_version}). The dashed line runs from the baseline to the target; a goal is flagged when the median of its last 3 points falls behind it.
          {behind > 0 && <strong className="ml-1 text-slate-900">{behind} goal{behind === 1 ? '' : 's'} need attention.</strong>}
        </p>
        {canWrite && !form && (
          <div className="flex gap-2">
            <button className={secondaryButtonClass} onClick={() => setForm('observation')} type="button">Add observation</button>
            <button className={secondaryButtonClass} onClick={() => setForm('grade')} type="button">Add grade</button>
          </div>
        )}
      </div>
      {message && <Alert tone="success">{message}</Alert>}
      {form && (
        <ProgressEntryForm
          goals={data.goals}
          ilawEntries={ilawEntries}
          key={form}
          kind={form}
          onCancel={() => setForm(null)}
          onSubmit={async (payload) => { await save(payload); setForm(null) }}
          period={period}
        />
      )}
      <ul className="space-y-4">
        {data.goals.map((gp) => (
          <GoalCard
            canWrite={canWrite}
            gp={gp}
            ilawEntries={ilawEntries}
            key={gp.goal.id}
            onDelete={async (id) => { try { await deleteProgress(id); setMessage('Data point deleted.'); refresh() } catch (err) { setError(getErrorMessage(err)) } }}
            onSaved={save}
            period={period}
          />
        ))}
      </ul>
      <Timeline goals={data.goals} learnerId={learner.id} refreshKey={refreshKey} />
    </div>
  )
}
