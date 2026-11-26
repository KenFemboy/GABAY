import { useCallback, useEffect, useState } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'

import { listGoals, searchGoals } from '../../api/goalsApi'
import {
  addIepFinding,
  addIepGoal,
  amendIep,
  deleteIepFinding,
  deleteIepGoal,
  discardIep,
  downloadIep,
  finalizeIep,
  getIep,
  reimportIep,
  reorderIepGoals,
  updateIep,
  updateIepFinding,
  updateIepGoal,
} from '../../api/iepApi'
import { getLearner } from '../../api/learnersApi'
import useAuth from '../../auth/useAuth'
import Alert from '../../shared/components/Alert'
import { inputClass, primaryButtonClass, secondaryButtonClass } from '../../shared/forms/styles'
import { getErrorMessage } from '../../shared/utils/apiError'
import { DOMAIN_LABELS, FINDING_CATEGORIES, FINDING_DOMAINS } from '../assessments/constants'
import { formatDate, IEP_EDITOR_ROLES, IEP_FINALIZER_ROLES } from './constants'
import IepGoalCard from './IepGoalCard'
import { IepStatusBadge } from './IepTab'
import TeamEditor from './TeamEditor'

const small = `${secondaryButtonClass} px-2 py-1 text-xs`

function issuesFor(validation, goalId) {
  const out = {}
  for (const i of validation) {
    if (i.goal_id === goalId) out[i.field.split('.').pop()] = i.message
  }
  return out
}

