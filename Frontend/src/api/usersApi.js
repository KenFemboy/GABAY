import client from './client'

export const listUsers = (params = {}) => client.get('/users', { params })

// Active Teachers ({ id, name }) for assigning learners; Coordinator/Admin only.
export const listTeachers = () => client.get('/users/teachers')

export const createUser = (data) => client.post('/users', data)

export const updateUser = (userId, data) => client.patch(`/users/${userId}`, data)
