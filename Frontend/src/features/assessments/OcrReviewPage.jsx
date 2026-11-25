import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { getAssessment, getDocumentUrl, getOcr, processAssessment, updateOcrPage } from '../../api/assessmentApi'
import { getLearner } from '../../api/learnersApi'
import useAuth from '../../auth/useAuth'
import Alert from '../../shared/components/Alert'
import { primaryButtonClass, secondaryButtonClass } from '../../shared/forms/styles'
import { getErrorMessage } from '../../shared/utils/apiError'
import AssessmentStatusBadge from './AssessmentStatusBadge'
import {
  ASSESSMENT_WRITER_ROLES,
  confidenceTone,
  DEFAULT_REVIEW_CONFIDENCE,
  EDITABLE_OCR_STATUSES,
  pageSourceLabel,
  PROCESSING_POLL_MS,
  STATUS_MANAGER_ROLES,
  TYPE_LABELS,
} from './constants'
import StatusControl from './StatusControl'

const fullName = (l) => [l.first_name, l.middle_name, l.last_name].filter(Boolean).join(' ')

/** Original document beside the text. Signed URLs are short-lived, so refresh before expiry. */
function DocumentPane({ assessmentId, document, pageNumber }) {
  const [state, setState] = useState({ url: null, error: null })

  useEffect(() => {
    let active = true
    let timer
    const load = () => {
      getDocumentUrl(assessmentId)
        .then(({ data }) => {
          if (!active) return
          setState({ url: data.url, error: null })
          // Re-sign a little before it expires so page changes keep working.
          timer = setTimeout(load, Math.max(5, data.expires_in - 5) * 1000)
        })
        .catch((err) => { if (active) setState({ url: null, error: getErrorMessage(err) }) })
    }
    load()
    return () => { active = false; clearTimeout(timer) }
  }, [assessmentId])

  const isPdf = document.mime_type === 'application/pdf'
  return (
    <div className="flex h-[75vh] items-center justify-center overflow-auto rounded-lg border border-slate-200 bg-slate-100">
      {state.error && <div className="p-4"><Alert>{state.error}</Alert></div>}
      {!state.error && !state.url && <p className="text-slate-500">Loading document…</p>}
      {state.url && isPdf && (
        // The key forces the browser viewer to jump to the selected page.
        <iframe className="h-full w-full" key={`${state.url}#${pageNumber}`} src={`${state.url}#page=${pageNumber}`} title={document.original_filename} />
      )}
      {state.url && !isPdf && (
        <img alt={document.original_filename} className="max-h-full max-w-full object-contain" src={state.url} />
      )}
    </div>
  )
}

export default function OcrReviewPage() {
  const { learnerId, assessmentId } = useParams()
  return <OcrReview assessmentId={assessmentId} key={assessmentId} learnerId={learnerId} />
}