/** Plan details: period, review date, accommodations, services, notes, team. */
function PlanDetails({ iep, readOnly, onSave, issues }) {
  const initial = {
    start_date: iep.start_date ?? '', end_date: iep.end_date ?? '', annual_review_date: iep.annual_review_date ?? '',
    accommodations: iep.accommodations ?? '', services: iep.services ?? '', notes: iep.notes ?? '',
    amendment_reason: iep.amendment_reason ?? '', team_members: iep.team_members ?? [],
  }
  const [form, setForm] = useState(initial)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const dirty = JSON.stringify(form) !== JSON.stringify(initial)
  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }))
  const issue = (field) => issues.find((i) => i.field === field)?.message

  const save = async () => {
    setBusy(true)
    setError(null)
    try {
      await onSave({
        ...form,
        start_date: form.start_date || null, end_date: form.end_date || null,
        annual_review_date: form.annual_review_date || null,
        amendment_reason: iep.version_number > 1 ? form.amendment_reason || null : undefined,
        team_members: form.team_members.filter((m) => m.name.trim() || m.role.trim()),
      })
    } catch (err) {
      setError(getErrorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  const label = 'block text-xs font-medium text-slate-600'
  return (
    <section className="space-y-3 rounded-xl border border-slate-200 bg-white p-4">
      <h2 className="font-semibold text-slate-900">Plan details</h2>
      {iep.version_number > 1 && (
        <label className={label}>
          Reason for this amendment
          <textarea className={`${inputClass} min-h-14 text-sm`} disabled={readOnly} maxLength={2000} onChange={set('amendment_reason')} value={form.amendment_reason} />
          {issue('amendment_reason') && <span className="text-red-600">{issue('amendment_reason')}</span>}
        </label>
      )}
      <div className="grid gap-3 sm:grid-cols-3">
        {[['start_date', 'IEP start'], ['end_date', 'IEP end'], ['annual_review_date', 'Annual review']].map(([key, text]) => (
          <label className={label} key={key}>
            {text}
            <input className={`${inputClass} text-sm`} disabled={readOnly} onChange={set(key)} type="date" value={form[key]} />
            {issue(key) && <span className="text-red-600">{issue(key)}</span>}
          </label>
        ))}
      </div>
      {[['accommodations', 'Accommodations and modifications'], ['services', 'Services and related services'], ['notes', 'Notes']].map(([key, text]) => (
        <label className={label} key={key}>
          {text}
          <textarea className={`${inputClass} min-h-16 text-sm`} disabled={readOnly} maxLength={5000} onChange={set(key)} value={form[key]} />
        </label>
      ))}
      <div>
        <span className={label}>IEP team (printed with signature lines)</span>
        {issue('team_members') && <span className="block text-xs text-red-600">{issue('team_members')}</span>}
        <div className="mt-1">
          <TeamEditor disabled={readOnly} onChange={(team_members) => setForm((f) => ({ ...f, team_members }))} value={form.team_members} />
        </div>
      </div>
      {error && <Alert>{error}</Alert>}
      {!readOnly && (
        <button className={`${primaryButtonClass} px-3 py-1 text-sm`} disabled={busy || !dirty} onClick={save} type="button">{busy ? 'Saving…' : 'Save details'}</button>
      )}
    </section>
  )
}

function FindingRow({ finding, readOnly, onSave, onDelete }) {
  const [editing, setEditing] = useState(false)
  const [text, setText] = useState(finding.text)
  if (editing) {
    return (
      <li className="space-y-1">
        <textarea aria-label="Finding text" className={`${inputClass} mt-0 min-h-14 text-sm`} maxLength={2000} onChange={(e) => setText(e.target.value)} value={text} />
        <div className="flex gap-2">
          <button className={`${primaryButtonClass} px-2 py-1 text-xs`} disabled={!text.trim()} onClick={async () => { await onSave(finding.id, { text }); setEditing(false) }} type="button">Save</button>
          <button className={small} onClick={() => setEditing(false)} type="button">Cancel</button>
        </div>
      </li>
    )
  }
  return (
    <li className="group flex gap-2 text-sm">
      <span className="flex-1">
        {finding.domain && <span className="mr-1 text-xs text-indigo-700">[{DOMAIN_LABELS[finding.domain]}]</span>}
        {finding.text}
      </span>
      {!readOnly && (
        <span className="shrink-0 space-x-2 text-xs opacity-60 group-hover:opacity-100">
          <button className="text-indigo-600 hover:underline" onClick={() => { setText(finding.text); setEditing(true) }} type="button">Edit</button>
          <button className="text-red-600 hover:underline" onClick={() => { if (window.confirm('Remove this item from the IEP?')) onDelete(finding.id) }} type="button">Remove</button>
        </span>
      )}
    </li>
  )
}

function AddFindingForm({ onAdd, onCancel }) {
  const [form, setForm] = useState({ category: 'present_level', domain: '', text: '' })
  const [error, setError] = useState(null)
  return (
    <div className="space-y-2 rounded-lg border border-dashed border-slate-300 p-3">
      <div className="grid gap-2 sm:grid-cols-2">
        <select aria-label="Category" className={`${inputClass} mt-0 py-1 text-sm`} onChange={(e) => setForm((f) => ({ ...f, category: e.target.value }))} value={form.category}>
          {FINDING_CATEGORIES.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
        </select>
        <select aria-label="Domain" className={`${inputClass} mt-0 py-1 text-sm`} onChange={(e) => setForm((f) => ({ ...f, domain: e.target.value }))} value={form.domain}>
          <option value="">No domain</option>
          {FINDING_DOMAINS.map((d) => <option key={d.value} value={d.value}>{d.label}</option>)}
        </select>
      </div>
      <textarea aria-label="Text" className={`${inputClass} mt-0 min-h-14 text-sm`} maxLength={2000} onChange={(e) => setForm((f) => ({ ...f, text: e.target.value }))} value={form.text} />
      {error && <Alert>{error}</Alert>}
      <div className="flex gap-2">
        <button
          className={`${primaryButtonClass} px-3 py-1 text-sm`}
          disabled={!form.text.trim()}
          onClick={async () => {
            try { await onAdd({ ...form, domain: form.domain || null }) } catch (err) { setError(getErrorMessage(err)) }
          }}
          type="button"
        >
          Add
        </button>
        <button className={`${secondaryButtonClass} px-3 py-1 text-sm`} onClick={onCancel} type="button">Cancel</button>
      </div>
    </div>
  )
}

function AddGoalPanel({ onAdd, onClose }) {
  const [mode, setMode] = useState('bank')
  const [query, setQuery] = useState('')
  const [results, setResults] = useState(null)
  const [statement, setStatement] = useState('')
  const [domain, setDomain] = useState('')
  const [error, setError] = useState(null)

  const search = async (e) => {
    e.preventDefault()
    setError(null)
    try {
      const { data } = query.trim().length >= 3 ? await searchGoals(query, 10) : await listGoals({ q: query, limit: 25 })
      setResults(data.items.map((x) => x.goal ?? x))
    } catch (err) {
      setError(getErrorMessage(err))
    }
  }
  const add = async (payload) => {
    setError(null)
    try { await onAdd(payload); onClose() } catch (err) { setError(getErrorMessage(err)) }
  }

  return (
    <div className="space-y-3 rounded-xl border border-indigo-200 bg-indigo-50/40 p-4">
      <div className="flex items-center justify-between">
        <div className="flex gap-1">
          {[['bank', 'From goal bank'], ['custom', 'Custom goal']].map(([key, text]) => (
            <button className={`${mode === key ? primaryButtonClass : secondaryButtonClass} px-3 py-1 text-xs`} key={key} onClick={() => setMode(key)} type="button">{text}</button>
          ))}
        </div>
        <button className={small} onClick={onClose} type="button">Close</button>
      </div>
      {mode === 'bank' ? (
        <>
          <form className="flex gap-2" onSubmit={search}>
            <input aria-label="Search goal bank" className={`${inputClass} mt-0 flex-1 text-sm`} onChange={(e) => setQuery(e.target.value)} placeholder="Describe the need or type a goal code" value={query} />
            <button className={`${primaryButtonClass} px-3 py-1 text-sm`} type="submit">Search</button>
          </form>
          {results && results.length === 0 && <p className="text-sm text-slate-500">No active goals found.</p>}
          <ul className="max-h-80 space-y-2 overflow-y-auto">
            {results?.map((g) => (
              <li className="flex items-start gap-2 rounded-lg border border-slate-200 bg-white p-2" key={g.id}>
                <div className="min-w-0 flex-1 text-sm">
                  <span className="font-mono text-xs font-semibold text-slate-700">{g.code}</span> {g.current_version.statement}
                </div>
                <button className={`${primaryButtonClass} px-2 py-1 text-xs`} onClick={() => add({ goal_id: g.id })} type="button">Add</button>
              </li>
            ))}
          </ul>
        </>
      ) : (
        <div className="space-y-2">
          <select aria-label="Domain" className={`${inputClass} mt-0 text-sm`} onChange={(e) => setDomain(e.target.value)} value={domain}>
            <option value="">Domain…</option>
            {FINDING_DOMAINS.map((d) => <option key={d.value} value={d.value}>{d.label}</option>)}
          </select>
          <textarea aria-label="Goal statement" className={`${inputClass} mt-0 min-h-20 text-sm`} maxLength={2000} onChange={(e) => setStatement(e.target.value)} placeholder="Given…, the learner will… with …% accuracy in …" value={statement} />
          <button className={`${primaryButtonClass} px-3 py-1 text-sm`} disabled={statement.trim().length < 10} onClick={() => add({ statement, domain: domain || null })} type="button">Add custom goal</button>
        </div>
      )}
      {error && <Alert>{error}</Alert>}
    </div>
  )
}

export default function IepBuilderPage() {
  const { learnerId, iepId } = useParams()
  return <IepBuilder iepId={iepId} key={iepId} learnerId={learnerId} />
}

function IepBuilder({ learnerId, iepId }) {
  const { user } = useAuth()
  const location = useLocation()
  const navigate = useNavigate()
  const canEdit = IEP_EDITOR_ROLES.includes(user.role)
  const canFinalize = IEP_FINALIZER_ROLES.includes(user.role)

  const [learner, setLearner] = useState(null)
  const [iep, setIep] = useState(null)
  const [load, setLoad] = useState({ loading: true, error: null })
  const [message, setMessage] = useState(location.state?.message ?? null)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const [addingFinding, setAddingFinding] = useState(false)
  const [addingGoal, setAddingGoal] = useState(false)
  const [detailsKey, setDetailsKey] = useState(0)

  useEffect(() => {
    let active = true
    Promise.all([getLearner(learnerId), getIep(iepId)])
      .then(([l, i]) => {
        if (!active) return
        setLearner(l.data)
        setIep(i.data)
        setLoad({ loading: false, error: null })
      })
      .catch((err) => { if (active) setLoad({ loading: false, error: getErrorMessage(err) }) })
    return () => { active = false }
  }, [learnerId, iepId])

  const reload = useCallback(async () => {
    const { data } = await getIep(iepId)
    setIep(data)
  }, [iepId])

  const act = async (fn, text) => {
    setBusy(true)
    setError(null)
    setMessage(null)
    try {
      await fn()
      if (text) setMessage(text)
    } catch (err) {
      const details = err?.response?.data?.error?.details
      setError(details?.length ? `${getErrorMessage(err)} (${details.length} item${details.length === 1 ? '' : 's'})` : getErrorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  if (load.loading) return <p className="text-slate-500">Loading…</p>
  if (load.error) return <Alert>{load.error}</Alert>

  const readOnly = iep.read_only || !canEdit
  const issues = iep.validation
  const needs = iep.findings.filter((f) => f.category === 'need')
  const period = { start: iep.start_date, end: iep.end_date }
  const byCategory = FINDING_CATEGORIES.map((c) => ({ ...c, items: iep.findings.filter((f) => f.category === c.value) }))

  const saveDetails = async (data) => {
    const { data: updated } = await updateIep(iep.id, data)
    setIep(updated)
    setDetailsKey((k) => k + 1)
    setMessage('Plan details saved.')
  }

  const moveGoal = (goalId, delta) => act(async () => {
    const ids = iep.goals.map((g) => g.id)
    const i = ids.indexOf(goalId)
    const j = i + delta
    if (j < 0 || j >= ids.length) return
    ;[ids[i], ids[j]] = [ids[j], ids[i]]
    const { data } = await reorderIepGoals(iep.id, ids)
    setIep(data)
  })

  const handleFinalize = () => {
    if (!window.confirm('Finalize this IEP? It becomes read-only; later changes need an amendment.')) return
    act(async () => {
      const { data } = await finalizeIep(iep.id)
      setIep(data)
      setDetailsKey((k) => k + 1)
    }, 'IEP finalized.')
  }

  const handleAmend = () => {
    const reason = window.prompt('Reason for the amendment (at least 5 characters):')
    if (!reason) return
    act(async () => {
      const { data } = await amendIep(iep.id, reason)
      navigate(`/learners/${learnerId}/ieps/${data.id}`, { state: { message: `Amendment draft v${data.version_number} created.` } })
    })
  }

  const handleDiscard = () => {
    if (!window.confirm('Discard this draft IEP? This cannot be undone.')) return
    act(async () => {
      await discardIep(iep.id)
      navigate(`/learners/${learnerId}?tab=iep`)
    })
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <Link className="text-sm text-indigo-600 hover:underline" to={`/learners/${learnerId}?tab=iep`}>← Back to {learner.full_name}</Link>
          <h1 className="mt-1 flex flex-wrap items-center gap-2 text-2xl font-semibold text-slate-900">
            IEP {iep.school_year} · v{iep.version_number} <IepStatusBadge status={iep.status} />
          </h1>
          <p className="text-sm text-slate-600">
            Period {formatDate(iep.start_date)} – {formatDate(iep.end_date)} · created by {iep.created_by_name}
            {iep.finalized_at && <> · finalized {new Date(iep.finalized_at).toLocaleDateString()} by {iep.finalized_by_name}</>}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button className={secondaryButtonClass} onClick={() => act(() => downloadIep(iep.id))} type="button">Download DOCX</button>
          {iep.status === 'draft' && canEdit && (
            <button className={secondaryButtonClass} disabled={busy} onClick={handleDiscard} type="button">Discard draft</button>
          )}
          {iep.status === 'draft' && canFinalize && (
            <button className={primaryButtonClass} disabled={busy || issues.length > 0} onClick={handleFinalize} title={issues.length ? 'Fix the checklist items first' : ''} type="button">Finalize</button>
          )}
          {iep.status === 'finalized' && canFinalize && (
            <button className={primaryButtonClass} disabled={busy} onClick={handleAmend} type="button">Amend</button>
          )}
        </div>
      </div>

      {iep.read_only && (
        <Alert tone="info">
          {iep.status === 'superseded' ? 'This version was replaced by a later amendment. ' : 'This IEP is finalized. '}
          It is read-only{iep.status === 'finalized' ? '; use Amend to make changes in a new version' : ''}.
        </Alert>
      )}
      {iep.status === 'draft' && !canFinalize && (
        <Alert tone="info">Only the SNED Coordinator can finalize this IEP.</Alert>
      )}
      {message && <Alert tone="success">{message}</Alert>}
      {error && <Alert>{error}</Alert>}

      <div className="grid gap-6 lg:grid-cols-[1fr_20rem]">
        <div className="space-y-6">
          <PlanDetails issues={issues} iep={iep} key={`${iep.id}-${detailsKey}`} onSave={saveDetails} readOnly={readOnly} />

          <section className="space-y-3 rounded-xl border border-slate-200 bg-white p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h2 className="font-semibold text-slate-900">Present levels and findings</h2>
              {!readOnly && (
                <div className="flex gap-2">
                  <button
                    className={small}
                    disabled={busy}
                    onClick={() => act(async () => {
                      const { data } = await reimportIep(iep.id)
                      setIep(data.iep)
                      setMessage(`Re-import added ${data.findings_added} findings and ${data.goals_added} goals.`)
                    })}
                    type="button"
                  >
                    Re-import approved findings &amp; goals
                  </button>
                  <button className={small} onClick={() => setAddingFinding(true)} type="button">+ Add</button>
                </div>
              )}
            </div>
            {issues.some((i) => i.field === 'findings') && <p className="text-xs text-red-600">{issues.find((i) => i.field === 'findings').message}</p>}
            {addingFinding && (
              <AddFindingForm onAdd={async (data) => { await addIepFinding(iep.id, data); await reload(); setAddingFinding(false) }} onCancel={() => setAddingFinding(false)} />
            )}
            {byCategory.filter((c) => c.items.length).map((c) => (
              <div key={c.value}>
                <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">{c.label}</h3>
                <ul className="mt-1 space-y-1">
                  {c.items.map((f) => (
                    <FindingRow
                      finding={f}
                      key={f.id}
                      onDelete={(id) => act(async () => { await deleteIepFinding(iep.id, id); await reload() })}
                      onSave={async (id, data) => { await updateIepFinding(iep.id, id, data); await reload() }}
                      readOnly={readOnly}
                    />
                  ))}
                </ul>
              </div>
            ))}
          </section>

          <section className="space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="font-semibold text-slate-900">Annual goals ({iep.goals.length})</h2>
              {!readOnly && !addingGoal && <button className={small} onClick={() => setAddingGoal(true)} type="button">+ Add goal</button>}
            </div>
            {addingGoal && <AddGoalPanel onAdd={async (data) => { await addIepGoal(iep.id, data); await reload() }} onClose={() => setAddingGoal(false)} />}
            {iep.goals.length === 0 && (
              <p className="text-sm text-slate-500">
                No goals yet. Accept goals on the <Link className="text-indigo-600 hover:underline" to={`/learners/${learnerId}/goals`}>Goal suggestions</Link> page and re-import, or add one here.
              </p>
            )}
            <ol className="space-y-3">
              {iep.goals.map((g, i) => (
                <IepGoalCard
                  goal={g}
                  isFirst={i === 0}
                  isLast={i === iep.goals.length - 1}
                  issues={issuesFor(issues, g.id)}
                  key={`${g.id}-${detailsKey}`}
                  needs={needs}
                  number={i + 1}
                  onDelete={(id) => act(async () => { await deleteIepGoal(iep.id, id); await reload() })}
                  onMove={moveGoal}
                  onSave={async (id, data) => { await updateIepGoal(iep.id, id, data); await reload() }}
                  period={period}
                  readOnly={readOnly}
                />
              ))}
            </ol>
          </section>
        </div>

        <aside className="h-fit space-y-2 rounded-xl border border-slate-200 bg-white p-4 lg:sticky lg:top-4">
          <h2 className="font-semibold text-slate-900">Ready to finalize?</h2>
          {issues.length === 0 ? (
            <p className="text-sm text-emerald-700">✓ All required information is complete.</p>
          ) : (
            <>
              <p className="text-sm text-slate-600">{issues.length} item{issues.length === 1 ? '' : 's'} to complete:</p>
              <ul className="space-y-1 text-sm">
                {issues.map((i) => (
                  <li key={`${i.field}-${i.message}`}>
                    {i.goal_id ? (
                      <a className="text-amber-800 hover:underline" href={`#goal-${i.goal_id}`}>{i.message}</a>
                    ) : (
                      <span className="text-amber-800">{i.message}</span>
                    )}
                  </li>
                ))}
              </ul>
            </>
          )}
        </aside>
      </div>
    </div>
  )
}
