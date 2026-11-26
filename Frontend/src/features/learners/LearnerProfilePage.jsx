import { useCallback, useEffect, useState } from 'react'
import { Link, useLocation, useParams, useSearchParams } from 'react-router-dom'

import { getLearnerSummary, updateLearner } from '../../api/learnersApi'
import useAuth from '../../auth/useAuth'
import Alert from '../../shared/components/Alert'
import { primaryButtonClass, secondaryButtonClass } from '../../shared/forms/styles'
import { getErrorMessage } from '../../shared/utils/apiError'
import AssessmentsTab from '../assessments/AssessmentsTab'
import IepTab from '../iep/IepTab'
import AssignmentsPanel from './AssignmentsPanel'
import { GRADE_LABELS, LEARNER_EDITOR_ROLES, PROFILE_TABS, SEX_LABELS } from './constants'
import LearnerForm from './LearnerForm'
import StatusBadge from './StatusBadge'

function ModuleTab({ label, module }) {
  if (!module?.available) {
    return (
      <div className="py-10 text-center">
        <p className="font-medium text-slate-700">{label} is not available yet</p>
        <p className="mt-1 text-sm text-slate-500">This module will be available in a later stage.</p>
      </div>
    )
  }
  if (module.count === 0) {
    return <p className="py-10 text-center text-slate-500">No {label} records for this learner yet.</p>
  }
  return (
    <dl className="grid gap-4 py-4 sm:grid-cols-3">
      <div><dt className="text-xs text-slate-500">Records</dt><dd className="text-lg font-semibold">{module.count}</dd></div>
      <div><dt className="text-xs text-slate-500">Latest status</dt><dd className="text-lg font-semibold">{module.latest_status ?? '—'}</dd></div>
      <div><dt className="text-xs text-slate-500">Last updated</dt><dd className="text-lg font-semibold">{module.latest_at ? new Date(module.latest_at).toLocaleDateString() : '—'}</dd></div>
    </dl>
  )
}

// Keyed on the id so navigating to another learner starts from fresh state.
export default function LearnerProfilePage() {
  const { learnerId } = useParams()
  return <LearnerProfile key={learnerId} learnerId={learnerId} />
}

function LearnerProfile({ learnerId }) {
  const { user } = useAuth()
  const location = useLocation()
  const [searchParams, setSearchParams] = useSearchParams()
  const canEdit = LEARNER_EDITOR_ROLES.includes(user.role)

  const [state, setState] = useState({ loading: true, error: null, notFound: false, summary: null })
  const [editing, setEditing] = useState(false)
  const [message, setMessage] = useState(location.state?.message ?? null)
  // Bumped after a module changes so tab counts refresh.
  const [summaryKey, setSummaryKey] = useState(0)
  const reloadSummary = useCallback(() => setSummaryKey((k) => k + 1), [])

  useEffect(() => {
    let active = true
    getLearnerSummary(learnerId)
      .then(({ data }) => {
        if (active) setState({ loading: false, error: null, notFound: false, summary: data })
      })
      .catch((err) => {
        if (!active) return
        const status = err?.response?.status
        setState({
          loading: false,
          error: getErrorMessage(err),
          notFound: status === 404 || status === 422,
          summary: null,
        })
      })
    return () => { active = false }
  }, [learnerId, summaryKey])

  const activeTab = PROFILE_TABS.some((t) => t.key === searchParams.get('tab'))
    ? searchParams.get('tab')
    : PROFILE_TABS[0].key

  if (state.loading) {
    return <p className="text-slate-500">Loading learner…</p>
  }

  if (state.notFound) {
    return (
      <section className="mx-auto max-w-lg rounded-xl bg-white p-8 text-center shadow">
        <h1 className="text-2xl font-bold text-slate-900">Learner not found</h1>
        <p className="mt-2 text-slate-600">
          This learner does not exist or you do not have access to their record.
        </p>
        <Link className="mt-6 inline-block font-medium text-indigo-600 hover:underline" to="/learners">
          Back to learners
        </Link>
      </section>
    )
  }

  if (state.error) {
    return <Alert>{state.error}</Alert>
  }

  const { learner, modules } = state.summary

  const handleUpdate = async (payload) => {
    const { data: updated } = await updateLearner(learner.id, payload)
    setState((s) => ({ ...s, summary: { ...s.summary, learner: updated } }))
    setEditing(false)
    setMessage(`Saved changes to ${updated.full_name}.`)
  }

  const details = [
    ['Learner code', <span className="font-mono" key="code">{learner.learner_code}</span>],
    ['Grade / section', `${GRADE_LABELS[learner.grade_level] ?? learner.grade_level} – ${learner.section}`],
    ['School year', learner.school_year],
    ['Birth date', new Date(`${learner.birth_date}T00:00:00`).toLocaleDateString()],
    ['Sex', SEX_LABELS[learner.sex] ?? learner.sex],
  ]

  return (
    <div className="space-y-6">
      <Link className="text-sm font-medium text-indigo-600 hover:underline" to="/learners">
        ← All learners
      </Link>

      {message && <Alert tone="success">{message}</Alert>}

      <section className="rounded-xl bg-white p-6 shadow">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-3xl font-bold text-slate-900">{learner.full_name}</h1>
              <StatusBadge status={learner.status} />
            </div>
            <dl className="mt-3 flex flex-wrap gap-x-8 gap-y-2 text-sm">
              {details.map(([label, value]) => (
                <div key={label}>
                  <dt className="text-xs text-slate-500">{label}</dt>
                  <dd className="text-slate-800">{value}</dd>
                </div>
              ))}
            </dl>
          </div>
          <div className="flex flex-wrap gap-2">
            <Link className={primaryButtonClass} to={`/learners/${learner.id}/goals`}>Goal suggestions</Link>
            {canEdit && !editing && (
              <button className={secondaryButtonClass} onClick={() => { setMessage(null); setEditing(true) }} type="button">
                Edit learner
              </button>
            )}
          </div>
        </div>
        {editing && (
          <div className="mt-6 border-t border-slate-200 pt-6">
            <LearnerForm learner={learner} onCancel={() => setEditing(false)} onSubmit={handleUpdate} />
          </div>
        )}
      </section>

      <AssignmentsPanel canEdit={canEdit} learner={learner} />

      <section className="rounded-xl bg-white shadow">
        <div className="flex gap-1 overflow-x-auto border-b border-slate-200 px-4" role="tablist">
          {PROFILE_TABS.map((tab) => {
            const module = modules[tab.key]
            const selected = tab.key === activeTab
            return (
              <button
                aria-selected={selected}
                className={`-mb-px border-b-2 px-4 py-3 text-sm font-medium ${selected ? 'border-indigo-600 text-indigo-700' : 'border-transparent text-slate-600 hover:text-slate-900'}`}
                key={tab.key}
                onClick={() => setSearchParams({ tab: tab.key }, { replace: true })}
                role="tab"
                type="button"
              >
                {tab.label}
                {module?.available && (
                  <span className="ml-2 rounded-full bg-slate-100 px-2 text-xs text-slate-600">{module.count}</span>
                )}
              </button>
            )
          })}
        </div>
        <div className="px-6" role="tabpanel">
          {activeTab === 'assessments' ? (
            <AssessmentsTab learner={learner} onChanged={reloadSummary} />
          ) : activeTab === 'iep' ? (
            <IepTab learner={learner} onChanged={reloadSummary} />
          ) : (
            <ModuleTab
              label={PROFILE_TABS.find((t) => t.key === activeTab).label}
              module={modules[activeTab]}
            />
          )}
        </div>
      </section>
    </div>
  )
}
