import { ROLES } from '../../auth/roles'

export const EVALUATION_WRITER_ROLES = [ROLES.SNED_COORDINATOR, ROLES.TEACHER]
export const EVALUATION_FINALIZER_ROLES = [ROLES.SNED_COORDINATOR]

export const RATINGS = [
  { value: 'met', label: 'Goal met' },
  { value: 'progressing', label: 'Progressing' },
  { value: 'limited_progress', label: 'Limited progress' },
  { value: 'insufficient_evidence', label: 'Not enough evidence' },
]
export const RATING_LABELS = Object.fromEntries(RATINGS.map((r) => [r.value, r.label]))

/** Human-readable description of an evidence ID from the stored snapshot. */
export function describeEvidence(snapshot, id) {
  if (!snapshot) return id
  const find = (key) => (snapshot[key] ?? []).find((x) => x.id === id)
  const g = find('goals')
  if (g) return `${id}: goal – ${g.statement}`
  const f = find('findings')
  if (f) return `${id}: ${f.category.replace('_', ' ')} – ${f.text}`
  const p = find('progress')
  if (p) return `${id}: ${p.type.replace('_', ' ')} (${p.goal}), week ${p.week}: ${p.value}${p.unit === 'percent' ? '%' : ` ${p.unit}`}`
  const a = find('activities')
  if (a) return `${id}: activity, week ${a.week} – ${a.title}`
  const o = find('observations')
  if (o) return `${id}: observation, week ${o.week} – ${o.note}`
  const r = find('grades')
  if (r) return `${id}: grade – ${r.subject} ${r.period}: ${r.value}`
  return id
}
