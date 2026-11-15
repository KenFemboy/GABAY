import client from './client'

export const getConfigStatus = () => client.get('/config/status')
