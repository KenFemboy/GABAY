import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { createManualEvaluation, listEvaluations } from '../../api/evaluationsApi'
import { getConfigStatus } from '../../api/systemApi'
import useAuth from '../../auth/useAuth'
import Alert from '../../shared/components/Alert'
import { primaryButtonClass, secondaryButtonClass } from '../../shared/forms/styles'
import { getErrorMessage } from '../../shared/utils/apiError'
import AiPreviewDialog from './AiPreviewDialog'
import { EVALUATION_WRITER_ROLES } from './constants'

/** Learner profile → Evaluations tab: year-end evaluations. */
export default function EvaluationsTab({ learner, onChanged }) {
  const { user } = useAuth()
  const navigate = useNavigate()
  const canWrite = EVALUATION_WRITER_ROLES.includes(user.role)
  const [items, setItems] = useState(null)
  const [ai, setAi] = useState(null)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const [previewing, setPreviewing] = useState(false)

  useEffect(() => {
    let active = true
    Promise.all([listEvaluations(learner.id), getConfigStatus().catch(() => ({ data: {} }))])
      .then(([e, s]) => { if (active) { setItems(e.data.items); setAi(s.data.evaluation_ai ?? { enabled: false, configured: false }) } })
      .catch((err) => { if (active) setError(getErrorMessage(err)) })
    return () => { active = false }
  }, [learner.id])

  const open = (ev, message) => {
    onChanged?.()
    navigate(`/learners/${learner.id}/evaluations/${ev.id}`, { state: { message, fallback: ev.fallback_reason } })
  }

  const manual = async () => {
    setBusy(true)
    setError(null)
    try {
      const { data } = await createManualEvaluation(learner.id)
      open(data, 'Manual draft created from the year’s evidence. Complete each section.')
    } catch (err) {
      setError(getErrorMessage(err))
      setBusy(false)
    }
  }

  const thisYear = (items ?? []).filter((e) => e.school_year === learner.school_year)
  const canCreate = canWrite && items && thisYear.length === 0
  const aiReady = ai?.enabled && ai?.configured

  return (
    <div className="space-y-4 py-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-slate-600">Year-end evaluation of progress on each goal of the active IEP.</p>
        {canCreate && (
          <div className="flex gap-2">
            <button className={secondaryButtonClass} disabled={busy} onClick={manual} type="button">Write manually</button>
            {aiReady && <button className={primaryButtonClass} onClick={() => setPreviewing(true)} type="button">Generate with AI…</button>}
          </div>
        )}
      </div>
      {canCreate && !aiReady && ai && (
        <p className="text-xs text-slate-500">
          AI drafting is {ai.enabled ? 'enabled but not configured (OPENAI_API_KEY and OPENAI_MODEL)' : 'turned off (EVALUATION_AI_ENABLED)'}. You can write the evaluation manually; it starts from the year’s evidence.
        </p>
      )}
      {error && <Alert>{error}</Alert>}
      {items && items.length === 0 && <p className="py-6 text-center text-slate-500">No evaluations yet.</p>}
      {items && items.length > 0 && (
        <ul className="divide-y divide-slate-100 rounded-lg border border-slate-200">
          {items.map((e) => (
            <li className="flex flex-wrap items-center justify-between gap-2 px-4 py-3 text-sm" key={e.id}>
              <div>
                <span className="font-medium text-slate-900">{e.school_year}</span>{' '}
                <span className={`ml-1 rounded-full px-2 py-0.5 text-xs ${e.status === 'finalized' ? 'bg-emerald-100 text-emerald-700' : 'bg-amber-100 text-amber-800'}`}>
                  {e.status === 'finalized' ? 'Finalized' : 'Draft'}
                </span>
                <div className="text-xs text-slate-500">
                  {e.source === 'ai' ? `AI draft · ${e.model} · prompt ${e.prompt_version}` : 'Written manually'}
                  {e.generation_error && ' (AI failed; manual fallback)'} · {e.created_by_name}
                  {e.finalized_at && ` · finalized ${new Date(e.finalized_at).toLocaleDateString()} by ${e.finalized_by_name}`}
                </div>
              </div>
              <Link className={`${primaryButtonClass} px-3 py-1 text-xs`} to={`/learners/${learner.id}/evaluations/${e.id}`}>
                {e.status === 'draft' && canWrite ? 'Edit' : 'Open'}
              </Link>
            </li>
          ))}
        </ul>
      )}
      {previewing && (
        <AiPreviewDialog
          learnerId={learner.id}
          onClose={() => setPreviewing(false)}
          onCreated={(ev) => open(ev, ev.fallback_reason ? null : 'AI draft created. Review every section and its evidence before finalizing.')}
        />
      )}
    </div>
  )
}
