import { ROLES } from '../../auth/roles'

export const IEP_EDITOR_ROLES = [ROLES.SNED_COORDINATOR, ROLES.TEACHER]
export const IEP_FINALIZER_ROLES = [ROLES.SNED_COORDINATOR]

export const IEP_STATUS = {
  draft: { label: 'Draft', className: 'bg-amber-100 text-amber-800' },
  finalized: { label: 'Finalized', className: 'bg-emerald-100 text-emerald-700' },
  superseded: { label: 'Superseded', className: 'bg-slate-200 text-slate-600' },
}

export const GOAL_SOURCE_LABELS = {
  accepted_recommendation: 'Accepted suggestion',
  goal_bank: 'Goal bank',
  custom: 'Custom goal',
}

export const formatDate = (iso) => (iso ? new Date(`${iso}T00:00:00`).toLocaleDateString() : '—')

/** Three checkpoints at 1/4, 2/4, 3/4 of the period plus the end date (mirrors the backend). */
export function quarterlyDates(start, end) {
  if (!start || !end) return []
  const s = new Date(`${start}T00:00:00Z`)
  const e = new Date(`${end}T00:00:00Z`)
  const span = (e - s) / 86400000
  return [1, 2, 3, 4].map((i) => {
    const d = new Date(s.getTime() + Math.round((span * i) / 4) * 86400000)
    return d.toISOString().slice(0, 10)
  })
}
