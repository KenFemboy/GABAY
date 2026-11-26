import client from './client'

export const getTaxonomy = () => client.get('/goal-taxonomy')
export const createDomain = (data) => client.post('/goal-taxonomy/domains', data)
export const updateDomain = (id, data) => client.patch(`/goal-taxonomy/domains/${id}`, data)
export const createSkill = (data) => client.post('/goal-taxonomy/skills', data)
export const updateSkill = (id, data) => client.patch(`/goal-taxonomy/skills/${id}`, data)

export const listGoals = (params = {}) => client.get('/goals', { params })
export const getGoal = (id) => client.get(`/goals/${id}`)
export const createGoal = (data) => client.post('/goals', data)
/** Returns { goal, new_version }. */
export const updateGoal = (id, data) => client.patch(`/goals/${id}`, data)
export const activateGoal = (id) => client.post(`/goals/${id}/activate`)
export const archiveGoal = (id) => client.post(`/goals/${id}/archive`)
export const deleteGoal = (id) => client.delete(`/goals/${id}`)

export const getIndexStatus = () => client.get('/goals/index-status')
export const reindexGoals = () => client.post('/goals/reindex')
/** Semantic search over active goals: { items: [{ goal, score }] } */
export const searchGoals = (q, k = 10) => client.get('/goals/search', { params: { q, k } })
