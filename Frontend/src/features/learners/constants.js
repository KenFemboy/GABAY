import { ROLES } from '../../auth/roles'

// Values must match the enums in Backend/app/models/learner.py.
export const GRADE_LEVELS = [
  { value: 'K', label: 'Kindergarten' },
  ...Array.from({ length: 12 }, (_, i) => ({ value: String(i + 1), label: `Grade ${i + 1}` })),
  { value: 'NG', label: 'Non-graded' },
]

export const SEX_OPTIONS = [
  { value: 'male', label: 'Male' },
  { value: 'female', label: 'Female' },
]

export const STATUS_OPTIONS = [
  { value: 'active', label: 'Active' },
  { value: 'transferred', label: 'Transferred' },
  { value: 'graduated', label: 'Graduated' },
  { value: 'inactive', label: 'Inactive' },
]

export const STATUS_BADGE_CLASS = {
  active: 'bg-emerald-100 text-emerald-700',
  transferred: 'bg-amber-100 text-amber-800',
  graduated: 'bg-indigo-100 text-indigo-700',
  inactive: 'bg-slate-200 text-slate-600',
}

// Order matches the tabs on the learner profile and the backend summary.
export const PROFILE_TABS = [
  { key: 'assessments', label: 'Assessments' },
  { key: 'iep', label: 'IEP' },
  { key: 'ilaw', label: 'ILAW' },
  { key: 'progress', label: 'Progress' },
  { key: 'evaluations', label: 'Evaluations' },
]

export const LEARNER_READER_ROLES = [ROLES.SNED_COORDINATOR, ROLES.SCHOOL_HEAD, ROLES.TEACHER]
export const LEARNER_EDITOR_ROLES = [ROLES.SNED_COORDINATOR]

const labelMap = (options) => Object.fromEntries(options.map((o) => [o.value, o.label]))
export const GRADE_LABELS = labelMap(GRADE_LEVELS)
export const SEX_LABELS = labelMap(SEX_OPTIONS)
export const STATUS_LABELS = labelMap(STATUS_OPTIONS)

/** Current school year, e.g. "2025-2026" (Philippine SY starts around June). */
export function currentSchoolYear(today = new Date()) {
  const start = today.getMonth() >= 5 ? today.getFullYear() : today.getFullYear() - 1
  return `${start}-${start + 1}`
}
