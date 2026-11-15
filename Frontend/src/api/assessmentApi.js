import client from './client'

export const getApiVersion = () => client.get('/version')
