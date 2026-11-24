import client from './client'

export const listLearners = (params = {}) => client.get('/learners', { params })

export const getLearner = (learnerId) => client.get(`/learners/${learnerId}`)

export const createLearner = (data) => client.post('/learners', data)

export const updateLearner = (learnerId, data) => client.patch(`/learners/${learnerId}`, data)

export const getLearnerSummary = (learnerId) => client.get(`/learners/${learnerId}/summary`)

export const listAssignments = (learnerId) => client.get(`/learners/${learnerId}/assignments`)

export const addAssignment = (learnerId, data) =>
  client.post(`/learners/${learnerId}/assignments`, data)

export const removeAssignment = (learnerId, assignmentId) =>
  client.delete(`/learners/${learnerId}/assignments/${assignmentId}`)
