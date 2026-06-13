import axios from 'axios'

const client = axios.create({ baseURL: '/api' })

export const fetchFleetSummary = () =>
  client.get('/fleet/summary').then(r => r.data)

export const fetchStations = (params) =>
  client.get('/stations', { params }).then(r => r.data)

export const fetchStation = (nrelId) =>
  client.get(`/stations/${nrelId}`).then(r => r.data)

export const fetchStationHealth = (nrelId) =>
  client.get(`/stations/${nrelId}/health`).then(r => r.data)

export const fetchDiagnosis = (nrelId) =>
  client.get(`/stations/${nrelId}/diagnosis`).then(r => r.data)

export const fetchAlerts = (params) =>
  client.get('/alerts', { params }).then(r => r.data)

export const resolveAlert = (alertId) =>
  client.post(`/alerts/${alertId}/resolve`).then(r => r.data)

export const triggerEtl = () =>
  client.post('/etl/run').then(r => r.data)