function OcrReview({ learnerId, assessmentId }) {
  const { user } = useAuth()
  const canWrite = ASSESSMENT_WRITER_ROLES.includes(user.role)
  const canManageStatus = STATUS_MANAGER_ROLES.includes(user.role)

  const [load, setLoad] = useState({ loading: true, error: null })
  const [learner, setLearner] = useState(null)
  const [assessment, setAssessment] = useState(null)
  const [ocr, setOcr] = useState(null)
  const [pageNumber, setPageNumber] = useState(1)
  // Unsaved edits per page number; a page without an entry shows its saved text.
  const [edits, setEdits] = useState({})
  const [showRaw, setShowRaw] = useState(false)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState(null)
  const [error, setError] = useState(null)

  const page = ocr?.pages.find((p) => p.page_number === pageNumber) ?? null
  const savedText = page ? (page.reviewed_text ?? page.raw_text) : ''
  const draft = edits[pageNumber] ?? savedText
  const dirty = page !== null && draft !== savedText
  const setDraft = (text) => setEdits((prev) => ({ ...prev, [pageNumber]: text }))
  const clearDraft = (n) => setEdits((prev) => {
    const next = { ...prev }
    delete next[n]
    return next
  })
  const editable = canWrite && assessment && EDITABLE_OCR_STATUSES.includes(assessment.processing_status) && page?.status === 'ok'
  const threshold = ocr?.summary.review_confidence ?? DEFAULT_REVIEW_CONFIDENCE

  const fetchAll = useCallback(
    () => Promise.all([getAssessment(assessmentId), getOcr(assessmentId)]),
    [assessmentId],
  )
  const reload = useCallback(
    () => fetchAll().then(([a, o]) => { setAssessment(a.data); setOcr(o.data) }),
    [fetchAll],
  )

  useEffect(() => {
    let active = true
    Promise.all([fetchAll(), getLearner(learnerId).then(({ data }) => data).catch(() => null)])
      .then(([[a, o], l]) => {
        if (!active) return
        setAssessment(a.data)
        setOcr(o.data)
        setLearner(l)
        setLoad({ loading: false, error: null })
      })
      .catch((err) => { if (active) setLoad({ loading: false, error: getErrorMessage(err) }) })
    return () => { active = false }
  }, [learnerId, fetchAll])

  // Poll while a reprocess is running.
  const processing = assessment?.processing_status === 'processing'
  useEffect(() => {
    if (!processing) return undefined
    const timer = setInterval(() => { reload().catch(() => {}) }, PROCESSING_POLL_MS)
    return () => clearInterval(timer)
  }, [processing, reload])

  // Warn before leaving the browser tab with unsaved edits.
  useEffect(() => {
    if (!dirty) return undefined
    const onBeforeUnload = (e) => { e.preventDefault(); e.returnValue = '' }
    window.addEventListener('beforeunload', onBeforeUnload)
    return () => window.removeEventListener('beforeunload', onBeforeUnload)
  }, [dirty])

  const goTo = (n) => {
    if (n === pageNumber) return
    if (dirty && !window.confirm('You have unsaved changes on this page. Discard them?')) return
    clearDraft(pageNumber)
    setMessage(null)
    setError(null)
    setShowRaw(false)
    setPageNumber(n)
  }

  const save = async (text) => {
    setSaving(true)
    setError(null)
    try {
      const { data } = await updateOcrPage(assessmentId, pageNumber, text)
      clearDraft(data.page_number)
      setOcr((prev) => ({
        ...prev,
        pages: prev.pages.map((p) => (p.page_number === data.page_number ? data : p)),
        summary: {
          ...prev.summary,
          reviewed_pages: prev.pages.filter((p) => (p.page_number === data.page_number ? data : p).reviewed_text !== null).length,
        },
      }))
      setMessage(text === null ? 'Reverted to the OCR text.' : `Page ${pageNumber} saved.`)
    } catch (err) {
      setError(getErrorMessage(err))
    } finally {
      setSaving(false)
    }
  }

  const reprocess = async () => {
    if (!window.confirm('Process the document again? The current OCR text and all corrections will be replaced.')) return
    setError(null)
    try {
      const { data } = await processAssessment(assessmentId)
      setAssessment(data)
      setEdits({})
      setMessage('Reprocessing started.')
    } catch (err) {
      setError(getErrorMessage(err))
    }
  }

  const onStatusChanged = (data, text) => {
    setAssessment(data)
    setMessage(text)
  }

  if (load.loading) return <p className="text-slate-500">Loading…</p>
  if (load.error) return <Alert>{load.error}</Alert>

  const backTo = `/learners/${learnerId}?tab=assessments`
  const pages = ocr.pages

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <Link className="text-sm text-indigo-600 hover:underline" to={backTo}>← Back to {learner ? fullName(learner) : 'learner'}</Link>
          <h1 className="mt-1 text-xl font-semibold text-slate-900">
            Review OCR text · {TYPE_LABELS[assessment.assessment_type] ?? assessment.assessment_type} assessment
          </h1>
          <p className="text-sm text-slate-600">
            {new Date(`${assessment.assessment_date}T00:00:00`).toLocaleDateString()} · {assessment.assessor}
            {assessment.document && <> · {assessment.document.original_filename}</>}
          </p>
        </div>
        <div className="flex flex-col items-end gap-2">
          <AssessmentStatusBadge status={assessment.processing_status} />
          {canWrite && EDITABLE_OCR_STATUSES.includes(assessment.processing_status) && (
            <button className={`${secondaryButtonClass} px-3 py-1 text-sm`} onClick={reprocess} type="button">Reprocess</button>
          )}
        </div>
      </div>

      {canManageStatus && !processing && <StatusControl assessment={assessment} onChanged={onStatusChanged} />}
      {message && <Alert tone="success">{message}</Alert>}
      {error && <Alert>{error}</Alert>}
      {processing && <Alert tone="info">The document is being processed again. This page updates automatically.</Alert>}
      {assessment.ocr_error && <Alert>Processing failed: {assessment.ocr_error}</Alert>}

      {ocr.summary.page_count > 0 && (
        <p className="text-sm text-slate-600">
          {ocr.summary.page_count} page{ocr.summary.page_count === 1 ? '' : 's'}
          {ocr.summary.mean_confidence != null && <> · average OCR confidence {Math.round(ocr.summary.mean_confidence)}%</>}
          {ocr.summary.low_confidence_pages > 0 && <> · <span className="text-amber-700">{ocr.summary.low_confidence_pages} below {threshold}%</span></>}
          {ocr.summary.failed_pages > 0 && <> · <span className="text-red-700">{ocr.summary.failed_pages} failed</span></>}
          {' '}· {ocr.summary.reviewed_pages} corrected
        </p>
      )}

      {pages.length === 0 ? (
        <p className="py-10 text-center text-slate-500">{processing ? 'Waiting for the OCR results…' : 'There is no OCR text for this assessment yet.'}</p>
      ) : (
        <>
          <nav aria-label="Pages" className="flex flex-wrap items-center gap-1">
            <button className={`${secondaryButtonClass} px-3 py-1 text-sm`} disabled={pageNumber <= 1} onClick={() => goTo(pageNumber - 1)} type="button">‹ Prev</button>
            {pages.map((p) => (
              <button
                aria-current={p.page_number === pageNumber ? 'page' : undefined}
                className={`min-w-9 rounded-md border px-2 py-1 text-sm font-medium ${confidenceTone(p, threshold)} ${p.page_number === pageNumber ? 'ring-2 ring-indigo-500' : ''}`}
                key={p.page_number}
                onClick={() => goTo(p.page_number)}
                title={`Page ${p.page_number}: ${pageSourceLabel(p)}${p.reviewed_text !== null ? ' (corrected)' : ''}`}
                type="button"
              >
                {p.page_number}{p.reviewed_text !== null ? '✓' : ''}
              </button>
            ))}
            <button className={`${secondaryButtonClass} px-3 py-1 text-sm`} disabled={pageNumber >= pages.length} onClick={() => goTo(pageNumber + 1)} type="button">Next ›</button>
          </nav>

          <div className="grid gap-4 lg:grid-cols-2">
            {assessment.document ? (
              <DocumentPane assessmentId={assessmentId} document={assessment.document} pageNumber={pageNumber} />
            ) : <div />}

            {page && (
              <div className="flex flex-col gap-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <h2 className="font-semibold text-slate-900">Page {page.page_number} of {pages.length}</h2>
                  <span className={`rounded-full border px-2 py-0.5 text-xs font-medium ${confidenceTone(page, threshold)}`}>{pageSourceLabel(page)}</span>
                </div>

                {page.status === 'failed' ? (
                  <Alert>{page.error_message || 'This page could not be read.'}</Alert>
                ) : (
                  <>
                    <label className="sr-only" htmlFor="ocr-text">Text for page {page.page_number}</label>
                    <textarea
                      className="h-[55vh] w-full resize-y rounded-lg border border-slate-300 p-3 font-mono text-sm text-slate-900 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-200 read-only:bg-slate-50"
                      id="ocr-text"
                      onChange={(e) => setDraft(e.target.value)}
                      readOnly={!editable}
                      spellCheck
                      value={draft}
                    />
                    <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-slate-500">
                      <span>
                        {page.reviewed_text !== null
                          ? `Corrected by ${page.reviewed_by_name ?? 'someone'} on ${new Date(page.reviewed_at).toLocaleString()}`
                          : 'Showing the original OCR text.'}
                        {dirty && <span className="ml-2 font-medium text-amber-700">Unsaved changes</span>}
                      </span>
                      {editable && (
                        <div className="flex gap-2">
                          {page.reviewed_text !== null && (
                            <button className={`${secondaryButtonClass} px-3 py-1 text-sm`} disabled={saving} onClick={() => save(null)} type="button">Revert to OCR text</button>
                          )}
                          {dirty && (
                            <button className={`${secondaryButtonClass} px-3 py-1 text-sm`} disabled={saving} onClick={() => clearDraft(pageNumber)} type="button">Discard</button>
                          )}
                          <button className={`${primaryButtonClass} px-3 py-1 text-sm`} disabled={!dirty || saving} onClick={() => save(draft)} type="button">
                            {saving ? 'Saving…' : 'Save page'}
                          </button>
                        </div>
                      )}
                    </div>
                    {page.reviewed_text !== null && (
                      <div>
                        <button className="text-sm text-indigo-600 hover:underline" onClick={() => setShowRaw((v) => !v)} type="button">
                          {showRaw ? 'Hide' : 'Show'} original OCR text
                        </button>
                        {showRaw && (
                          <pre className="mt-2 max-h-60 overflow-auto whitespace-pre-wrap rounded-lg border border-slate-200 bg-slate-50 p-3 text-xs text-slate-700">{page.raw_text}</pre>
                        )}
                      </div>
                    )}
                  </>
                )}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  )
}
