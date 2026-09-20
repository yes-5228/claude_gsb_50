import http from './client.js'

export const listStandardVersions = () => http.get('/standards/versions')
export const getStandardVersion = (id) => http.get(`/standards/versions/${id}`)
export const createStandardVersion = (payload) => http.post('/standards/versions', payload)
export const updateStandardVersion = (id, payload) => http.put(`/standards/versions/${id}`, payload)
export const deleteStandardVersion = (id) => http.delete(`/standards/versions/${id}`)
export const resolveStandard = (measuredAt) =>
  http.get('/standards/resolve', { params: measuredAt ? { measured_at: measuredAt } : {} })
