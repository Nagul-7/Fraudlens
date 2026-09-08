// One risk ramp, used by the map, the legend, the watchlist and the panels,
// so a colour always means the same number everywhere on screen.
// Most districts sit near zero (only ~5% of district-windows have a cash-out),
// so the bottom of the ramp is deliberately dark and desaturated: quiet
// districts recede into the map and the live corridors carry the colour.
export const RISK_STOPS = [
  { at: 0.00, color: '#16362a' },   // near-zero: dark green, recessive
  { at: 0.08, color: '#1d6046' },
  { at: 0.20, color: '#3f8f3a' },   // green
  { at: 0.40, color: '#b8a327' },   // amber
  { at: 0.60, color: '#e07a22' },
  { at: 0.80, color: '#d6452c' },   // red
  { at: 0.92, color: '#a01d18' },
]

export function riskColor(risk) {
  if (risk === null || risk === undefined || Number.isNaN(risk)) return '#1a2430'
  let c = RISK_STOPS[0].color
  for (const s of RISK_STOPS) if (risk >= s.at) c = s.color
  return c
}

export const pct = (v, digits = 1) =>
  v === null || v === undefined || Number.isNaN(v) ? '--' : `${(v * 100).toFixed(digits)}%`

// THE single risk formatter. Every surface that shows a risk score - map
// tooltip, watchlist, stats blocks, drill-down, alerts, intelligence report -
// calls this and nothing else, so the same district can never read 76.8% in one
// panel and 77% in another. There is deliberately no `digits` parameter: an
// optional precision argument is exactly how the two spellings diverged.
//
// Isotonic calibration clips its top bin to exactly 1.0, so a raw display would
// read "100%" - a claim of certainty the model does not make. On the held-out
// test months that top bin actually fires ~97% of the time, so we show ">99%".
// Same reasoning at the bottom: "<1%" rather than a bare 0%.
//
// A missing score is "no score" (this district was not scored for this window),
// which is different from "--" (nothing loaded yet); callers use "--" for the
// loading case themselves.
export function riskLabel(v) {
  if (v === null || v === undefined || Number.isNaN(v)) return 'no score'
  if (v >= 0.995) return '>99%'
  if (v > 0 && v < 0.005) return '<1%'
  return `${Math.round(v * 100)}%`
}

// Indian-style short money, matching the API's own formatting.
export function rupees(v) {
  if (v === null || v === undefined || Number.isNaN(v)) return '--'
  if (v >= 1e7) return `Rs ${(v / 1e7).toFixed(1)}Cr`
  if (v >= 1e5) return `Rs ${(v / 1e5).toFixed(1)}L`
  if (v >= 1e3) return `Rs ${(v / 1e3).toFixed(0)}K`
  return `Rs ${Math.round(v)}`
}

export const fmtWindow = (iso) => {
  if (!iso) return '--'
  const d = new Date(iso)
  const date = d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })
  const hh = String(d.getHours()).padStart(2, '0')
  const end = String((d.getHours() + 6) % 24).padStart(2, '0')
  return { date, slot: `${hh}:00 - ${end}:00` }
}
