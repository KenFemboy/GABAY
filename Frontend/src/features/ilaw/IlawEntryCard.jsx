import { useState } from 'react'

import { addLink, changeLink, confirmLink, deleteEntry, rejectLink, resetLink, resuggest, updateEntry } from '../../api/ilawApi'
import Alert from '../../shared/components/Alert'
import { inputClass, secondaryButtonClass } from '../../shared/forms/styles'
import { getErrorMessage } from '../../shared/utils/apiError'
import { DOMAIN_LABELS } from '../assessments/constants'
import IlawEntryForm from './IlawEntryForm'

const small = `${secondaryButtonClass} px-2 py-0.5 text-xs`

function goalLabel(goal, goals) {
  const n = goals.findIndex((g) => g.id === goal.id)
  return `${n >= 0 ? `Goal ${n + 1}` : 'Earlier IEP goal'}${goal.goal_code ? ` (${goal.goal_code})` : ''}`
}

function Score({ score }) {
  const pct = Math.round(score * 100)
  return (
    <span className="inline-flex items-center gap-1" title={`Similarity ${score.toFixed(3)}`}>
      <span className="h-1.5 w-14 overflow-hidden rounded-full bg-slate-200"><span className="block h-full bg-indigo-500" style={{ width: `${Math.max(0, pct)}%` }} /></span>
      <span className="text-xs tabular-nums text-slate-500">{pct}%</span>
    </span>
  )
}

function LinkRow({ link, goals, canWrite, onAction }) {
  const [changing, setChanging] = useState(false)
  const [target, setTarget] = useState('')
  const status = link.status
  const others = goals.filter((g) => g.id !== link.iep_goal_id)
  return (
    <li className={`rounded-lg border p-2 text-sm ${status === 'confirmed' ? 'border-emerald-300 bg-emerald-50/60' : status === 'rejected' ? 'border-slate-200 bg-slate-50 opacity-70' : 'border-slate-200 bg-white'}`}>
      <div className="flex flex-wrap items-center gap-2 text-xs text-slate-600">
        {status === 'confirmed' && <span className="font-semibold text-emerald-700">✓ Linked</span>}
        {status === 'rejected' && <span className="font-semibold text-slate-500">Not linked</span>}
        {status === 'suggested' && <span className="font-semibold text-indigo-700">Suggested{link.rank ? ` #${link.rank}` : ''}</span>}
        <span className="font-medium text-slate-800">{goalLabel(link.goal, goals)}</span>
        {link.goal.domain && <span>{DOMAIN_LABELS[link.goal.domain]}</span>}
        {link.score != null && <Score score={link.score} />}
        {link.source === 'manual' && <span className="rounded bg-slate-100 px-1">added by hand</span>}
        {link.decided_by_name && <span>· {link.decided_by_name}</span>}
      </div>
      <p className={`mt-1 ${status === 'rejected' ? 'line-through text-slate-500' : 'text-slate-900'}`}>{link.goal.statement}</p>
      {canWrite && !changing && (
        <div className="mt-1 flex flex-wrap gap-1">
          {status === 'suggested' && (
            <>
              <button className={small} onClick={() => onAction(() => confirmLink(link.id))} type="button">Confirm</button>
              <button className={small} onClick={() => onAction(() => rejectLink(link.id))} type="button">Reject</button>
              {others.length > 0 && <button className={small} onClick={() => setChanging(true)} type="button">Change…</button>}
            </>
          )}
          {status !== 'suggested' && (
            <button className={small} onClick={() => onAction(() => resetLink(link.id))} type="button">{link.source === 'manual' ? 'Remove' : 'Undo'}</button>
          )}
        </div>
      )}
      {changing && (
        <div className="mt-1 flex flex-wrap gap-1">
          <select aria-label="Link to another goal" className={`${inputClass} mt-0 w-auto flex-1 py-1 text-xs`} onChange={(e) => setTarget(e.target.value)} value={target}>
            <option value="">Link to another goal instead…</option>
            {others.map((g) => <option key={g.id} value={g.id}>{goalLabel(g, goals)}: {g.statement.slice(0, 80)}</option>)}
          </select>
          <button className={small} disabled={!target} onClick={() => onAction(() => changeLink(link.id, Number(target))).then(() => setChanging(false))} type="button">Change</button>
          <button className="px-1 text-xs text-slate-500" onClick={() => setChanging(false)} type="button">Cancel</button>
        </div>
      )}
    </li>
  )
}

