/** Helpers for the backend's shared error format: { error: { code, message, details? } } */

export function getErrorCode(error) {
  return error?.response?.data?.error?.code ?? null
}

export function getErrorMessage(error, fallback = 'Something went wrong. Please try again.') {
  if (error?.response?.data?.error?.message) return error.response.data.error.message
  if (error?.request && !error.response) return 'Cannot reach the server. Check your connection.'
  return fallback
}

/** Returns { fieldName: message } from validation error details. */
export function getFieldErrors(error) {
  const details = error?.response?.data?.error?.details ?? []
  return Object.fromEntries(details.filter((d) => d.field).map((d) => [d.field, d.message]))
}
