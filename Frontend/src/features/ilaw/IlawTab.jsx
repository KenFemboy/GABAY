import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { createEntry, getActiveIep, listEntries } from '../../api/ilawApi'
import useAuth from '../../auth/useAuth'
import { ROLES } from '../../auth/roles'
import Alert from '../../shared/components/Alert'
import { inputClass, primaryButtonClass, secondaryButtonClass } from '../../shared/forms/styles'
import { getErrorMessage } from '../../shared/utils/apiError'
import IlawEntryCard from './IlawEntryCard'
import IlawEntryForm from './IlawEntryForm'

const WRITER_ROLES = [ROLES.SNED_COORDINATOR, ROLES.TEACHER]
const PAGE_SIZE = 20
const EMPTY_FILTERS = { from: '', to: '', goal: '' }

/** Learner profile → ILAW tab: daily learning activity log aligned with the active IEP. */
export default function IlawTab({ learner, onChanged }) {
  const { user } = useAuth()
  const canWrite = WRITER_ROLES.includes(user.role)
  const [iep, setIep] = useState(undefined) // undefined = loading, null = none
  const [data, setData] = useState({ items: [], total: 0 })
  const [filters, setFilters] = useState(EMPTY_FILTERS)
  const [offset, setOffset] = useState(0)
  const [reloadKey, setReloadKey] = useState(0)
  const [creating, setCreating] = useState(false)
  const [message, setMessage] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    let active = true
    getActiveIep(learner.id)
      .then(({ data: r }) => { if (active) setIep(r.iep) })
      .catch((err) => { if (active) { setIep(null); setError(getErrorMessage(err)) } })
    return () => { active = false }
  }, [learner.id])

  useEffect(() => {
    let active = true
    const params = Object.fromEntries(Object.entries(filters).filter(([, v]) => v))
    listEntries(learner.id, { ...params, offset, limit: PAGE_SIZE })
      .then(({ data: r }) => { if (active) setData(r) })
      .catch((err) => { if (active) setError(getErrorMessage(err)) })
    return () => { active = false }
  }, [learner.id, filters, offset, reloadKey])

  const reload = useCallback(async () => {
    setReloadKey((k) => k + 1)
    onChanged?.()
  }, [onChanged])

  const handleCreate = async (payload) => {
    const { data: entry } = await createEntry(learner.id, payload)
    setCreating(false)
    setMessage(entry.suggestions_error ? `Activity logged. ${entry.suggestions_error}` : 'Activity logged. Review the suggested IEP goals below.')
    setOffset(0)
    await reload()
  }

  const setFilter = (key) => (e) => { setOffset(0); setFilters((f) => ({ ...f, [key]: e.target.value })) }
  const goals = iep?.goals ?? []
  const period = iep ? { start: iep.start_date, end: iep.end_date } : null

  return (
    <div className="space-y-4 py-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-slate-600">
          Daily learning activities with this learner, linked to the goals of the active IEP
          {iep && <> (v{iep.version_number}, {iep.school_year})</>}.
        </p>
        {canWrite && iep && !creating && (
          <button className={primaryButtonClass} onClick={() => { setMessage(null); setCreating(true) }} type="button">Log activity</button>
        )}
      </div>

      {iep === null && (
        <Alert tone="info">
          This learner has no finalized IEP for {learner.school_year}. Finalize the IEP to start logging activities.{' '}
          <Link className="font-medium underline" to={`/learners/${learner.id}?tab=iep`}>Go to the IEP tab</Link>
        </Alert>
      )}
      {message && <Alert tone="success">{message}</Alert>}
      {error && <Alert>{error}</Alert>}

      {creating && (
        <div className="rounded-xl border border-slate-200 p-4">
          <IlawEntryForm onCancel={() => setCreating(false)} onSubmit={handleCreate} period={period} />
        </div>
      )}

      {(data.total > 0 || Object.values(filters).some(Boolean)) && (
        <div className="flex flex-wrap items-end gap-2 text-sm">
          <label className="text-xs text-slate-600">From<input className={`${inputClass} mt-0 py-1`} onChange={setFilter('from')} type="date" value={filters.from} /></label>
          <label className="text-xs text-slate-600">To<input className={`${inputClass} mt-0 py-1`} onChange={setFilter('to')} type="date" value={filters.to} /></label>
          {goals.length > 0 && (
            <label className="text-xs text-slate-600">
              Linked goal
              <select className={`${inputClass} mt-0 py-1`} onChange={setFilter('goal')} value={filters.goal}>
                <option value="">Any</option>
                {goals.map((g, i) => <option key={g.id} value={g.id}>Goal {i + 1}{g.goal_code ? ` (${g.goal_code})` : ''}</option>)}
              </select>
            </label>
          )}
          {Object.values(filters).some(Boolean) && (
            <button className={`${secondaryButtonClass} px-3 py-1 text-xs`} onClick={() => { setOffset(0); setFilters(EMPTY_FILTERS) }} type="button">Clear</button>
          )}
        </div>
      )}

      {data.items.length === 0 ? (
        iep && <p className="py-8 text-center text-slate-500">No activities logged{Object.values(filters).some(Boolean) ? ' for these filters' : ' yet'}.</p>
      ) : (
        <ul className="space-y-3">
          {data.items.map((entry) => (
            <IlawEntryCard
              canWrite={canWrite}
              entry={entry}
              goals={goals}
              key={`${entry.id}-${entry.updated_at}-${entry.alignments.map((a) => `${a.id}${a.status}`).join(',')}`}
              onChanged={reload}
              onDeleted={() => setMessage('Activity deleted.')}
              period={period}
            />
          ))}
        </ul>
      )}

      {data.total > PAGE_SIZE && (
        <div className="flex items-center justify-between text-sm text-slate-600">
          <span>{offset + 1}–{Math.min(offset + PAGE_SIZE, data.total)} of {data.total}</span>
          <div className="flex gap-2">
            <button className={`${secondaryButtonClass} px-3 py-1 text-sm`} disabled={offset === 0} onClick={() => setOffset((o) => Math.max(0, o - PAGE_SIZE))} type="button">Previous</button>
            <button className={`${secondaryButtonClass} px-3 py-1 text-sm`} disabled={offset + PAGE_SIZE >= data.total} onClick={() => setOffset((o) => o + PAGE_SIZE)} type="button">Next</button>
          </div>
        </div>
      )}
    </div>
  )
}
