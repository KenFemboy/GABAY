import { ROLES } from '../../auth/roles'

// Values must match Backend/app/models/assessment.py.
export const ASSESSMENT_TYPES = [
  { value: 'informal', label: 'Informal (section adviser)' },
  { value: 'formal', label: 'Formal (psychologist report)' },
]

export const TYPE_LABELS = { informal: 'Informal', formal: 'Formal' }

export const PROCESSING_STATUS = {
  draft: { label: 'Draft', className: 'bg-slate-200 text-slate-700' },
  uploaded: { label: 'Uploaded', className: 'bg-sky-100 text-sky-700' },
  processing: { label: 'Processing', className: 'bg-amber-100 text-amber-800' },
  processed: { label: 'Processed', className: 'bg-indigo-100 text-indigo-700' },
  needs_review: { label: 'Needs review', className: 'bg-orange-100 text-orange-800' },
  finalized: { label: 'Finalized', className: 'bg-emerald-100 text-emerald-700' },
}

export const ASSESSMENT_WRITER_ROLES = [ROLES.SNED_COORDINATOR, ROLES.TEACHER]
export const DOCUMENT_DELETER_ROLES = [ROLES.SNED_COORDINATOR]
export const STATUS_MANAGER_ROLES = [ROLES.SNED_COORDINATOR]
// The backend refuses to remove documents in these statuses.
export const DOCUMENT_LOCKED_STATUSES = ['processing', 'finalized']

// Mirrors the backend checks for quicker feedback; the backend still decides.
export const ACCEPTED_EXTENSIONS = ['pdf', 'jpg', 'jpeg', 'png']
export const ACCEPT_ATTRIBUTE = '.pdf,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png'
export const MAX_UPLOAD_MB = 15

export function formatFileSize(bytes) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

// OCR (Stage 5). The backend sends the real threshold in the OCR summary
// (OCR_REVIEW_CONFIDENCE); this is only the fallback.
export const DEFAULT_REVIEW_CONFIDENCE = 70
export const PROCESSABLE_STATUSES = ['uploaded', 'processed', 'needs_review']
export const REVIEWABLE_STATUSES = ['processed', 'needs_review', 'finalized']
export const EDITABLE_OCR_STATUSES = ['processed', 'needs_review']
export const PROCESSING_POLL_MS = 3000

export function confidenceTone(page, threshold = DEFAULT_REVIEW_CONFIDENCE) {
  if (page.status === 'failed') return 'bg-red-100 text-red-700 border-red-200'
  if (page.source === 'text_layer') return 'bg-slate-100 text-slate-700 border-slate-200'
  if (page.confidence == null || page.confidence < threshold) return 'bg-amber-100 text-amber-800 border-amber-200'
  return 'bg-emerald-100 text-emerald-700 border-emerald-200'
}

export function pageSourceLabel(page) {
  if (page.status === 'failed') return 'Failed'
  if (page.source === 'text_layer') return 'PDF text'
  return page.confidence == null ? 'OCR' : `OCR · ${Math.round(page.confidence)}%`
}
