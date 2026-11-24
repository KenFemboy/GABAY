import { useEffect, useState } from 'react'

import { getDocumentUrl } from '../../api/assessmentApi'
import Alert from '../../shared/components/Alert'
import { secondaryButtonClass } from '../../shared/forms/styles'
import { getErrorMessage } from '../../shared/utils/apiError'

/**
 * Modal preview. A fresh short-lived signed URL is requested every time it
 * opens, so links are never stored or reused.
 */
export default function DocumentPreview({ assessmentId, document, onClose }) {
  const [state, setState] = useState({ url: null, error: null })

  useEffect(() => {
    let active = true
    getDocumentUrl(assessmentId)
      .then(({ data }) => { if (active) setState({ url: data.url, error: null }) })
      .catch((err) => { if (active) setState({ url: null, error: getErrorMessage(err) }) })
    return () => { active = false }
  }, [assessmentId])

  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const isPdf = document.mime_type === 'application/pdf'

  return (
    <div
      aria-label={`Preview of ${document.original_filename}`}
      aria-modal="true"
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 p-4"
      onClick={onClose}
      role="dialog"
    >
      <div className="flex h-[90vh] w-full max-w-5xl flex-col rounded-xl bg-white shadow-xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between border-b border-slate-200 px-4 py-3">
          <h2 className="truncate font-semibold text-slate-900">{document.original_filename}</h2>
          <button className={`${secondaryButtonClass} px-3 py-1 text-sm`} onClick={onClose} type="button">
            Close
          </button>
        </div>
        <div className="flex flex-1 items-center justify-center overflow-auto bg-slate-100">
          {state.error && <div className="p-4"><Alert>{state.error}</Alert></div>}
          {!state.error && !state.url && <p className="text-slate-500">Loading preview…</p>}
          {state.url && isPdf && (
            <iframe className="h-full w-full" src={state.url} title={document.original_filename} />
          )}
          {state.url && !isPdf && (
            <img alt={document.original_filename} className="max-h-full max-w-full object-contain" src={state.url} />
          )}
        </div>
      </div>
    </div>
  )
}
