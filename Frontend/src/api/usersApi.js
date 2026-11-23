import client from './client'

export const listUsers = (params = {}) => client.get('/users', { params })

export const createUser = (data) => client.post('/users', data)

export const updateUser = (userId, data) => client.patch(`/users/${userId}`, data)
