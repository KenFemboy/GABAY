import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { createAssessment, deleteDocument, getDocumentUrl, listAssessments, processAssessment } from '../../api/assessmentApi'
import useAuth from '../../auth/useAuth'
import Alert from '../../shared/components/Alert'
import { primaryButtonClass, secondaryButtonClass } from '../../shared/forms/styles'
import { getErrorMessage } from '../../shared/utils/apiError'
import AssessmentForm from './AssessmentForm'
import AssessmentStatusBadge from './AssessmentStatusBadge'
import {
  ASSESSMENT_WRITER_ROLES,
  DOCUMENT_DELETER_ROLES,
  DOCUMENT_LOCKED_STATUSES,
  formatFileSize,
  PROCESSABLE_STATUSES,
  PROCESSING_POLL_MS,
  REVIEWABLE_STATUSES,
  STATUS_MANAGER_ROLES,
  TYPE_LABELS,
} from './constants'
import DocumentPreview from './DocumentPreview'
import DocumentUpload from './DocumentUpload'
import StatusControl from './StatusControl'

const formatDate = (iso) => new Date(`${iso}T00:00:00`).toLocaleDateString()

function AssessmentDetails({ assessment, canWrite, canDelete, canManageStatus, onChanged }) {
  const [previewing, setPreviewing] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const doc = assessment.document

  const handleDownload = async () => {
    setError(null)
    try {
      const { data } = await getDocumentUrl(assessment.id, { download: true })
      window.location.assign(data.url)
    } catch (err) {
      setError(getErrorMessage(err))
    }
  }

  const handleProcess = async () => {
    const reprocess = assessment.processing_status !== 'uploaded'
    if (reprocess && !window.confirm('Process the document again? The current OCR text and any corrections will be replaced.')) return
    setBusy(true)
    setError(null)
    try {
      const { data } = await processAssessment(assessment.id)
      onChanged(data, reprocess ? 'Reprocessing started.' : 'Processing started. This can take a minute per page.')
    } catch (err) {
      setError(getErrorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  const handleRemove = async () => {
    if (!window.confirm(`Remove ${doc.original_filename}? The assessment returns to Draft.`)) return
    setBusy(true)
    setError(null)
    try {
      const { data } = await deleteDocument(assessment.id)
      onChanged(data, 'Document removed.')
    } catch (err) {
      setError(getErrorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-4 bg-slate-50 px-4 py-4">
      <dl className="grid gap-3 text-sm sm:grid-cols-3">
        <div><dt className="text-xs text-slate-500">Created by</dt><dd>{assessment.created_by_name}</dd></div>
        <div><dt className="text-xs text-slate-500">Created</dt><dd>{new Date(assessment.created_at).toLocaleString()}</dd></div>
        <div className="sm:col-span-3"><dt className="text-xs text-slate-500">Notes</dt><dd className="whitespace-pre-wrap">{assessment.notes || '—'}</dd></div>
      </dl>
      {error && <Alert>{error}</Alert>}
      {assessment.ocr_error && assessment.processing_status === 'uploaded' && (
        <Alert>Processing failed: {assessment.ocr_error}</Alert>
      )}
      {assessment.processing_status === 'processing' && (
        <Alert tone="info">Reading the document… this page updates automatically.</Alert>
      )}
      {doc ? (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-slate-200 bg-white p-3">
          <div className="text-sm">
            <div className="font-medium text-slate-900">{doc.original_filename}</div>
            <div className="text-xs text-slate-500">
              {formatFileSize(doc.file_size)} · uploaded by {doc.uploaded_by_name} on {new Date(doc.uploaded_at).toLocaleString()}
            </div>
          </div>
          <div className="flex gap-2">
            <button className={`${secondaryButtonClass} px-3 py-1 text-sm`} onClick={() => setPreviewing(true)} type="button">Preview</button>
            <button className={`${secondaryButtonClass} px-3 py-1 text-sm`} onClick={handleDownload} type="button">Download</button>
            {canDelete && !DOCUMENT_LOCKED_STATUSES.includes(assessment.processing_status) && (
              <button className="px-3 py-1 text-sm font-medium text-red-600 hover:underline disabled:opacity-60" disabled={busy} onClick={handleRemove} type="button">
                Remove
              </button>
            )}
          </div>
        </div>
      ) : canWrite ? (
        <DocumentUpload assessmentId={assessment.id} onUploaded={(data) => onChanged(data, 'Document uploaded.')} />
      ) : (
        <p className="text-sm text-slate-500">No document uploaded yet.</p>
      )}
      {doc && (canWrite || REVIEWABLE_STATUSES.includes(assessment.processing_status)) && (
        <div className="flex flex-wrap gap-2">
          {REVIEWABLE_STATUSES.includes(assessment.processing_status) && (
            <Link
              className={`${primaryButtonClass} px-3 py-1 text-sm`}
              to={`/learners/${assessment.learner_id}/assessments/${assessment.id}/review`}
            >
              Review text
            </Link>
          )}
          {canWrite && PROCESSABLE_STATUSES.includes(assessment.processing_status) && (
            <button
              className={`${assessment.processing_status === 'uploaded' ? primaryButtonClass : secondaryButtonClass} px-3 py-1 text-sm`}
              disabled={busy}
              onClick={handleProcess}
              type="button"
            >
              {assessment.processing_status === 'uploaded' ? (assessment.ocr_error ? 'Try processing again' : 'Process document') : 'Reprocess'}
            </button>
          )}
        </div>
      )}
      {canManageStatus && <StatusControl assessment={assessment} onChanged={onChanged} />}
      {previewing && doc && (
        <DocumentPreview assessmentId={assessment.id} document={doc} onClose={() => setPreviewing(false)} />
      )}
    </div>
  )
}

export default function AssessmentsTab({ learner, onChanged }) {
  const { user } = useAuth()
  const canWrite = ASSESSMENT_WRITER_ROLES.includes(user.role)
  const canDelete = DOCUMENT_DELETER_ROLES.includes(user.role)
  const canManageStatus = STATUS_MANAGER_ROLES.includes(user.role)

  const [data, setData] = useState({ items: [], total: 0 })
  const [loadState, setLoadState] = useState({ loading: true, error: null })
  const [creating, setCreating] = useState(false)
  const [expandedId, setExpandedId] = useState(null)
  const [message, setMessage] = useState(null)
  const [reloadKey, setReloadKey] = useState(0)

  useEffect(() => {
    let active = true
    listAssessments(learner.id)
      .then(({ data: result }) => {
        if (!active) return
        setData(result)
        setLoadState({ loading: false, error: null })
      })
      .catch((err) => { if (active) setLoadState({ loading: false, error: getErrorMessage(err) }) })
    return () => { active = false }
  }, [learner.id, reloadKey])

  // While any document is being processed, poll until the worker finishes it.
  const anyProcessing = data.items.some((a) => a.processing_status === 'processing')
  useEffect(() => {
    if (!anyProcessing) return undefined
    const timer = setInterval(() => {
      listAssessments(learner.id)
        .then(({ data: result }) => {
          setData(result)
          if (!result.items.some((a) => a.processing_status === 'processing')) onChanged?.()
        })
        .catch(() => {}) // keep polling quietly; the next tick may succeed
    }, PROCESSING_POLL_MS)
    return () => clearInterval(timer)
  }, [anyProcessing, learner.id, onChanged])

  const refresh = (text) => {
    setMessage(text)
    setReloadKey((k) => k + 1)
    onChanged?.()
  }

  const handleCreate = async (payload) => {
    const { data: created } = await createAssessment(payload)
    setCreating(false)
    setExpandedId(created.id)
    refresh('Assessment created. Upload its document below.')
  }

  return (
    <div className="space-y-4 py-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-slate-600">Informal assessments from the section adviser and formal psychologist reports.</p>
        {canWrite && !creating && (
          <button className={primaryButtonClass} onClick={() => { setMessage(null); setCreating(true) }} type="button">
            New assessment
          </button>
        )}
      </div>

      {message && <Alert tone="success">{message}</Alert>}

      {creating && (
        <div className="rounded-lg border border-slate-200 p-4">
          <AssessmentForm learnerId={learner.id} onCancel={() => setCreating(false)} onSubmit={handleCreate} />
        </div>
      )}

      {loadState.error && <Alert>{loadState.error}</Alert>}

      <div className="overflow-x-auto rounded-lg border border-slate-200">
        <table className="min-w-full text-left text-sm">
          <thead className="bg-slate-50 text-slate-600">
            <tr>
              <th className="px-4 py-3 font-medium">Date</th>
              <th className="px-4 py-3 font-medium">Type</th>
              <th className="px-4 py-3 font-medium">Assessor</th>
              <th className="px-4 py-3 font-medium">Document</th>
              <th className="px-4 py-3 font-medium">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {loadState.loading && (
              <tr><td className="px-4 py-6 text-center text-slate-500" colSpan={5}>Loading assessments…</td></tr>
            )}
            {!loadState.loading && !loadState.error && data.items.length === 0 && (
              <tr><td className="px-4 py-6 text-center text-slate-500" colSpan={5}>No assessments for this learner yet.</td></tr>
            )}
            {data.items.map((a) => {
              const expanded = expandedId === a.id
              return [
                <tr
                  aria-expanded={expanded}
                  className="cursor-pointer hover:bg-slate-50"
                  key={a.id}
                  onClick={() => setExpandedId(expanded ? null : a.id)}
                  onKeyDown={(e) => { if (e.key === 'Enter') setExpandedId(expanded ? null : a.id) }}
                  tabIndex={0}
                >
                  <td className="px-4 py-3">{formatDate(a.assessment_date)}</td>
                  <td className="px-4 py-3">{TYPE_LABELS[a.assessment_type] ?? a.assessment_type}</td>
                  <td className="px-4 py-3">{a.assessor}</td>
                  <td className="px-4 py-3 text-slate-600">{a.document ? a.document.original_filename : <span className="text-slate-400">None</span>}</td>
                  <td className="px-4 py-3"><AssessmentStatusBadge status={a.processing_status} /></td>
                </tr>,
                expanded && (
                  <tr key={`${a.id}-details`}>
                    <td className="p-0" colSpan={5}>
                      <AssessmentDetails assessment={a} canDelete={canDelete} canManageStatus={canManageStatus} canWrite={canWrite} onChanged={(_, text) => refresh(text)} />
                    </td>
                  </tr>
                ),
              ]
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
