import { ROLES } from '../../auth/roles'

export const PROGRESS_WRITER_ROLES = [ROLES.SNED_COORDINATOR, ROLES.TEACHER]
export const ATTENTION_VIEWER_ROLES = [ROLES.SNED_COORDINATOR, ROLES.SCHOOL_HEAD]

export const EVIDENCE_LABELS = {
  probe: 'Data probe',
  work_sample: 'Work sample',
  test: 'Test',
  observation: 'Observation',
  grade: 'Grade',
  ilaw: 'ILAW activity',
}

/* Status colours are the reserved status palette (never series colours) and always
   appear with an icon + label. good #0aac23 · warning #fbb315 · serious #f18a59 · critical #dc3c3d */
export const STATUS = {
  met: { label: 'Target met', icon: '✓', className: 'bg-emerald-50 text-emerald-800 border-emerald-300', dot: '#0aac23' },
  on_track: { label: 'On track', icon: '↗', className: 'bg-emerald-50 text-emerald-800 border-emerald-300', dot: '#0aac23' },
  below_aim: { label: 'Below aim line', icon: '!', className: 'bg-red-50 text-red-800 border-red-300', dot: '#dc3c3d' },
  no_recent_data: { label: 'No recent data', icon: '⏱', className: 'bg-amber-50 text-amber-900 border-amber-300', dot: '#fbb315' },
  no_data: { label: 'No data yet', icon: '○', className: 'bg-orange-50 text-orange-900 border-orange-300', dot: '#f18a59' },
  no_baseline: { label: 'No numeric baseline', icon: '?', className: 'bg-slate-100 text-slate-700 border-slate-300', dot: '#666666' },
  not_started: { label: 'Just started', icon: '·', className: 'bg-slate-100 text-slate-700 border-slate-300', dot: '#666666' },
}

/* Client-side mirror of the server rules (the server still decides). */
export const METHOD_RULES = {
  percent_accuracy: { min: 0, max: 100, step: 'any', label: 'Percent correct', allowCorrectTotal: true },
  checklist: { min: 0, max: 100, step: 'any', label: 'Percent of steps completed', allowCorrectTotal: true },
  trials: { min: 0, max: 50, step: 'any', label: 'Successful trials', needsOutOf: true },
  frequency: { min: 0, max: 1000, step: 1, label: 'Count', integer: true },
  duration: { min: 0, max: 480, step: 'any', label: 'Minutes', exclusiveMin: true },
  rate: { min: 0, max: 400, step: 'any', label: 'Per minute', exclusiveMin: true },
  rubric: { min: 0, max: 10, step: 1, label: 'Rubric level', integer: true },
}

export const GRADING_PERIODS = ['Q1', 'Q2', 'Q3', 'Q4', 'final']
