// One risk ramp, used by the map, the legend, the watchlist and the panels,
// so a colour always means the same number everywhere on screen.
//
// This is a SEQUENTIAL ramp - one hue, light to dark - not a green-to-red
// rainbow. Two reasons. Technically, risk is a magnitude, and magnitude is
// encoded by lightness; a rainbow makes readers decode hue order, and the
// green-red pair is exactly the one red-green colourblind officers cannot
// separate. Operationally, only ~5% of district-windows have a cash-out, so
// the bottom of the ramp sits close to the page colour: quiet districts
// recede and the eye lands on the live corridors without being asked to.
export const RISK_STOPS = [
  { at: 0.00, color: '#eceae3' },   // near-zero: warm grey, recedes into the page
  { at: 0.08, color: '#f2ddc8' },
  { at: 0.20, color: '#eac39f' },
  { at: 0.40, color: '#dfa277' },
  { at: 0.60, color: '#d07d51' },
  { at: 0.80, color: '#b85c37' },
  { at: 0.92, color: '#8f3d22' },   // highest risk: deep clay
]

export function riskColor(risk) {
  if (risk === null || risk === undefined || Number.isNaN(risk)) return '#f2f1ec'
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
