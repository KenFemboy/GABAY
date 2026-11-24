import { STATUS_BADGE_CLASS, STATUS_LABELS } from './constants'

export default function StatusBadge({ status }) {
  return (
    <span
      className={`rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_BADGE_CLASS[status] ?? STATUS_BADGE_CLASS.inactive}`}
    >
      {STATUS_LABELS[status] ?? status}
    </span>
  )
}
