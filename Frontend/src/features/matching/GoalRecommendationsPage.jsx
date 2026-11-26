import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { listGoals, searchGoals } from '../../api/goalsApi'
import { getLearner } from '../../api/learnersApi'
import {
  acceptRecommendation,
  addManualGoal,
  editRecommendation,
  getLatestRecommendations,
  rejectRecommendation,
  removeManualGoal,
  resetRecommendation,
  runMatching,
} from '../../api/matchingApi'
import useAuth from '../../auth/useAuth'
import Alert from '../../shared/components/Alert'
import { inputClass, primaryButtonClass, secondaryButtonClass } from '../../shared/forms/styles'
import { getErrorMessage } from '../../shared/utils/apiError'
import { ASSESSMENT_WRITER_ROLES, DOMAIN_LABELS } from '../assessments/constants'
import { formatTarget, GRADE_BAND_LABELS, METHOD_LABELS, UNIT_LABELS } from '../goals/constants'

const small = `${secondaryButtonClass} px-2 py-1 text-xs`

function ScoreBar({ score }) {
  const pct = Math.max(0, Math.min(100, Math.round(score * 100)))
  const tone = pct >= 60 ? 'bg-emerald-500' : pct >= 45 ? 'bg-amber-500' : 'bg-slate-400'
  return (
    <div className="flex items-center gap-2" title={`Similarity ${score.toFixed(3)}`}>
      <div className="h-1.5 w-20 overflow-hidden rounded-full bg-slate-200"><div className={`h-full ${tone}`} style={{ width: `${pct}%` }} /></div>
      <span className="text-xs tabular-nums text-slate-600">{pct}%</span>
    </div>
  )
}

const STATUS_STYLE = {
  suggested: 'border-slate-200 bg-white',
  accepted: 'border-emerald-300 bg-emerald-50/50',
  rejected: 'border-slate-200 bg-slate-50 opacity-70',
}

/** Inline form for learner-specific wording; empty fields fall back to the goal bank version. */
function EditForm({ rec, submitLabel, onSubmit, onCancel }) {
  const v = rec.goal_version
  const [form, setForm] = useState({
    statement: rec.final_statement,
    target: String(rec.final_target_value),
    criterion: rec.final_criterion ?? '',
  })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const submit = async () => {
    setBusy(true)
    setError(null)
    try {
      await onSubmit({
        edited_statement: form.statement.trim() || null,
        edited_target_value: form.target === '' ? null : Number(form.target),
        edited_criterion: form.criterion.trim() || null,
      })
    } catch (err) {
      setError(getErrorMessage(err))
      setBusy(false)
    }
  }

  return (
    <div className="mt-2 space-y-2 rounded-lg border border-indigo-200 bg-white p-3">
      <p className="text-xs text-slate-500">Changes apply to this learner only; the goal bank stays unchanged.</p>
      <label className="sr-only" htmlFor={`st-${rec.id}`}>Goal statement</label>
      <textarea className={`${inputClass} mt-0 min-h-20 text-sm`} id={`st-${rec.id}`} maxLength={2000} onChange={(e) => setForm((f) => ({ ...f, statement: e.target.value }))} value={form.statement} />
      <div className="grid gap-2 sm:grid-cols-[8rem_1fr]">
        <label className="text-xs text-slate-600">
          Target ({UNIT_LABELS[v.target_unit] ?? v.target_unit})
          <input className={`${inputClass} mt-1 py-1 text-sm`} min="0" onChange={(e) => setForm((f) => ({ ...f, target: e.target.value }))} step="any" type="number" value={form.target} />
        </label>
        <label className="text-xs text-slate-600">
          Criterion
          <input className={`${inputClass} mt-1 py-1 text-sm`} maxLength={300} onChange={(e) => setForm((f) => ({ ...f, criterion: e.target.value }))} value={form.criterion} />
        </label>
      </div>
      {error && <Alert>{error}</Alert>}
      <div className="flex gap-2">
        <button className={`${primaryButtonClass} px-3 py-1 text-sm`} disabled={busy || form.statement.trim().length < 10} onClick={submit} type="button">{submitLabel}</button>
        <button className={`${secondaryButtonClass} px-3 py-1 text-sm`} onClick={onCancel} type="button">Cancel</button>
      </div>
    </div>
  )
}

