import client from './client'

/** Run rule-based extraction; creates a new draft version. */
export const runExtraction = (assessmentId) => client.post(`/assessments/${assessmentId}/extractions`)

export const listExtractions = (assessmentId) => client.get(`/assessments/${assessmentId}/extractions`)

export const getExtraction = (versionId) => client.get(`/extractions/${versionId}`)

export const addFinding = (versionId, finding) => client.post(`/extractions/${versionId}/findings`, finding)

export const updateFinding = (versionId, findingId, changes) =>
  client.patch(`/extractions/${versionId}/findings/${findingId}`, changes)

export const deleteFinding = (versionId, findingId) =>
  client.delete(`/extractions/${versionId}/findings/${findingId}`)

export const reorderFindings = (versionId, findingIds) =>
  client.put(`/extractions/${versionId}/order`, { finding_ids: findingIds })

/** "Edit as new draft" */
export const copyExtraction = (versionId) => client.post(`/extractions/${versionId}/copy`)

export const approveExtraction = (versionId) => client.post(`/extractions/${versionId}/approve`)

export const discardExtraction = (versionId) => client.delete(`/extractions/${versionId}`)

/** Approved findings only (input for goal matching). */
export const getLearnerFindings = (learnerId) => client.get(`/learners/${learnerId}/findings`)
