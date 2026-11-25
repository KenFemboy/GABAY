import { useState } from 'react'

import { updateAssessmentStatus } from '../../api/assessmentApi'
import Alert from '../../shared/components/Alert'
import { secondaryButtonClass } from '../../shared/forms/styles'
import { getErrorMessage } from '../../shared/utils/apiError'
import { PROCESSING_STATUS } from './constants'

const label = (status) => PROCESSING_STATUS[status]?.label ?? status

function confirmMessage(current, target) {
  if (target === 'finalized') return 'Finalize this assessment? Its document can no longer be removed.'
  if (current === 'finalized') return 'Reopen this finalized assessment for review?'
  return null
}

/** Coordinator-only buttons for the next allowed statuses (sent by the backend). */
export default function StatusControl({ assessment, onChanged }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const targets = assessment.next_statuses ?? []
  if (targets.length === 0) return null

  const move = async (target) => {
    const message = confirmMessage(assessment.processing_status, target)
    if (message && !window.confirm(message)) return
    setBusy(true)
    setError(null)
    try {
      const { data } = await updateAssessmentStatus(assessment.id, target)
      onChanged(data, `Status changed to ${label(target)}.`)
    } catch (err) {
      setError(getErrorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="text-xs text-slate-500">Move to:</span>
        {targets.map((target) => (
          <button
            className={`${secondaryButtonClass} px-3 py-1 text-sm`}
            disabled={busy}
            key={target}
            onClick={() => move(target)}
            type="button"
          >
            {assessment.processing_status === 'finalized' ? `Reopen (${label(target)})` : label(target)}
          </button>
        ))}
      </div>
      {error && <Alert>{error}</Alert>}
    </div>
  )
}
