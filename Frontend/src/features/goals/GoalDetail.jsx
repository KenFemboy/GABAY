import { useEffect, useState } from 'react'

import { activateGoal, archiveGoal, deleteGoal, getGoal, updateGoal } from '../../api/goalsApi'
import Alert from '../../shared/components/Alert'
import { primaryButtonClass, secondaryButtonClass } from '../../shared/forms/styles'
import { getErrorMessage } from '../../shared/utils/apiError'
import { formatTarget, GOAL_STATUS, GRADE_BAND_LABELS, METHOD_LABELS } from './constants'
import GoalForm from './GoalForm'

export function GoalStatusBadge({ status }) {
  const info = GOAL_STATUS[status] ?? { label: status, className: 'bg-slate-200 text-slate-700' }
  return <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${info.className}`}>{info.label}</span>
}

function VersionBlock({ version, current }) {
  return (
    <div className={`rounded-lg border p-3 ${current ? 'border-indigo-200 bg-indigo-50/40' : 'border-slate-200'}`}>
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-slate-500">
        <span className="font-medium text-slate-700">Version {version.version_number}{current ? ' (current)' : ''}</span>
        <span>{version.created_by_name} · {new Date(version.created_at).toLocaleDateString()}{version.usage_count > 0 && ` · used ${version.usage_count}×`}</span>
      </div>
      <p className="mt-1 text-sm text-slate-900">{version.statement}</p>
      <p className="mt-1 text-xs text-slate-600">
        {version.domain.name} → {version.skill.name} · {METHOD_LABELS[version.measurement_method]} · target {formatTarget(version)}
        {version.criterion && <> · {version.criterion}</>} · {GRADE_BAND_LABELS[version.grade_band]}
      </p>
      {version.change_note && <p className="mt-1 text-xs italic text-slate-500">“{version.change_note}”</p>}
    </div>
  )
}

/** Modal with the goal's details, history and (for the Coordinator) actions. */
export default function GoalDetail({ goalId, taxonomy, canManage, onClose, onChanged }) {
  const [goal, setGoal] = useState(null)
  const [error, setError] = useState(null)
  const [editing, setEditing] = useState(false)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState(null)

  useEffect(() => {
    let active = true
    getGoal(goalId)
      .then(({ data }) => { if (active) setGoal(data) })
      .catch((err) => { if (active) setError(getErrorMessage(err)) })
    return () => { active = false }
  }, [goalId])

  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const act = async (fn, text) => {
    setBusy(true)
    setError(null)
    try {
      const { data } = await fn()
      if (data) setGoal(data)
      setMessage(text)
      onChanged()
    } catch (err) {
      setError(getErrorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  const save = async (payload) => {
    const { data } = await updateGoal(goalId, payload)
    setGoal(data.goal)
    setEditing(false)
    setMessage(data.new_version ? `Saved as version ${data.goal.current_version.version_number}.` : 'Changes saved.')
    onChanged()
  }

  const remove = async () => {
    if (!window.confirm('Delete this draft goal permanently?')) return
    setBusy(true)
    try {
      await deleteGoal(goalId)
      onChanged()
      onClose()
    } catch (err) {
      setError(getErrorMessage(err))
      setBusy(false)
    }
  }

  return (
    <div aria-modal="true" className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-slate-900/50 p-4" onClick={onClose} role="dialog">
      <div className="my-8 w-full max-w-3xl rounded-xl bg-white shadow-xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b border-slate-200 px-5 py-3">
          <h2 className="font-semibold text-slate-900">
            {goal ? <>{goal.code} <GoalStatusBadge status={goal.status} /></> : 'Goal'}
          </h2>
          <button className={`${secondaryButtonClass} px-3 py-1 text-sm`} onClick={onClose} type="button">Close</button>
        </div>
        <div className="space-y-4 p-5">
          {error && <Alert>{error}</Alert>}
          {message && <Alert tone="success">{message}</Alert>}
          {!goal && !error && <p className="text-slate-500">Loading…</p>}
          {goal && editing && (
            <GoalForm goal={goal} onCancel={() => setEditing(false)} onSubmit={save} taxonomy={taxonomy} />
          )}
          {goal && !editing && (
            <>
              <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
                <span>Created by {goal.created_by_name}</span>
                {goal.in_use && <span className="rounded-full bg-indigo-50 px-2 py-0.5 text-indigo-700">In use</span>}
                {goal.status === 'active' && (
                  <span className={`rounded-full px-2 py-0.5 ${goal.indexed ? 'bg-emerald-50 text-emerald-700' : 'bg-amber-50 text-amber-700'}`}>
                    {goal.indexed ? 'Indexed for matching' : 'Not indexed yet'}
                  </span>
                )}
              </div>
              {canManage && (
                <div className="flex flex-wrap gap-2">
                  {goal.status !== 'archived' && (
                    <button className={`${secondaryButtonClass} px-3 py-1 text-sm`} disabled={busy} onClick={() => setEditing(true)} type="button">Edit</button>
                  )}
                  {goal.status !== 'active' && (
                    <button className={`${primaryButtonClass} px-3 py-1 text-sm`} disabled={busy} onClick={() => act(() => activateGoal(goalId), 'Goal activated.')} type="button">Activate</button>
                  )}
                  {goal.status !== 'archived' && (
                    <button className={`${secondaryButtonClass} px-3 py-1 text-sm`} disabled={busy} onClick={() => act(() => archiveGoal(goalId), 'Goal archived.')} type="button">Archive</button>
                  )}
                  {goal.status === 'draft' && !goal.in_use && (
                    <button className="px-3 py-1 text-sm font-medium text-red-600 hover:underline" disabled={busy} onClick={remove} type="button">Delete draft</button>
                  )}
                </div>
              )}
              <div className="space-y-2">
                {goal.versions.map((v) => <VersionBlock current={v.id === goal.current_version.id} key={v.id} version={v} />)}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
