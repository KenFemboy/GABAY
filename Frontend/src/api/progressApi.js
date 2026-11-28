import client from './client'

/** { iep_id, iep_version, goals: [goal progress with status, points, aim line] } */
export const getGoalProgress = (learnerId) => client.get(`/learners/${learnerId}/progress/goals`)
export const getOneGoalProgress = (iepGoalId) => client.get(`/iep-goals/${iepGoalId}/progress`)
export const listProgress = (learnerId, params = {}) => client.get(`/learners/${learnerId}/progress`, { params })
export const createProgress = (learnerId, data) => client.post(`/learners/${learnerId}/progress`, data)
export const updateProgress = (id, data) => client.patch(`/progress/${id}`, data)
export const deleteProgress = (id) => client.delete(`/progress/${id}`)
/** params: { types?: 'ilaw,probe,...', from?, to? } */
export const getTimeline = (learnerId, params = {}) => client.get(`/learners/${learnerId}/timeline`, { params })
/** params: { status?: 'below_aim,no_recent_data,...' } */
export const getAttention = (params = {}) => client.get('/progress/attention', { params })
