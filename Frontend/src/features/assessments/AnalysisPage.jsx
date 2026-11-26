import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { getAssessment, getOcr } from '../../api/assessmentApi'
import {
  addFinding,
  approveExtraction,
  copyExtraction,
  deleteFinding,
  discardExtraction,
  getExtraction,
  listExtractions,
  reorderFindings,
  runExtraction,
  updateFinding,
} from '../../api/extractionApi'
import useAuth from '../../auth/useAuth'
import Alert from '../../shared/components/Alert'
import { inputClass, primaryButtonClass, secondaryButtonClass } from '../../shared/forms/styles'
import { getErrorMessage } from '../../shared/utils/apiError'
import {
  ASSESSMENT_WRITER_ROLES,
  DOMAIN_LABELS,
  EXTRACTION_APPROVER_ROLES,
  EXTRACTION_METHOD_LABELS,
  EXTRACTION_STATUS,
  FINDING_CATEGORIES,
  FINDING_DOMAINS,
  TYPE_LABELS,
} from './constants'

const smallButton = `${secondaryButtonClass} px-2 py-1 text-xs`

function VersionBadge({ status }) {
  const info = EXTRACTION_STATUS[status] ?? { label: status, className: 'bg-slate-200 text-slate-700' }
  return <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${info.className}`}>{info.label}</span>
}

const versionLabel = (v) =>
  `v${v.version_number} · ${EXTRACTION_STATUS[v.status]?.label ?? v.status} · ${EXTRACTION_METHOD_LABELS[v.method] ?? v.method}`

function DomainSelect({ value, onChange, id }) {
  return (
    <select className={`${inputClass} mt-0 py-1 text-sm`} id={id} onChange={(e) => onChange(e.target.value || null)} value={value ?? ''}>
      <option value="">No domain</option>
      {FINDING_DOMAINS.map((d) => <option key={d.value} value={d.value}>{d.label}</option>)}
    </select>
  )
}

function FindingCard({ finding, editable, isFirst, isLast, onSave, onDelete, onMove, onShowSource }) {
  const [editing, setEditing] = useState(false)
  const [form, setForm] = useState({ text: finding.text, category: finding.category, domain: finding.domain })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const startEdit = () => {
    setForm({ text: finding.text, category: finding.category, domain: finding.domain })
    setError(null)
    setEditing(true)
  }

  const save = async () => {
    setBusy(true)
    setError(null)
    try {
      await onSave(finding.id, form)
      setEditing(false)
    } catch (err) {
      setError(getErrorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <li className="rounded-lg border border-slate-200 bg-white p-3">
      {editing ? (
        <div className="space-y-2">
          <label className="sr-only" htmlFor={`f-${finding.id}`}>Finding text</label>
          <textarea
            className={`${inputClass} mt-0 min-h-20 text-sm`}
            id={`f-${finding.id}`}
            maxLength={2000}
            onChange={(e) => setForm((f) => ({ ...f, text: e.target.value }))}
            value={form.text}
          />
          <div className="grid gap-2 sm:grid-cols-2">
            <select
              aria-label="Category"
              className={`${inputClass} mt-0 py-1 text-sm`}
              onChange={(e) => setForm((f) => ({ ...f, category: e.target.value }))}
              value={form.category}
            >
              {FINDING_CATEGORIES.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
            </select>
            <DomainSelect id={`d-${finding.id}`} onChange={(domain) => setForm((f) => ({ ...f, domain }))} value={form.domain} />
          </div>
          {error && <Alert>{error}</Alert>}
          <div className="flex gap-2">
            <button className={`${primaryButtonClass} px-3 py-1 text-sm`} disabled={busy || !form.text.trim()} onClick={save} type="button">Save</button>
            <button className={`${secondaryButtonClass} px-3 py-1 text-sm`} onClick={() => setEditing(false)} type="button">Cancel</button>
          </div>
        </div>
      ) : (
        <div className="flex gap-3">
          <div className="min-w-0 flex-1 space-y-1">
            <p className="text-sm text-slate-900">{finding.text}</p>
            <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
              {finding.domain && <span className="rounded-full bg-indigo-50 px-2 py-0.5 text-indigo-700">{DOMAIN_LABELS[finding.domain] ?? finding.domain}</span>}
              {finding.origin === 'manual' && <span className="rounded-full bg-slate-100 px-2 py-0.5">Added by hand</span>}
              {finding.edited && <span className="rounded-full bg-amber-50 px-2 py-0.5 text-amber-700">Edited</span>}
              {finding.source_page != null && (
                <button className="truncate text-left text-indigo-600 hover:underline" onClick={() => onShowSource(finding)} type="button">
                  Page {finding.source_page}: “{finding.source_quote?.slice(0, 80)}{finding.source_quote?.length > 80 ? '…' : ''}”
                </button>
              )}
            </div>
          </div>
          {editable && (
            <div className="flex shrink-0 flex-col items-end gap-1">
              <div className="flex gap-1">
                <button aria-label="Move up" className={smallButton} disabled={isFirst} onClick={() => onMove(finding.id, -1)} type="button">↑</button>
                <button aria-label="Move down" className={smallButton} disabled={isLast} onClick={() => onMove(finding.id, 1)} type="button">↓</button>
              </div>
              <div className="flex gap-1">
                <button className={smallButton} onClick={startEdit} type="button">Edit</button>
                <button
                  className="px-2 py-1 text-xs font-medium text-red-600 hover:underline"
                  onClick={() => { if (window.confirm('Delete this finding?')) onDelete(finding.id) }}
                  type="button"
                >
                  Delete
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </li>
  )
}

function AddFinding({ category, onAdd }) {
  const [open, setOpen] = useState(false)
  const [text, setText] = useState('')
  const [domain, setDomain] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  if (!open) {
    return <button className="text-sm font-medium text-indigo-600 hover:underline" onClick={() => setOpen(true)} type="button">+ Add finding</button>
  }

  const submit = async () => {
    setBusy(true)
    setError(null)
    try {
      await onAdd({ category, domain, text })
      setText('')
      setDomain(null)
      setOpen(false)
    } catch (err) {
      setError(getErrorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-2 rounded-lg border border-dashed border-slate-300 p-3">
      <label className="sr-only" htmlFor={`add-${category}`}>New finding</label>
      <textarea className={`${inputClass} mt-0 min-h-16 text-sm`} id={`add-${category}`} maxLength={2000} onChange={(e) => setText(e.target.value)} placeholder="Write the finding…" value={text} />
      <DomainSelect id={`add-d-${category}`} onChange={setDomain} value={domain} />
      {error && <Alert>{error}</Alert>}
      <div className="flex gap-2">
        <button className={`${primaryButtonClass} px-3 py-1 text-sm`} disabled={busy || !text.trim()} onClick={submit} type="button">Add</button>
        <button className={`${secondaryButtonClass} px-3 py-1 text-sm`} onClick={() => setOpen(false)} type="button">Cancel</button>
      </div>
    </div>
  )
}

/** Side panel: the page text with the finding's source span highlighted. */
function SourcePanel({ assessmentId, finding, onClose }) {
  const [pages, setPages] = useState(null)
  const [error, setError] = useState(null)
  const [pageNumber, setPageNumber] = useState(finding.source_page)

  useEffect(() => {
    let active = true
    getOcr(assessmentId)
      .then(({ data }) => { if (active) setPages(data.pages) })
      .catch((err) => { if (active) setError(getErrorMessage(err)) })
    return () => { active = false }
  }, [assessmentId])

  const page = pages?.find((p) => p.page_number === pageNumber)
  const text = page ? (page.reviewed_text ?? page.raw_text) : ''
  const highlight = page && pageNumber === finding.source_page && finding.source_end <= text.length

  return (
    <aside aria-label="Source text" className="flex max-h-[80vh] flex-col rounded-lg border border-slate-200 bg-white lg:sticky lg:top-4">
      <div className="flex items-center justify-between border-b border-slate-200 px-3 py-2">
        <div className="flex items-center gap-1">
          <button className={smallButton} disabled={!pages || pageNumber <= 1} onClick={() => setPageNumber((n) => n - 1)} type="button">‹</button>
          <span className="px-2 text-sm font-medium">Page {pageNumber}{pages ? ` of ${pages.length}` : ''}</span>
          <button className={smallButton} disabled={!pages || pageNumber >= pages.length} onClick={() => setPageNumber((n) => n + 1)} type="button">›</button>
        </div>
        <button className={smallButton} onClick={onClose} type="button">Close</button>
      </div>
      <div className="overflow-auto p-3">
        {error && <Alert>{error}</Alert>}
        {!pages && !error && <p className="text-sm text-slate-500">Loading…</p>}
        {page && (
          <pre className="whitespace-pre-wrap font-sans text-sm text-slate-800">
            {highlight ? (
              <>
                {text.slice(0, finding.source_start)}
                <mark className="rounded bg-yellow-200 px-0.5">{text.slice(finding.source_start, finding.source_end)}</mark>
                {text.slice(finding.source_end)}
              </>
            ) : text}
          </pre>
        )}
      </div>
    </aside>
  )
}

export default function AnalysisPage() {
  const { learnerId, assessmentId } = useParams()
  return <Analysis assessmentId={assessmentId} key={assessmentId} learnerId={learnerId} />
}

function pickDefault(versions) {
  return (versions.find((v) => v.status === 'draft') ?? versions.find((v) => v.status === 'approved') ?? versions[0])?.id ?? null
}

function Analysis({ learnerId, assessmentId }) {
  const { user } = useAuth()
  const canWrite = ASSESSMENT_WRITER_ROLES.includes(user.role)
  const canApprove = EXTRACTION_APPROVER_ROLES.includes(user.role)

  const [load, setLoad] = useState({ loading: true, error: null })
  const [assessment, setAssessment] = useState(null)
  const [versions, setVersions] = useState([])
  const [selectedId, setSelectedId] = useState(null)
  const [version, setVersion] = useState(null)
  const [source, setSource] = useState(null)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    let active = true
    Promise.all([getAssessment(assessmentId), listExtractions(assessmentId)])
      .then(([a, v]) => {
        if (!active) return
        setAssessment(a.data)
        setVersions(v.data.items)
        setSelectedId(pickDefault(v.data.items))
        setLoad({ loading: false, error: null })
      })
      .catch((err) => { if (active) setLoad({ loading: false, error: getErrorMessage(err) }) })
    return () => { active = false }
  }, [assessmentId])

  useEffect(() => {
    if (selectedId == null) return undefined
    let active = true
    getExtraction(selectedId)
      .then(({ data }) => { if (active) setVersion(data) })
      .catch((err) => { if (active) setError(getErrorMessage(err)) })
    return () => { active = false }
  }, [selectedId])

  const refreshList = useCallback(async (selectId) => {
    const { data } = await listExtractions(assessmentId)
    setVersions(data.items)
    setSelectedId(selectId ?? pickDefault(data.items))
  }, [assessmentId])

  const act = async (fn, successText) => {
    setBusy(true)
    setError(null)
    setMessage(null)
    try {
      await fn()
      if (successText) setMessage(successText)
    } catch (err) {
      setError(getErrorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  const shown = selectedId == null ? null : version?.id === selectedId ? version : null
  const editable = Boolean(shown && shown.status === 'draft' && canWrite)
  const hasDraft = versions.some((v) => v.status === 'draft')
  const finalized = assessment?.processing_status === 'finalized'

  const handleRun = () => act(async () => {
    const { data } = await runExtraction(assessmentId)
    setVersion(data)
    await refreshList(data.id)
  }, 'Extraction finished. Review the draft below, then approve it.')

  const handleCopy = () => act(async () => {
    const { data } = await copyExtraction(shown.id)
    setVersion(data)
    await refreshList(data.id)
  }, 'A new draft was created from this version.')

  const handleApprove = () => {
    if (!window.confirm('Approve these findings? They will be used for goal matching, and any previously approved version will be superseded.')) return
    act(async () => {
      const { data } = await approveExtraction(shown.id)
      setVersion(data)
      await refreshList(data.id)
    }, 'Findings approved.')
  }

  const handleDiscard = () => {
    if (!window.confirm('Discard this draft? Its findings and edits will be deleted.')) return
    act(async () => {
      await discardExtraction(shown.id)
      setVersion(null)
      await refreshList()
    }, 'Draft discarded.')
  }

  const reloadVersion = async () => {
    const { data } = await getExtraction(shown.id)
    setVersion(data)
  }

  const handleSave = async (findingId, form) => {
    await updateFinding(shown.id, findingId, form)
    await reloadVersion()
  }

  const handleAdd = async (finding) => {
    await addFinding(shown.id, finding)
    await reloadVersion()
  }

  const handleDelete = (findingId) => act(async () => {
    await deleteFinding(shown.id, findingId)
    await reloadVersion()
  })

  // Move within the finding's category; the server stores one global order.
  const handleMove = (findingId, delta) => act(async () => {
    const all = shown.findings
    const target = all.find((f) => f.id === findingId)
    const sameCategory = all.filter((f) => f.category === target.category)
    const index = sameCategory.findIndex((f) => f.id === findingId)
    const swapWith = sameCategory[index + delta]
    if (!swapWith) return
    const ids = all.map((f) => f.id)
    const a = ids.indexOf(findingId)
    const b = ids.indexOf(swapWith.id)
    ;[ids[a], ids[b]] = [ids[b], ids[a]]
    const { data } = await reorderFindings(shown.id, ids)
    setVersion(data)
  })

  if (load.loading) return <p className="text-slate-500">Loading…</p>
  if (load.error) return <Alert>{load.error}</Alert>

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <Link className="text-sm text-indigo-600 hover:underline" to={`/learners/${learnerId}?tab=assessments`}>← Back to learner</Link>
          <h1 className="mt-1 text-xl font-semibold text-slate-900">
            Assessment analysis · {TYPE_LABELS[assessment.assessment_type] ?? assessment.assessment_type}
          </h1>
          <p className="text-sm text-slate-600">
            {new Date(`${assessment.assessment_date}T00:00:00`).toLocaleDateString()} · {assessment.assessor}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Link className={`${secondaryButtonClass} px-3 py-1 text-sm`} to={`/learners/${learnerId}/assessments/${assessmentId}/review`}>OCR text</Link>
          {canWrite && finalized && !hasDraft && (
            <button className={`${primaryButtonClass} px-3 py-1 text-sm`} disabled={busy} onClick={handleRun} type="button">
              {versions.length ? 'Run extraction again' : 'Run extraction'}
            </button>
          )}
        </div>
      </div>

      {!finalized && (
        <Alert tone="info">Finalize the assessment (after reviewing the OCR text) before running or approving extraction.</Alert>
      )}
      {message && <Alert tone="success">{message}</Alert>}
      {error && <Alert>{error}</Alert>}

      {versions.length === 0 ? (
        <p className="py-10 text-center text-slate-500">No findings have been extracted yet.</p>
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-3 rounded-lg border border-slate-200 bg-slate-50 p-3">
            <label className="text-sm text-slate-600" htmlFor="version">Version</label>
            <select className={`${inputClass} mt-0 w-auto py-1 text-sm`} id="version" onChange={(e) => setSelectedId(Number(e.target.value))} value={selectedId ?? ''}>
              {versions.map((v) => <option key={v.id} value={v.id}>{versionLabel(v)}</option>)}
            </select>
            {shown && (
              <>
                <VersionBadge status={shown.status} />
                <span className="text-xs text-slate-500">
                  {shown.finding_count} findings · created by {shown.created_by_name} {new Date(shown.created_at).toLocaleString()}
                  {shown.approved_by_name && <> · approved by {shown.approved_by_name} {new Date(shown.approved_at).toLocaleString()}</>}
                </span>
                <div className="ml-auto flex flex-wrap gap-2">
                  {editable && canApprove && (
                    <button className={`${primaryButtonClass} px-3 py-1 text-sm`} disabled={busy || shown.is_stale || !finalized} onClick={handleApprove} type="button">Approve</button>
                  )}
                  {editable && (
                    <button className="px-3 py-1 text-sm font-medium text-red-600 hover:underline" disabled={busy} onClick={handleDiscard} type="button">Discard draft</button>
                  )}
                  {canWrite && finalized && shown.status !== 'draft' && !hasDraft && (
                    <button className={`${secondaryButtonClass} px-3 py-1 text-sm`} disabled={busy} onClick={handleCopy} type="button">Edit as new draft</button>
                  )}
                </div>
              </>
            )}
          </div>

          {shown?.is_stale && (
            <Alert>The OCR text changed after these findings were extracted, so the page references may be wrong. Run extraction again.</Alert>
          )}
          {shown?.status === 'draft' && !canApprove && (
            <Alert tone="info">This draft needs the SNED Coordinator's approval before it can be used for goal matching.</Alert>
          )}

          {!shown ? (
            <p className="text-slate-500">Loading findings…</p>
          ) : (
            <div className={`grid gap-4 ${source ? 'lg:grid-cols-[1fr_24rem]' : ''}`}>
              <div className="space-y-6">
                {FINDING_CATEGORIES.map((cat) => {
                  const items = shown.findings.filter((f) => f.category === cat.value)
                  return (
                    <section aria-labelledby={`h-${cat.value}`} className="space-y-2" key={cat.value}>
                      <div className="flex items-baseline justify-between">
                        <h2 className="font-semibold text-slate-900" id={`h-${cat.value}`}>{cat.label} <span className="text-sm font-normal text-slate-500">({items.length})</span></h2>
                        {cat.hint && <span className="text-xs text-slate-500">{cat.hint}</span>}
                      </div>
                      {items.length === 0 && <p className="text-sm text-slate-500">None found.</p>}
                      <ul className="space-y-2">
                        {items.map((f, i) => (
                          <FindingCard
                            editable={editable}
                            finding={f}
                            isFirst={i === 0}
                            isLast={i === items.length - 1}
                            key={f.id}
                            onDelete={handleDelete}
                            onMove={handleMove}
                            onSave={handleSave}
                            onShowSource={setSource}
                          />
                        ))}
                      </ul>
                      {editable && <AddFinding category={cat.value} onAdd={handleAdd} />}
                    </section>
                  )
                })}
              </div>
              {source && (
                <SourcePanel assessmentId={assessmentId} finding={source} key={source.id} onClose={() => setSource(null)} />
              )}
            </div>
          )}
        </>
      )}
    </div>
  )
}
