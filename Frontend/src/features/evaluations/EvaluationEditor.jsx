import { useEffect, useState } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'

import { discardEvaluation, finalizeEvaluation, getEvaluation, updateEvaluation } from '../../api/evaluationsApi'
import { getGoalProgress } from '../../api/progressApi'
import useAuth from '../../auth/useAuth'
import Alert from '../../shared/components/Alert'
import { inputClass, primaryButtonClass, secondaryButtonClass } from '../../shared/forms/styles'
import { getErrorMessage } from '../../shared/utils/apiError'
import { describeEvidence, EVALUATION_FINALIZER_ROLES, EVALUATION_WRITER_ROLES, RATINGS } from './constants'

function EvidenceChips({ ids, snapshot }) {
  if (!ids?.length) return <span className="text-xs text-slate-400">No evidence cited</span>
  return (
    <span className="flex flex-wrap gap-1">
      {ids.map((id) => (
        <span className="cursor-help rounded border border-slate-200 bg-slate-50 px-1.5 py-0.5 font-mono text-[11px] text-slate-600" key={id} title={describeEvidence(snapshot, id)}>{id}</span>
      ))}
    </span>
  )
}

function ListEditor({ label, items, readOnly, snapshot, onChange, error }) {
  return (
    <section className="space-y-2">
      <h2 className="font-semibold text-slate-900">{label}</h2>
      {error && <p className="text-xs text-red-600">{error}</p>}
      {items.length === 0 && <p className="text-sm text-slate-500">None yet.</p>}
      {items.map((item, i) => (
        <div className="space-y-1" key={i}>
          <div className="flex gap-2">
            <textarea aria-label={`${label} ${i + 1}`} className={`${inputClass} mt-0 min-h-14 text-sm`} disabled={readOnly} maxLength={1500} onChange={(e) => onChange(items.map((x, j) => (j === i ? { ...x, text: e.target.value } : x)))} value={item.text} />
            {!readOnly && <button className="self-start px-2 text-xs text-red-600 hover:underline" onClick={() => onChange(items.filter((_, j) => j !== i))} type="button">Remove</button>}
          </div>
          <EvidenceChips ids={item.evidence_ids} snapshot={snapshot} />
        </div>
      ))}
      {!readOnly && items.length < 10 && (
        <button className={`${secondaryButtonClass} px-3 py-1 text-xs`} onClick={() => onChange([...items, { text: '', evidence_ids: [] }])} type="button">+ Add</button>
      )}
    </section>
  )
}

export default function EvaluationEditorPage() {
  const { learnerId, evaluationId } = useParams()
  return <EvaluationEditor evaluationId={evaluationId} key={evaluationId} learnerId={learnerId} />
}

