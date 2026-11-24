import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { createLearner, listLearners } from '../../api/learnersApi'
import useAuth from '../../auth/useAuth'
import Alert from '../../shared/components/Alert'
import { inputClass, primaryButtonClass, secondaryButtonClass } from '../../shared/forms/styles'
import { getErrorMessage } from '../../shared/utils/apiError'
import { GRADE_LABELS, GRADE_LEVELS, LEARNER_EDITOR_ROLES, STATUS_OPTIONS } from './constants'
import LearnerForm from './LearnerForm'
import StatusBadge from './StatusBadge'

const PAGE_SIZE = 25
const EMPTY_FILTERS = { search: '', grade_level: '', section: '', school_year: '', status: '' }

export default function LearnersPage() {
  const { user } = useAuth()
  const navigate = useNavigate()
  const canEdit = LEARNER_EDITOR_ROLES.includes(user.role)

  const [filters, setFilters] = useState(EMPTY_FILTERS)
  const [offset, setOffset] = useState(0)
  const [data, setData] = useState({ items: [], total: 0 })
  const [loadState, setLoadState] = useState({ loading: true, error: null })
  const [creating, setCreating] = useState(false)

  useEffect(() => {
    let active = true
    const params = Object.fromEntries(Object.entries(filters).filter(([, v]) => v.trim()))
    const timer = setTimeout(() => {
      setLoadState((s) => ({ ...s, loading: true }))
      listLearners({ ...params, offset, limit: PAGE_SIZE })
        .then(({ data: result }) => {
          if (!active) return
          setData(result)
          setLoadState({ loading: false, error: null })
        })
        .catch((err) => {
          if (active) setLoadState({ loading: false, error: getErrorMessage(err) })
        })
    }, 250)
    return () => {
      active = false
      clearTimeout(timer)
    }
  }, [filters, offset])

  const setFilter = (field) => (e) => {
    setOffset(0)
    setFilters((f) => ({ ...f, [field]: e.target.value }))
  }

  const handleCreate = async (payload) => {
    const { data: created } = await createLearner(payload)
    navigate(`/learners/${created.id}`, { state: { message: `Created ${created.full_name}.` } })
  }

  const hasFilters = Object.values(filters).some((v) => v)
  const pageEnd = Math.min(offset + PAGE_SIZE, data.total)

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold text-slate-900">Learners</h1>
          <p className="mt-1 text-slate-600">
            {canEdit ? 'Every assessment, IEP and record links back to a learner here.' : 'Learners you have access to.'}
          </p>
        </div>
        {canEdit && !creating && (
          <button className={primaryButtonClass} onClick={() => setCreating(true)} type="button">
            Add learner
          </button>
        )}
      </div>

      {creating && (
        <section className="rounded-xl bg-white p-6 shadow">
          <h2 className="mb-4 text-lg font-semibold text-slate-900">New learner</h2>
          <LearnerForm onCancel={() => setCreating(false)} onSubmit={handleCreate} />
        </section>
      )}

      <section className="rounded-xl bg-white shadow">
        <div className="grid gap-3 border-b border-slate-200 p-4 sm:grid-cols-2 lg:grid-cols-5">
          <input aria-label="Search learners" className={`${inputClass} lg:col-span-2`} onChange={setFilter('search')} placeholder="Search name or learner code" value={filters.search} />
          <select aria-label="Filter by grade" className={inputClass} onChange={setFilter('grade_level')} value={filters.grade_level}>
            <option value="">All grades</option>
            {GRADE_LEVELS.map((g) => (
              <option key={g.value} value={g.value}>{g.label}</option>
            ))}
          </select>
          <input aria-label="Filter by section" className={inputClass} onChange={setFilter('section')} placeholder="Section" value={filters.section} />
          <input aria-label="Filter by school year" className={inputClass} onChange={setFilter('school_year')} placeholder="School year (2025-2026)" value={filters.school_year} />
          <select aria-label="Filter by status" className={inputClass} onChange={setFilter('status')} value={filters.status}>
            <option value="">All statuses</option>
            {STATUS_OPTIONS.map((s) => (
              <option key={s.value} value={s.value}>{s.label}</option>
            ))}
          </select>
          {hasFilters && (
            <button className={`${secondaryButtonClass} mt-1 text-sm`} onClick={() => { setOffset(0); setFilters(EMPTY_FILTERS) }} type="button">
              Clear filters
            </button>
          )}
        </div>

        {loadState.error && <div className="p-4"><Alert>{loadState.error}</Alert></div>}

        <div className="overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead className="bg-slate-50 text-slate-600">
              <tr>
                <th className="px-4 py-3 font-medium">Name</th>
                <th className="px-4 py-3 font-medium">Learner code</th>
                <th className="px-4 py-3 font-medium">Grade</th>
                <th className="px-4 py-3 font-medium">Section</th>
                <th className="px-4 py-3 font-medium">School year</th>
                <th className="px-4 py-3 font-medium">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {loadState.loading && data.items.length === 0 && (
                <tr><td className="px-4 py-6 text-center text-slate-500" colSpan={6}>Loading learners…</td></tr>
              )}
              {!loadState.loading && !loadState.error && data.items.length === 0 && (
                <tr>
                  <td className="px-4 py-6 text-center text-slate-500" colSpan={6}>
                    {hasFilters ? 'No learners match these filters.' : canEdit ? 'No learners yet. Add the first one.' : 'No learners are assigned to you yet.'}
                  </td>
                </tr>
              )}
              {data.items.map((l) => (
                <tr
                  className="cursor-pointer hover:bg-slate-50"
                  key={l.id}
                  onClick={() => navigate(`/learners/${l.id}`)}
                  onKeyDown={(e) => { if (e.key === 'Enter') navigate(`/learners/${l.id}`) }}
                  tabIndex={0}
                >
                  <td className="px-4 py-3 font-medium text-indigo-700">{l.last_name}, {l.first_name}{l.middle_name ? ` ${l.middle_name}` : ''}</td>
                  <td className="px-4 py-3 font-mono text-slate-600">{l.learner_code}</td>
                  <td className="px-4 py-3 text-slate-600">{GRADE_LABELS[l.grade_level] ?? l.grade_level}</td>
                  <td className="px-4 py-3 text-slate-600">{l.section}</td>
                  <td className="px-4 py-3 text-slate-600">{l.school_year}</td>
                  <td className="px-4 py-3"><StatusBadge status={l.status} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="flex items-center justify-between border-t border-slate-200 px-4 py-3 text-sm text-slate-500">
          <span>
            {data.total === 0 ? '0 learners' : `${offset + 1}–${pageEnd} of ${data.total} learner${data.total === 1 ? '' : 's'}`}
          </span>
          <div className="flex gap-2">
            <button className={`${secondaryButtonClass} px-3 py-1 text-sm`} disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))} type="button">
              Previous
            </button>
            <button className={`${secondaryButtonClass} px-3 py-1 text-sm`} disabled={pageEnd >= data.total} onClick={() => setOffset(offset + PAGE_SIZE)} type="button">
              Next
            </button>
          </div>
        </div>
      </section>
    </div>
  )
}
