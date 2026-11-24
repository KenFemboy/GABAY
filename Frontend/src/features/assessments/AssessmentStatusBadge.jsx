import { PROCESSING_STATUS } from './constants'

export default function AssessmentStatusBadge({ status }) {
  const info = PROCESSING_STATUS[status] ?? { label: status, className: 'bg-slate-200 text-slate-700' }
  return (
    <span className={`whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium ${info.className}`}>
      {info.label}
    </span>
  )
}
