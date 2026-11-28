import client from './client'

/** { iep: { id, version_number, school_year, start_date, end_date, goals } | null } */
export const getActiveIep = (learnerId) => client.get(`/learners/${learnerId}/ilaw/active-iep`)
/** params: { from?, to?, goal?, offset?, limit? } */
export const listEntries = (learnerId, params = {}) => client.get(`/learners/${learnerId}/ilaw`, { params })
export const createEntry = (learnerId, data) => client.post(`/learners/${learnerId}/ilaw`, data)
export const updateEntry = (entryId, data) => client.patch(`/ilaw/${entryId}`, data)
export const deleteEntry = (entryId) => client.delete(`/ilaw/${entryId}`)
export const resuggest = (entryId) => client.post(`/ilaw/${entryId}/suggest`)
export const addLink = (entryId, iepGoalId) => client.post(`/ilaw/${entryId}/links`, { iep_goal_id: iepGoalId })
export const confirmLink = (linkId) => client.post(`/ilaw-links/${linkId}/confirm`)
export const rejectLink = (linkId) => client.post(`/ilaw-links/${linkId}/reject`)
export const resetLink = (linkId) => client.post(`/ilaw-links/${linkId}/reset`)
export const changeLink = (linkId, iepGoalId) => client.post(`/ilaw-links/${linkId}/change`, { iep_goal_id: iepGoalId })
