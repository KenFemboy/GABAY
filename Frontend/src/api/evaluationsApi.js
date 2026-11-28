import client from './client'

export const listEvaluations = (learnerId) => client.get(`/learners/${learnerId}/evaluations`)
/** The exact de-identified package + { ai_enabled, ai_configured, evidence_hash, evidence_count } */
export const previewEvidence = (learnerId) => client.get(`/learners/${learnerId}/evaluations/preview`)
/** Sends the previewed package to OpenAI. On failure the server saves a manual draft (fallback_reason set). */
export const generateEvaluation = (learnerId, evidenceHash) =>
  client.post(`/learners/${learnerId}/evaluations/generate`, { evidence_hash: evidenceHash })
export const createManualEvaluation = (learnerId) => client.post(`/learners/${learnerId}/evaluations/manual`)
export const getEvaluation = (id) => client.get(`/evaluations/${id}`)
export const updateEvaluation = (id, content) => client.patch(`/evaluations/${id}`, content)
export const finalizeEvaluation = (id) => client.post(`/evaluations/${id}/finalize`)
export const discardEvaluation = (id) => client.delete(`/evaluations/${id}`)
