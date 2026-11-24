import client from './client'

export const listAssessments = (learnerId, params = {}) =>
  client.get('/assessments', { params: { learner_id: learnerId, ...params } })

export const createAssessment = (data) => client.post('/assessments', data)

export const getAssessment = (assessmentId) => client.get(`/assessments/${assessmentId}`)

/** Multipart upload; `onProgress` receives 0–100. */
export const uploadDocument = (assessmentId, file, onProgress) => {
  const form = new FormData()
  form.append('file', file)
  return client.post(`/assessments/${assessmentId}/document`, form, {
    // Let the browser set the multipart boundary.
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress: (event) => {
      if (onProgress && event.total) onProgress(Math.round((event.loaded / event.total) * 100))
    },
  })
}

/** Returns { url, expires_in }: a short-lived signed URL, fetched fresh each time. */
export const getDocumentUrl = (assessmentId, { download = false } = {}) =>
  client.get(`/assessments/${assessmentId}/document`, { params: { download } })

export const deleteDocument = (assessmentId) => client.delete(`/assessments/${assessmentId}/document`)
