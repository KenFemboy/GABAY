import client from './client'

/** options: { top_k?, min_score?, same_domain?, use_grade_band? } */
export const runMatching = (learnerId, options = {}) => client.post(`/learners/${learnerId}/matching-runs`, options)
export const listRuns = (learnerId) => client.get(`/learners/${learnerId}/matching-runs`)
/** { run, manual, selected, approved_need_count } */
export const getLatestRecommendations = (learnerId) => client.get(`/learners/${learnerId}/recommendations/latest`)
export const getSelectedGoals = (learnerId) => client.get(`/learners/${learnerId}/selected-goals`)

/** edits: { edited_statement?, edited_target_value?, edited_criterion? } */
export const acceptRecommendation = (id, edits = {}) => client.post(`/recommendations/${id}/accept`, edits)
export const editRecommendation = (id, edits) => client.patch(`/recommendations/${id}`, edits)
export const rejectRecommendation = (id, reason) => client.post(`/recommendations/${id}/reject`, { reason: reason || null })
export const resetRecommendation = (id) => client.post(`/recommendations/${id}/reset`)
export const addManualGoal = (learnerId, data) => client.post(`/learners/${learnerId}/recommendations`, data)
export const removeManualGoal = (id) => client.delete(`/recommendations/${id}`)
