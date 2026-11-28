import { useEffect, useState } from 'react'

import { generateEvaluation, previewEvidence } from '../../api/evaluationsApi'
import Alert from '../../shared/components/Alert'
import { primaryButtonClass, secondaryButtonClass } from '../../shared/forms/styles'
import { getErrorMessage } from '../../shared/utils/apiError'

function Section({ title, items, render }) {
  if (!items?.length) return null
  return (
    <div>
      <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">{title} ({items.length})</h3>
      <ul className="mt-1 space-y-1 text-sm text-slate-800">{items.map((i) => <li key={i.id}><span className="font-mono text-xs text-slate-500">{i.id}</span> {render(i)}</li>)}</ul>
    </div>
  )
}

/**
 * Shows the EXACT de-identified evidence package before anything is sent to OpenAI.
 * Nothing leaves the server until "Generate draft" is clicked.
 */
export default function AiPreviewDialog({ learnerId, onClose, onCreated }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [raw, setRaw] = useState(false)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    let active = true
    previewEvidence(learnerId)
      .then(({ data: d }) => { if (active) setData(d) })
      .catch((err) => { if (active) setError(getErrorMessage(err)) })
    return () => { active = false }
  }, [learnerId])

  const generate = async () => {
    setBusy(true)
    setError(null)
    try {
      const { data: ev } = await generateEvaluation(learnerId, data.evidence_hash)
      onCreated(ev)
    } catch (err) {
      setError(getErrorMessage(err))
      setBusy(false)
    }
  }

  const pkg = data?.package
  return (
    <div aria-modal="true" className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-slate-900/50 p-4" onClick={onClose} role="dialog">
      <div className="my-8 w-full max-w-3xl rounded-xl bg-white shadow-xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b border-slate-200 px-5 py-3">
          <h2 className="font-semibold text-slate-900">Generate a draft with AI</h2>
          <button className={`${secondaryButtonClass} px-3 py-1 text-sm`} onClick={onClose} type="button">Close</button>
        </div>
        <div className="space-y-4 p-5">
          <Alert tone="info">
            This is exactly what will be sent to <strong>OpenAI</strong> if you click <strong>Generate draft</strong>.
            Names, the learner code, the birth date, staff names, phone numbers, emails and calendar dates have been removed.
            Check it before sending. The draft must be reviewed and edited before it is finalized.
          </Alert>
          {error && <Alert>{error}</Alert>}
          {!data && !error && <p className="text-slate-500">Building the evidence package…</p>}
          {pkg && (
            <>
              <p className="text-sm text-slate-600">
                {data.evidence_count} evidence items · {pkg.learner.grade}, age {pkg.learner.age_years} · IEP {pkg.iep.school_year} v{pkg.iep.version}
                <button className="ml-3 text-indigo-600 hover:underline" onClick={() => setRaw((v) => !v)} type="button">{raw ? 'Readable view' : 'Raw JSON'}</button>
              </p>
              {raw ? (
                <pre className="max-h-[50vh] overflow-auto rounded-lg bg-slate-900 p-3 text-xs text-slate-100">{JSON.stringify(pkg, null, 2)}</pre>
              ) : (
                <div className="max-h-[50vh] space-y-3 overflow-y-auto rounded-lg border border-slate-200 p-3">
                  <Section items={pkg.goals} render={(g) => <>{g.statement} <span className="text-xs text-slate-500">({g.computed_status.replace('_', ' ')}, {g.data_points} points)</span></>} title="Goals" />
                  <Section items={pkg.findings} render={(f) => <><span className="text-xs text-slate-500">{f.category}</span> {f.text}</>} title="Findings" />
                  <Section items={pkg.progress} render={(p) => `${p.goal} · week ${p.week} · ${p.value}${p.unit === 'percent' ? '%' : ` ${p.unit}`}${p.note ? ` · ${p.note}` : ''}`} title="Progress data" />
                  <Section items={pkg.activities} render={(a) => `week ${a.week} · ${a.title} – ${a.summary}`} title="Activities" />
                  <Section items={pkg.observations} render={(o) => `week ${o.week} · ${o.note}`} title="Observations" />
                  <Section items={pkg.grades} render={(r) => `${r.subject} ${r.period}: ${r.value}`} title="Grades" />
                </div>
              )}
              <div className="flex gap-2">
                <button className={primaryButtonClass} disabled={busy || !data.ai_enabled || !data.ai_configured} onClick={generate} type="button">
                  {busy ? 'Generating… (this can take a minute)' : 'Generate draft'}
                </button>
                <button className={secondaryButtonClass} onClick={onClose} type="button">Cancel</button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
