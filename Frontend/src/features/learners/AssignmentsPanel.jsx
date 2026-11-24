import { useEffect, useState } from 'react'

import { addAssignment, listAssignments, removeAssignment } from '../../api/learnersApi'
import { listTeachers } from '../../api/usersApi'
import Alert from '../../shared/components/Alert'
import { inputClass, primaryButtonClass } from '../../shared/forms/styles'
import { getErrorMessage } from '../../shared/utils/apiError'

/** Teachers assigned to a learner. Coordinators can add and remove assignments. */
export default function AssignmentsPanel({ learner, canEdit }) {
  const [assignments, setAssignments] = useState([])
  const [teachers, setTeachers] = useState([])
  const [selected, setSelected] = useState('')
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const [reloadKey, setReloadKey] = useState(0)

  useEffect(() => {
    let active = true
    listAssignments(learner.id)
      .then(({ data }) => { if (active) setAssignments(data) })
      .catch((err) => { if (active) setError(getErrorMessage(err)) })
    return () => { active = false }
  }, [learner.id, reloadKey])

  useEffect(() => {
    if (!canEdit) return undefined
    let active = true
    listTeachers()
      .then(({ data }) => { if (active) setTeachers(data) })
      .catch((err) => { if (active) setError(getErrorMessage(err)) })
    return () => { active = false }
  }, [canEdit])

  const run = async (action) => {
    setBusy(true)
    setError(null)
    try {
      await action()
      setReloadKey((k) => k + 1)
    } catch (err) {
      setError(getErrorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  const handleAssign = (event) => {
    event.preventDefault()
    if (!selected) return
    run(async () => {
      await addAssignment(learner.id, { user_id: Number(selected) })
      setSelected('')
    })
  }

  const current = assignments.filter((a) => a.school_year === learner.school_year)
  const past = assignments.filter((a) => a.school_year !== learner.school_year)
  const assignedIds = new Set(current.map((a) => a.user_id))
  const available = teachers.filter((t) => !assignedIds.has(t.id))

  return (
    <section className="rounded-xl bg-white p-6 shadow">
      <h2 className="text-lg font-semibold text-slate-900">Assigned teachers</h2>
      <p className="mt-1 text-sm text-slate-500">
        Teachers see this learner only while assigned for school year {learner.school_year}.
      </p>
      {error && <div className="mt-3"><Alert>{error}</Alert></div>}

      <ul className="mt-4 divide-y divide-slate-100">
        {current.length === 0 && <li className="py-2 text-sm text-slate-500">No teachers assigned.</li>}
        {current.map((a) => (
          <li className="flex items-center justify-between py-2 text-sm" key={a.id}>
            <span className="text-slate-800">{a.user_name}</span>
            {canEdit && (
              <button
                className="text-sm font-medium text-red-600 hover:underline disabled:opacity-60"
                disabled={busy}
                onClick={() => run(() => removeAssignment(learner.id, a.id))}
                type="button"
              >
                Remove
              </button>
            )}
          </li>
        ))}
      </ul>

      {past.length > 0 && (
        <p className="mt-2 text-xs text-slate-500">
          Earlier years: {past.map((a) => `${a.user_name} (${a.school_year})`).join(', ')}
        </p>
      )}

      {canEdit && (
        <form className="mt-4 flex gap-2" onSubmit={handleAssign}>
          <select aria-label="Teacher to assign" className={`${inputClass} mt-0`} onChange={(e) => setSelected(e.target.value)} value={selected}>
            <option value="">{available.length ? 'Select a teacher' : 'No more active teachers'}</option>
            {available.map((t) => (
              <option key={t.id} value={t.id}>{t.name}</option>
            ))}
          </select>
          <button className={primaryButtonClass} disabled={busy || !selected} type="submit">
            Assign
          </button>
        </form>
      )}
    </section>
  )
}
