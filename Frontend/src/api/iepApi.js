import client from './client'

export const listIeps = (learnerId) => client.get(`/learners/${learnerId}/ieps`)
/** Creates a draft and imports approved findings + accepted goals: { findings_added, goals_added, iep } */
export const createIep = (learnerId) => client.post(`/learners/${learnerId}/ieps`)
export const getIep = (id) => client.get(`/ieps/${id}`)
export const updateIep = (id, data) => client.patch(`/ieps/${id}`, data)
export const reimportIep = (id) => client.post(`/ieps/${id}/import`)
export const discardIep = (id) => client.delete(`/ieps/${id}`)
export const finalizeIep = (id) => client.post(`/ieps/${id}/finalize`)
export const amendIep = (id, reason) => client.post(`/ieps/${id}/amend`, { reason })

export const addIepFinding = (id, data) => client.post(`/ieps/${id}/findings`, data)
export const updateIepFinding = (id, findingId, data) => client.patch(`/ieps/${id}/findings/${findingId}`, data)
export const deleteIepFinding = (id, findingId) => client.delete(`/ieps/${id}/findings/${findingId}`)

/** data.goal_id = from the goal bank; omit for a custom goal. */
export const addIepGoal = (id, data) => client.post(`/ieps/${id}/goals`, data)
export const updateIepGoal = (id, goalId, data) => client.patch(`/ieps/${id}/goals/${goalId}`, data)
export const deleteIepGoal = (id, goalId) => client.delete(`/ieps/${id}/goals/${goalId}`)
export const reorderIepGoals = (id, ids) => client.put(`/ieps/${id}/goals/order`, { ids })

/** Downloads the DOCX generated from the saved record. */
export async function downloadIep(id) {
  const response = await client.get(`/ieps/${id}/document`, { responseType: 'blob' })
  const disposition = response.headers['content-disposition'] ?? ''
  const name = /filename="([^"]+)"/.exec(disposition)?.[1] ?? `IEP_${id}.docx`
  const url = URL.createObjectURL(response.data)
  const link = document.createElement('a')
  link.href = url
  link.download = name
  document.body.appendChild(link)
  link.click()
  link.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
