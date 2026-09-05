// Thin API client. Every call goes through `request`, which turns any failure
// into a thrown Error with a readable message - the UI never sees a raw fetch
// rejection, so a dead backend shows a banner instead of a white screen.
const BASE = '/api'

async function request(path, options) {
  let res
  try {
    res = await fetch(BASE + path, options)
  } catch (e) {
    throw new Error(`Cannot reach the FraudLens API. Is it running on port 8000? (${e.message})`)
  }
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`
    try {
      const body = await res.json()
      if (body.detail) detail = body.detail
    } catch { /* response was not json; keep the status text */ }
    throw new Error(detail)
  }
  return res.json()
}

const qs = (params) => {
  const p = new URLSearchParams()
  Object.entries(params).forEach(([k, v]) => {
    if (v !== null && v !== undefined && v !== '') p.set(k, v)
  })
  const s = p.toString()
  return s ? `?${s}` : ''
}

export const getGeoJSON = () => request('/geojson/districts')
export const getStates = () => request('/states')
export const getSimState = () => request('/simulate/state')
export const getHeatmap = (params) => request(`/heatmap${qs(params)}`)
export const getAlerts = (params) => request(`/alerts${qs(params)}`)
export const getDistrict = (id, params) => request(`/districts/${id}${qs(params)}`)
export const advance = (params) => request(`/simulate/advance${qs(params)}`, { method: 'POST' })
export const resetClock = () => request('/simulate/reset', { method: 'POST' })

// Phase 6
export const getRoles = () => request('/roles')
export const getFeed = (params) => request(`/feed${qs(params)}`)
export const setAlertStatus = (id, status) =>
  request(`/feed/${id}/status${qs({ status })}`, { method: 'POST' })
export const dispatchAlert = (id, channel) =>
  request(`/feed/${id}/dispatch${qs({ channel })}`, { method: 'POST' })
export const getReport = (id) => request(`/feed/${id}/report`)
export const getCrossJurisdiction = (params) => request(`/cross-jurisdiction${qs(params)}`)
export const getBankExposure = (params) => request(`/bank/exposure${qs(params)}`)
