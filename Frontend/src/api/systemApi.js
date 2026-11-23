import client from './client'

export const getHealth = () => client.get('/health')

export const getVersion = () => client.get('/version')

export const getConfigStatus = () => client.get('/config/status')
