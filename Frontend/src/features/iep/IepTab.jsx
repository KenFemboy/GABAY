import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { createIep, downloadIep, listIeps } from '../../api/iepApi'
import useAuth from '../../auth/useAuth'
import Alert from '../../shared/components/Alert'
import { primaryButtonClass, secondaryButtonClass } from '../../shared/forms/styles'
import { getErrorMessage } from '../../shared/utils/apiError'
import { formatDate, IEP_EDITOR_ROLES, IEP_STATUS } from './constants'

export function IepStatusBadge({ status }) {
  const info = IEP_STATUS[status] ?? { label: status, className: 'bg-slate-200 text-slate-700' }
  return <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${info.className}`}>{info.label}</span>
}

/** Learner profile → IEP tab: version history and "Create IEP". */
export default function IepTab({ learner, onChanged }) {
  const { user } = useAuth()
  const navigate = useNavigate()
  const canEdit = IEP_EDITOR_ROLES.includes(user.role)
  const [items, setItems] = useState(null)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    let active = true
    listIeps(learner.id)
      .then(({ data }) => { if (active) setItems(data.items) })
      .catch((err) => { if (active) setError(getErrorMessage(err)) })
    return () => { active = false }
  }, [learner.id])

  const thisYear = (items ?? []).filter((i) => i.school_year === learner.school_year)
  const hasDraft = thisYear.some((i) => i.status === 'draft')
  const hasFinal = thisYear.some((i) => i.status === 'finalized')

  const handleCreate = async () => {
    setBusy(true)
    setError(null)
    try {
      const { data } = await createIep(learner.id)
      onChanged?.()
      navigate(`/learners/${learner.id}/ieps/${data.iep.id}`, {
        state: { message: `Draft IEP created with ${data.findings_added} findings and ${data.goals_added} goals imported.` },
      })
    } catch (err) {
      setError(getErrorMessage(err))
      setBusy(false)
    }
  }

  return (
    <div className="space-y-4 py-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-slate-600">
          The IEP is built from approved assessment findings and the goals accepted on the{' '}
          <Link className="text-indigo-600 hover:underline" to={`/learners/${learner.id}/goals`}>Goal suggestions</Link> page.
        </p>
        {canEdit && items && !hasDraft && !hasFinal && (
          <button className={primaryButtonClass} disabled={busy} onClick={handleCreate} type="button">
            {busy ? 'Creating…' : `Create IEP for ${learner.school_year}`}
          </button>
        )}
      </div>
      {error && <Alert>{error}</Alert>}
      {!items && !error && <p className="text-slate-500">Loading…</p>}
      {items && items.length === 0 && <p className="py-8 text-center text-slate-500">No IEP yet for this learner.</p>}
      {items && items.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-slate-200">
          <table className="min-w-full text-left text-sm">
            <thead className="bg-slate-50 text-slate-600">
              <tr>
                <th className="px-4 py-2 font-medium">School year</th>
                <th className="px-4 py-2 font-medium">Version</th>
                <th className="px-4 py-2 font-medium">Status</th>
                <th className="px-4 py-2 font-medium">Period</th>
                <th className="px-4 py-2 font-medium">Goals</th>
                <th className="px-4 py-2 font-medium">Finalized</th>
                <th className="px-4 py-2" />
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {items.map((iep) => (
                <tr key={iep.id}>
                  <td className="px-4 py-2">{iep.school_year}</td>
                  <td className="px-4 py-2">
                    v{iep.version_number}
                    {iep.amendment_reason && <div className="max-w-xs truncate text-xs text-slate-500" title={iep.amendment_reason}>Amendment: {iep.amendment_reason}</div>}
                  </td>
                  <td className="px-4 py-2"><IepStatusBadge status={iep.status} /></td>
                  <td className="px-4 py-2 text-slate-600">{formatDate(iep.start_date)} – {formatDate(iep.end_date)}</td>
                  <td className="px-4 py-2">{iep.goal_count}</td>
                  <td className="px-4 py-2 text-slate-600">{iep.finalized_at ? `${new Date(iep.finalized_at).toLocaleDateString()} by ${iep.finalized_by_name}` : '—'}</td>
                  <td className="whitespace-nowrap px-4 py-2 text-right">
                    <button className={`${secondaryButtonClass} mr-2 px-2 py-1 text-xs`} onClick={() => downloadIep(iep.id).catch((err) => setError(getErrorMessage(err)))} type="button">DOCX</button>
                    <Link className={`${primaryButtonClass} px-3 py-1 text-xs`} to={`/learners/${learner.id}/ieps/${iep.id}`}>
                      {iep.status === 'draft' && canEdit ? 'Edit' : 'Open'}
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
