import client from './client'

export const login = (email, password) => client.post('/auth/login', { email, password })

export const getMe = () => client.get('/auth/me')

export const logout = () => client.post('/auth/logout')

export const changePassword = (currentPassword, newPassword) =>
  client.post('/auth/change-password', {
    current_password: currentPassword,
    new_password: newPassword,
  })