/** One ILAW entry with its aligned IEP goals. */
export default function IlawEntryCard({ entry, goals, period, canWrite, onChanged, onDeleted }) {
  const [editing, setEditing] = useState(false)
  const [adding, setAdding] = useState('')
  const [error, setError] = useState(entry.suggestions_error)
  const [busy, setBusy] = useState(false)
  const linkedIds = new Set(entry.alignments.map((l) => l.iep_goal_id))
  const unlinked = goals.filter((g) => !linkedIds.has(g.id))
  const version = entry.alignments.find((l) => l.model_version)?.model_version

  const act = async (fn) => {
    setBusy(true)
    setError(null)
    try {
      const result = await fn()
      if (result?.data?.suggestions_error) setError(result.data.suggestions_error)
      await onChanged()
    } catch (err) {
      setError(getErrorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  if (editing) {
    return (
      <li className="rounded-xl border border-indigo-200 bg-white p-4">
        <IlawEntryForm
          entry={entry}
          onCancel={() => setEditing(false)}
          onSubmit={async (data) => { const r = await updateEntry(entry.id, data); setEditing(false); setError(r.data.suggestions_error); await onChanged() }}
          period={period}
        />
      </li>
    )
  }

  return (
    <li className="space-y-3 rounded-xl border border-slate-200 bg-white p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <p className="text-xs text-slate-500">
            {new Date(`${entry.activity_date}T00:00:00`).toLocaleDateString()}
            {entry.duration_minutes && ` · ${entry.duration_minutes} min`} · {entry.created_by_name}
          </p>
          <h3 className="font-semibold text-slate-900">{entry.title}</h3>
        </div>
        {canWrite && (
          <div className="flex gap-1">
            <button className={small} disabled={busy} onClick={() => act(() => resuggest(entry.id))} type="button">Re-suggest</button>
            <button className={small} onClick={() => setEditing(true)} type="button">Edit</button>
            <button className="px-2 text-xs font-medium text-red-600 hover:underline" onClick={() => { if (window.confirm('Delete this activity entry?')) act(async () => { await deleteEntry(entry.id); onDeleted?.() }) }} type="button">Delete</button>
          </div>
        )}
      </div>
      <p className="whitespace-pre-wrap text-sm text-slate-800">{entry.description}</p>
      {(entry.learner_response || entry.materials || entry.notes) && (
        <dl className="grid gap-2 text-sm sm:grid-cols-3">
          {entry.learner_response && <div><dt className="text-xs text-slate-500">Learner's response</dt><dd className="whitespace-pre-wrap">{entry.learner_response}</dd></div>}
          {entry.materials && <div><dt className="text-xs text-slate-500">Materials</dt><dd className="whitespace-pre-wrap">{entry.materials}</dd></div>}
          {entry.notes && <div><dt className="text-xs text-slate-500">Notes</dt><dd className="whitespace-pre-wrap">{entry.notes}</dd></div>}
        </dl>
      )}
      <div className="space-y-2">
        <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-500">Aligned IEP goals</h4>
        {error && <Alert tone="info">{error}</Alert>}
        {entry.alignments.length === 0 && !error && <p className="text-sm text-slate-500">No goal was similar enough. Link one by hand below.</p>}
        <ul className="space-y-2">
          {entry.alignments.map((l) => <LinkRow canWrite={canWrite} goals={goals} key={l.id} link={l} onAction={act} />)}
        </ul>
        {canWrite && unlinked.length > 0 && (
          <div className="flex flex-wrap gap-1">
            <select aria-label="Link another goal" className={`${inputClass} mt-0 w-auto flex-1 py-1 text-xs`} onChange={(e) => setAdding(e.target.value)} value={adding}>
              <option value="">+ Link another goal…</option>
              {unlinked.map((g) => <option key={g.id} value={g.id}>{goalLabel(g, goals)}: {g.statement.slice(0, 80)}</option>)}
            </select>
            <button className={small} disabled={!adding || busy} onClick={() => act(() => addLink(entry.id, Number(adding))).then(() => setAdding(''))} type="button">Link</button>
          </div>
        )}
        {version && <p className="text-[11px] text-slate-400">Suggestions by {version}</p>}
      </div>
    </li>
  )
}
