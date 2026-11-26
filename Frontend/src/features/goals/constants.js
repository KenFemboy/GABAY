import { ROLES } from '../../auth/roles'

// Values must match Backend/app/models/goal.py.
export const GOAL_MANAGER_ROLES = [ROLES.SNED_COORDINATOR]
export const GOAL_READER_ROLES = [ROLES.SNED_COORDINATOR, ROLES.SCHOOL_HEAD, ROLES.TEACHER]

export const GOAL_STATUS = {
  draft: { label: 'Draft', className: 'bg-amber-100 text-amber-800' },
  active: { label: 'Active', className: 'bg-emerald-100 text-emerald-700' },
  archived: { label: 'Archived', className: 'bg-slate-200 text-slate-600' },
}

export const MEASUREMENT_METHODS = [
  { value: 'percent_accuracy', label: 'Percent accuracy' },
  { value: 'trials', label: 'Trials (e.g. 4 of 5)' },
  { value: 'frequency', label: 'Frequency (count)' },
  { value: 'duration', label: 'Duration' },
  { value: 'rate', label: 'Rate (e.g. words per minute)' },
  { value: 'rubric', label: 'Rubric level' },
  { value: 'checklist', label: 'Checklist' },
]
export const METHOD_LABELS = Object.fromEntries(MEASUREMENT_METHODS.map((m) => [m.value, m.label]))

export const TARGET_UNITS = [
  { value: 'percent', label: '%' },
  { value: 'trials', label: 'trials' },
  { value: 'count', label: 'times' },
  { value: 'minutes', label: 'minutes' },
  { value: 'wpm', label: 'words per minute' },
  { value: 'level', label: 'rubric level' },
]
export const UNIT_LABELS = Object.fromEntries(TARGET_UNITS.map((u) => [u.value, u.label]))

export const GRADE_BANDS = [
  { value: 'any', label: 'Any grade' },
  { value: 'K-3', label: 'K–3' },
  { value: '4-6', label: '4–6' },
  { value: '7-10', label: '7–10' },
  { value: '11-12', label: '11–12' },
]
export const GRADE_BAND_LABELS = Object.fromEntries(GRADE_BANDS.map((g) => [g.value, g.label]))

export function formatTarget(version) {
  const value = Number.isInteger(version.target_value) ? version.target_value : version.target_value.toFixed(1)
  const unit = UNIT_LABELS[version.target_unit] ?? version.target_unit
  return version.target_unit === 'percent' ? `${value}%` : `${value} ${unit}`
}

/** Rough check used as a hint only: a measurable goal names a number and a condition. */
export function measurabilityHints(statement) {
  const hints = []
  if (statement && !/\d/.test(statement)) hints.push('The statement has no number (e.g. 80%, 4 of 5 trials).')
  if (statement && !/\b(given|when|during|after|using|in|with)\b/i.test(statement)) {
    hints.push('Consider stating the condition (e.g. "Given…", "During…").')
  }
  if (statement && !/\bwill\b/i.test(statement)) hints.push('State the expected behavior ("the learner will…").')
  return hints
}