function SuggestionCard({ rec, canWrite, onChanged }) {
  const [mode, setMode] = useState(null) // null | 'edit' | 'reject'
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const v = rec.goal_version
  const edited = rec.edited_statement || rec.edited_target_value != null || rec.edited_criterion != null

  const act = async (fn) => {
    setBusy(true)
    setError(null)
    try {
      await fn()
      setMode(null)
      onChanged()
    } catch (err) {
      setError(getErrorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <li className={`rounded-lg border p-3 ${STATUS_STYLE[rec.status]}`}>
      <div className="flex flex-wrap items-center gap-2 text-xs">
        {rec.rank != null && <span className="rounded bg-slate-800 px-1.5 py-0.5 font-semibold text-white">#{rec.rank}</span>}
        {rec.score != null && <ScoreBar score={rec.score} />}
        <span className="font-mono font-semibold text-slate-700">{rec.goal_code}</span>
        <span className="text-slate-500">{v.skill.name} · {METHOD_LABELS[v.measurement_method]} · {GRADE_BAND_LABELS[v.grade_band]}</span>
        {rec.status === 'accepted' && <span className="rounded-full bg-emerald-100 px-2 py-0.5 font-medium text-emerald-700">Accepted{edited ? ' (edited)' : ''}</span>}
        {rec.status === 'rejected' && <span className="rounded-full bg-slate-200 px-2 py-0.5 font-medium text-slate-600">Rejected{rec.reject_reason ? `: ${rec.reject_reason}` : ''}</span>}
      </div>
      <p className={`mt-1 text-sm ${rec.status === 'rejected' ? 'text-slate-500 line-through' : 'text-slate-900'}`}>{rec.final_statement}</p>
      <p className="text-xs text-slate-500">
        Target {formatTarget({ target_value: rec.final_target_value, target_unit: v.target_unit })}
        {rec.final_criterion && <> · {rec.final_criterion}</>}
        {rec.decided_by_name && <> · decided by {rec.decided_by_name}</>}
      </p>
      {error && <div className="mt-2"><Alert>{error}</Alert></div>}

      {canWrite && mode === null && (
        <div className="mt-2 flex flex-wrap gap-1">
          {rec.status === 'suggested' && (
            <>
              <button className={`${primaryButtonClass} px-2 py-1 text-xs`} disabled={busy} onClick={() => act(() => acceptRecommendation(rec.id))} type="button">Accept</button>
              <button className={small} disabled={busy} onClick={() => setMode('edit')} type="button">Edit &amp; accept</button>
              <button className={small} disabled={busy} onClick={() => setMode('reject')} type="button">Reject</button>
            </>
          )}
          {rec.status === 'accepted' && (
            <>
              <button className={small} disabled={busy} onClick={() => setMode('edit')} type="button">Edit wording</button>
              {rec.source === 'matched'
                ? <button className={small} disabled={busy} onClick={() => act(() => resetRecommendation(rec.id))} type="button">Undo</button>
                : <button className={small} disabled={busy} onClick={() => { if (window.confirm('Remove this manually added goal?')) act(() => removeManualGoal(rec.id)) }} type="button">Remove</button>}
            </>
          )}
          {rec.status === 'rejected' && (
            <button className={small} disabled={busy} onClick={() => act(() => resetRecommendation(rec.id))} type="button">Undo</button>
          )}
        </div>
      )}
      {mode === 'edit' && (
        <EditForm
          onCancel={() => setMode(null)}
          onSubmit={(edits) => act(() => (rec.status === 'accepted' ? editRecommendation(rec.id, edits) : acceptRecommendation(rec.id, edits)))}
          rec={rec}
          submitLabel={rec.status === 'accepted' ? 'Save wording' : 'Accept with changes'}
        />
      )}
      {mode === 'reject' && (
        <div className="mt-2 flex flex-wrap gap-2">
          <input aria-label="Reason (optional)" className={`${inputClass} mt-0 flex-1 py-1 text-sm`} maxLength={300} onChange={(e) => setReason(e.target.value)} placeholder="Reason (optional)" value={reason} />
          <button className={`${secondaryButtonClass} px-3 py-1 text-sm`} disabled={busy} onClick={() => act(() => rejectRecommendation(rec.id, reason))} type="button">Reject</button>
          <button className="px-2 text-sm text-slate-500" onClick={() => setMode(null)} type="button">Cancel</button>
        </div>
      )}
    </li>
  )
}

/** Modal: pick any active goal from the bank (semantic search or text search). */
function GoalPicker({ learnerId, need, onClose, onAdded }) {
  const [query, setQuery] = useState(need?.text ?? '')
  const [mode, setMode] = useState(need ? 'similar' : 'text')
  const [results, setResults] = useState(null)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  const search = async (e) => {
    e?.preventDefault()
    setBusy(true)
    setError(null)
    try {
      if (mode === 'similar') {
        const { data } = await searchGoals(query, 10)
        setResults(data.items.map((h) => ({ goal: h.goal, score: h.score })))
      } else {
        const { data } = await listGoals({ q: query, limit: 25 })
        setResults(data.items.map((g) => ({ goal: g, score: null })))
      }
    } catch (err) {
      setError(getErrorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  const add = async (goal) => {
    setBusy(true)
    setError(null)
    try {
      await addManualGoal(learnerId, { goal_id: goal.id, finding_id: need?.id ?? null })
      onAdded()
      onClose()
    } catch (err) {
      setError(getErrorMessage(err))
      setBusy(false)
    }
  }

  return (
    <div aria-modal="true" className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-slate-900/50 p-4" onClick={onClose} role="dialog">
      <div className="my-8 w-full max-w-2xl rounded-xl bg-white shadow-xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b border-slate-200 px-5 py-3">
          <h2 className="font-semibold text-slate-900">Add a goal manually</h2>
          <button className={small} onClick={onClose} type="button">Close</button>
        </div>
        <div className="space-y-3 p-5">
          {need && <p className="text-sm text-slate-600">For need: “{need.text}”</p>}
          <form className="flex flex-wrap gap-2" onSubmit={search}>
            <select aria-label="Search type" className={`${inputClass} mt-0 w-auto`} onChange={(e) => setMode(e.target.value)} value={mode}>
              <option value="similar">Similar meaning</option>
              <option value="text">Text or code</option>
            </select>
            <input aria-label="Search goals" className={`${inputClass} mt-0 flex-1`} onChange={(e) => setQuery(e.target.value)} value={query} />
            <button className={`${primaryButtonClass} px-3 py-1 text-sm`} disabled={busy || query.trim().length < (mode === 'similar' ? 3 : 1)} type="submit">Search</button>
          </form>
          {error && <Alert>{error}</Alert>}
          {results && results.length === 0 && <p className="text-sm text-slate-500">No active goals found.</p>}
          <ul className="max-h-[60vh] space-y-2 overflow-y-auto">
            {results?.map(({ goal, score }) => (
              <li className="flex items-start gap-3 rounded-lg border border-slate-200 p-3" key={goal.id}>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
                    <span className="font-mono font-semibold text-slate-700">{goal.code}</span>
                    {goal.current_version.domain.name} → {goal.current_version.skill.name}
                    {score != null && <ScoreBar score={score} />}
                  </div>
                  <p className="mt-1 text-sm text-slate-900">{goal.current_version.statement}</p>
                </div>
                <button className={`${primaryButtonClass} px-3 py-1 text-xs`} disabled={busy} onClick={() => add(goal)} type="button">Add</button>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  )
}

function RunSettings({ onRun, busy, onCancel }) {
  const [opts, setOpts] = useState({ top_k: 5, min_score: 0.35, same_domain: true, use_grade_band: true })
  return (
    <div className="space-y-3 rounded-lg border border-slate-200 bg-white p-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <label className="text-sm text-slate-700">
          Suggestions per need
          <select className={`${inputClass} py-1`} onChange={(e) => setOpts((o) => ({ ...o, top_k: Number(e.target.value) }))} value={opts.top_k}>
            {[3, 5, 10].map((k) => <option key={k} value={k}>{k}</option>)}
          </select>
        </label>
        <label className="text-sm text-slate-700">
          Minimum similarity: <strong>{Math.round(opts.min_score * 100)}%</strong>
          <input className="mt-2 w-full" max="0.8" min="0" onChange={(e) => setOpts((o) => ({ ...o, min_score: Number(e.target.value) }))} step="0.05" type="range" value={opts.min_score} />
        </label>
      </div>
      <div className="flex flex-wrap gap-4 text-sm text-slate-700">
        <label className="flex items-center gap-2"><input checked={opts.same_domain} onChange={(e) => setOpts((o) => ({ ...o, same_domain: e.target.checked }))} type="checkbox" />Only goals in the need's domain</label>
        <label className="flex items-center gap-2"><input checked={opts.use_grade_band} onChange={(e) => setOpts((o) => ({ ...o, use_grade_band: e.target.checked }))} type="checkbox" />Only goals for the learner's grade band</label>
      </div>
      <div className="flex gap-2">
        <button className={primaryButtonClass} disabled={busy} onClick={() => onRun(opts)} type="button">{busy ? 'Matching… (the first run loads the model)' : 'Run matching'}</button>
        <button className={secondaryButtonClass} onClick={onCancel} type="button">Cancel</button>
      </div>
    </div>
  )
}

export default function GoalRecommendationsPage() {
  const { learnerId } = useParams()
  return <Recommendations key={learnerId} learnerId={learnerId} />
}

function Recommendations({ learnerId }) {
  const { user } = useAuth()
  const canWrite = ASSESSMENT_WRITER_ROLES.includes(user.role)

  const [learner, setLearner] = useState(null)
  const [view, setView] = useState(null)
  const [load, setLoad] = useState({ loading: true, error: null })
  const [showSettings, setShowSettings] = useState(false)
  const [running, setRunning] = useState(false)
  const [message, setMessage] = useState(null)
  const [error, setError] = useState(null)
  const [picker, setPicker] = useState(null) // null | { need } (need may be null)

  useEffect(() => {
    let active = true
    Promise.all([getLearner(learnerId), getLatestRecommendations(learnerId)])
      .then(([l, r]) => {
        if (!active) return
        setLearner(l.data)
        setView(r.data)
        setLoad({ loading: false, error: null })
      })
      .catch((err) => { if (active) setLoad({ loading: false, error: getErrorMessage(err) }) })
    return () => { active = false }
  }, [learnerId])

  const reload = useCallback(() => {
    getLatestRecommendations(learnerId).then(({ data }) => setView(data)).catch((err) => setError(getErrorMessage(err)))
  }, [learnerId])

  const handleRun = async (options) => {
    setRunning(true)
    setError(null)
    setMessage(null)
    try {
      await runMatching(learnerId, options)
      setShowSettings(false)
      setMessage('Matching finished. Review the suggestions for each need.')
      reload()
    } catch (err) {
      setError(getErrorMessage(err))
    } finally {
      setRunning(false)
    }
  }

  if (load.loading) return <p className="text-slate-500">Loading…</p>
  if (load.error) return <Alert>{load.error}</Alert>

  const run = view.run
  const needsByDomain = {}
  for (const need of run?.needs ?? []) {
    ;(needsByDomain[need.domain ?? 'other'] ??= []).push(need)
  }
  const manualFor = (needId) => view.manual.filter((m) => m.finding_id === needId)
  const unlinkedManual = view.manual.filter((m) => m.finding_id == null)

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <Link className="text-sm text-indigo-600 hover:underline" to={`/learners/${learnerId}`}>← Back to {learner.full_name}</Link>
          <h1 className="mt-1 text-2xl font-semibold text-slate-900">Goal suggestions</h1>
          <p className="text-sm text-slate-600">
            Suggestions come from the learner's approved needs ({view.approved_need_count}) and the active goal bank. A person always decides.
          </p>
        </div>
        {canWrite && !showSettings && (
          <div className="flex gap-2">
            <button className={secondaryButtonClass} onClick={() => setPicker({ need: null })} type="button">Add goal manually</button>
            <button className={primaryButtonClass} disabled={view.approved_need_count === 0} onClick={() => setShowSettings(true)} type="button">
              {run ? 'Run matching again' : 'Run matching'}
            </button>
          </div>
        )}
      </div>

      {showSettings && <RunSettings busy={running} onCancel={() => setShowSettings(false)} onRun={handleRun} />}
      {message && <Alert tone="success">{message}</Alert>}
      {error && <Alert>{error}</Alert>}
      {view.approved_need_count === 0 && (
        <Alert tone="info">This learner has no approved needs yet. Approve an assessment analysis (Stage 6) first.</Alert>
      )}

      {run && (
        <p className="rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-600">
          Last run {new Date(run.created_at).toLocaleString()} by {run.created_by_name} · model <code>{run.model_version}</code> ·
          top {run.top_k} · minimum {Math.round(run.min_score * 100)}% · {run.same_domain ? 'same domain' : 'all domains'} ·
          {run.grade_band ? ` grade band ${run.grade_band}` : ' all grade bands'}
        </p>
      )}

      <div className="grid gap-6 lg:grid-cols-[1fr_22rem]">
        <div className="space-y-6">
          {!run && view.approved_need_count > 0 && <p className="py-10 text-center text-slate-500">No matching has been run for this learner yet.</p>}
          {Object.entries(needsByDomain).map(([domain, needs]) => (
            <section className="space-y-4" key={domain}>
              <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">{DOMAIN_LABELS[domain] ?? domain}</h2>
              {needs.map((need) => (
                <div className="space-y-2 rounded-xl border border-slate-200 bg-slate-50/60 p-4" key={need.id}>
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <p className="font-medium text-slate-900">Need: “{need.text}”</p>
                    <Link className="text-xs text-indigo-600 hover:underline" to={`/learners/${learnerId}/assessments/${need.assessment_id}/analysis`}>Source analysis</Link>
                  </div>
                  {need.suggestions.length === 0 && (
                    <p className="text-sm text-slate-500">No goal above the minimum score. Lower the threshold or add one manually.</p>
                  )}
                  <ul className="space-y-2">
                    {need.suggestions.map((rec) => <SuggestionCard canWrite={canWrite} key={rec.id} onChanged={reload} rec={rec} />)}
                    {manualFor(need.id).map((rec) => <SuggestionCard canWrite={canWrite} key={rec.id} onChanged={reload} rec={rec} />)}
                  </ul>
                  {canWrite && (
                    <button className="text-sm font-medium text-indigo-600 hover:underline" onClick={() => setPicker({ need })} type="button">+ Add goal manually</button>
                  )}
                </div>
              ))}
            </section>
          ))}
          {unlinkedManual.length > 0 && (
            <section className="space-y-2">
              <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500">Added manually (no linked need)</h2>
              <ul className="space-y-2">
                {unlinkedManual.map((rec) => <SuggestionCard canWrite={canWrite} key={rec.id} onChanged={reload} rec={rec} />)}
              </ul>
            </section>
          )}
        </div>

        <aside className="h-fit space-y-3 rounded-xl border border-emerald-200 bg-white p-4 lg:sticky lg:top-4">
          <h2 className="font-semibold text-slate-900">Selected goals ({view.selected.length})</h2>
          {view.selected.length === 0 && <p className="text-sm text-slate-500">Accepted goals appear here. They will be used for the IEP.</p>}
          <ol className="space-y-3">
            {view.selected.map((rec) => (
              <li className="border-l-2 border-emerald-400 pl-3 text-sm" key={rec.id}>
                <div className="text-xs text-slate-500">
                  <span className="font-mono font-semibold text-slate-700">{rec.goal_code}</span> · {rec.goal_version.domain.name}
                  {rec.source === 'manual' ? ' · added manually' : rec.score != null ? ` · ${Math.round(rec.score * 100)}% match` : ''}
                </div>
                <p className="text-slate-900">{rec.final_statement}</p>
              </li>
            ))}
          </ol>
        </aside>
      </div>

      {picker && <GoalPicker learnerId={learnerId} need={picker.need} onAdded={() => { setMessage('Goal added.'); reload() }} onClose={() => setPicker(null)} />}
    </div>
  )
}