function EvaluationEditor({ learnerId, evaluationId }) {
  const { user } = useAuth()
  const location = useLocation()
  const navigate = useNavigate()
  const canWrite = EVALUATION_WRITER_ROLES.includes(user.role)
  const canFinalize = EVALUATION_FINALIZER_ROLES.includes(user.role)
  const [evaluation, setEvaluation] = useState(null)
  const [content, setContent] = useState(null)
  const [goalText, setGoalText] = useState({})
  const [load, setLoad] = useState({ loading: true, error: null })
  const [message, setMessage] = useState(location.state?.message ?? null)
  const [error, setError] = useState(null)
  const [fieldErrors, setFieldErrors] = useState({})
  const [busy, setBusy] = useState(false)
  const fallback = location.state?.fallback

  useEffect(() => {
    let active = true
    Promise.all([getEvaluation(evaluationId), getGoalProgress(learnerId).catch(() => ({ data: { goals: [] } }))])
      .then(([e, p]) => {
        if (!active) return
        setEvaluation(e.data)
        setContent(e.data.content)
        setGoalText(Object.fromEntries(p.data.goals.map((g) => [g.goal.id, { number: g.goal.number, statement: g.goal.statement, status: g.status.status }])))
        setLoad({ loading: false, error: null })
      })
      .catch((err) => { if (active) setLoad({ loading: false, error: getErrorMessage(err) }) })
    return () => { active = false }
  }, [evaluationId, learnerId])

  if (load.loading) return <p className="text-slate-500">Loading…</p>
  if (load.error) return <Alert>{load.error}</Alert>

  const readOnly = evaluation.read_only || !canWrite
  const snapshot = evaluation.evidence_snapshot
  const dirty = JSON.stringify(content) !== JSON.stringify(evaluation.content)
  const setGoal = (i, patch) => setContent((c) => ({ ...c, goals: c.goals.map((g, j) => (j === i ? { ...g, ...patch } : g)) }))

  const run = async (fn, okText) => {
    setBusy(true)
    setError(null)
    setFieldErrors({})
    try {
      await fn()
      if (okText) setMessage(okText)
    } catch (err) {
      const details = err?.response?.data?.error?.details ?? []
      setFieldErrors(Object.fromEntries(details.map((d) => [d.field, d.message])))
      setError(getErrorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  const save = () => run(async () => {
    const payload = {
      summary: content.summary ?? '',
      goals: content.goals.map((g) => ({ iep_goal_id: g.iep_goal_id, rating: g.rating, narrative: g.narrative, evidence_ids: g.evidence_ids ?? [] })),
      strengths: (content.strengths ?? []).filter((s) => s.text.trim()),
      recommendations: (content.recommendations ?? []).filter((s) => s.text.trim()),
    }
    const { data } = await updateEvaluation(evaluation.id, payload)
    setEvaluation(data)
    setContent(data.content)
  }, 'Saved.')

  const finalize = () => {
    if (dirty) { setError('Save your changes before finalizing.'); return }
    if (!window.confirm('Finalize this evaluation? It becomes read-only.')) return
    run(async () => {
      const { data } = await finalizeEvaluation(evaluation.id)
      setEvaluation(data)
      setContent(data.content)
    }, 'Evaluation finalized.')
  }

  const discard = () => {
    if (!window.confirm('Discard this draft?')) return
    run(async () => {
      await discardEvaluation(evaluation.id)
      navigate(`/learners/${learnerId}?tab=evaluations`)
    })
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <Link className="text-sm text-indigo-600 hover:underline" to={`/learners/${learnerId}?tab=evaluations`}>← Back to learner</Link>
          <h1 className="mt-1 text-2xl font-semibold text-slate-900">Year-end evaluation {evaluation.school_year}</h1>
          <p className="text-sm text-slate-600">{evaluation.status === 'finalized' ? `Finalized ${new Date(evaluation.finalized_at).toLocaleDateString()} by ${evaluation.finalized_by_name}` : 'Draft'}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          {!readOnly && <button className={secondaryButtonClass} disabled={busy || !dirty} onClick={save} type="button">{busy ? 'Saving…' : 'Save'}</button>}
          {!readOnly && <button className={secondaryButtonClass} disabled={busy} onClick={discard} type="button">Discard draft</button>}
          {evaluation.status === 'draft' && canFinalize && <button className={primaryButtonClass} disabled={busy} onClick={finalize} type="button">Finalize</button>}
        </div>
      </div>

      {fallback && (
        <Alert tone="info">The AI draft could not be used ({fallback}). A manual draft was started from the year’s evidence instead.</Alert>
      )}
      {evaluation.source === 'ai' && evaluation.status === 'draft' && (
        <Alert tone="info">This draft was written by AI from de-identified evidence. Check every statement against its evidence (hover the IDs) before finalizing.</Alert>
      )}
      {evaluation.validation_warnings?.length > 0 && evaluation.status === 'draft' && (
        <Alert tone="info">Review notes: {evaluation.validation_warnings.join(' ')}</Alert>
      )}
      {message && <Alert tone="success">{message}</Alert>}
      {error && <Alert>{error}</Alert>}

      <section className="space-y-1">
        <h2 className="font-semibold text-slate-900">Overall summary</h2>
        <textarea aria-label="Overall summary" className={`${inputClass} min-h-28 text-sm`} disabled={readOnly} maxLength={4000} onChange={(e) => setContent((c) => ({ ...c, summary: e.target.value }))} value={content.summary ?? ''} />
        {fieldErrors.summary && <p className="text-xs text-red-600">{fieldErrors.summary}</p>}
        <EvidenceChips ids={content.summary_evidence_ids} snapshot={snapshot} />
      </section>

      <section className="space-y-3">
        <h2 className="font-semibold text-slate-900">Progress on each goal</h2>
        {content.goals.map((g, i) => {
          const info = goalText[g.iep_goal_id]
          return (
            <div className="space-y-2 rounded-xl border border-slate-200 bg-white p-4" key={g.iep_goal_id}>
              <div className="flex flex-wrap items-start justify-between gap-2">
                <p className="text-sm text-slate-800"><span className="font-semibold">Goal {info?.number ?? i + 1}.</span> {info?.statement}</p>
                <select aria-label={`Rating for goal ${i + 1}`} className={`${inputClass} mt-0 w-auto py-1 text-sm`} disabled={readOnly} onChange={(e) => setGoal(i, { rating: e.target.value })} value={g.rating}>
                  {RATINGS.map((r) => <option key={r.value} value={r.value}>{r.label}</option>)}
                </select>
              </div>
              {info?.status && <p className="text-xs text-slate-500">Computed progress status: {info.status.replaceAll('_', ' ')}</p>}
              <textarea aria-label={`Narrative for goal ${i + 1}`} className={`${inputClass} mt-0 min-h-24 text-sm`} disabled={readOnly} maxLength={3000} onChange={(e) => setGoal(i, { narrative: e.target.value })} value={g.narrative} />
              {(fieldErrors[`goals.${i}.narrative`] || fieldErrors[`goals.${i}.rating`]) && (
                <p className="text-xs text-red-600">{fieldErrors[`goals.${i}.narrative`] ?? fieldErrors[`goals.${i}.rating`]}</p>
              )}
              <EvidenceChips ids={g.evidence_ids} snapshot={snapshot} />
            </div>
          )
        })}
      </section>

      <ListEditor items={content.strengths ?? []} label="Strengths" onChange={(strengths) => setContent((c) => ({ ...c, strengths }))} readOnly={readOnly} snapshot={snapshot} />
      <ListEditor items={content.recommendations ?? []} label="Recommendations for next school year" onChange={(recommendations) => setContent((c) => ({ ...c, recommendations }))} readOnly={readOnly} snapshot={snapshot} />

      <footer className="rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-500">
        {evaluation.source === 'ai'
          ? <>Drafted by AI · model <code>{evaluation.model}</code> · prompt <code>{evaluation.prompt_version}</code> · {evaluation.evidence_ids.length} evidence items · {new Date(evaluation.created_at).toLocaleString()} by {evaluation.created_by_name}</>
          : <>Written manually from {evaluation.evidence_ids.length} evidence items · started {new Date(evaluation.created_at).toLocaleString()} by {evaluation.created_by_name}{evaluation.generation_error && <> · AI fallback reason: {evaluation.generation_error}</>}</>}
      </footer>
    </div>
  )
}
