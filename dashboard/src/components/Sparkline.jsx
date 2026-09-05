import React from 'react'
import { riskColor } from '../risk.js'

// 30 days of 6-hour windows is 120 points, which is an unreadable scribble at
// panel width. So the bold line is the DAILY PEAK risk (one point per day) and
// the raw 6-hour series sits faintly behind it, keeping the diurnal detail
// visible without letting it dominate. Points from the held-out test period are
// solid; anything reaching back into the calibration period is shaded, so the
// distinction is on the chart rather than buried in a tooltip.
export default function Sparkline({ history, width = 340, height = 74 }) {
  if (!history || history.length < 2) return <div className="empty">Not enough history yet.</div>

  const pad = 4
  const w = width - pad * 2
  const h = height - pad * 2

  // group into days
  const days = []
  history.forEach((p) => {
    const key = p.window_start.slice(0, 10)
    const last = days[days.length - 1]
    if (last && last.key === key) {
      last.peak = Math.max(last.peak, p.risk)
      last.withdrawals += p.actual_withdrawals
      last.oos = last.oos && p.is_out_of_sample
    } else {
      days.push({ key, peak: p.risk, withdrawals: p.actual_withdrawals, oos: p.is_out_of_sample })
    }
  })

  const xRaw = (i) => pad + (i / (history.length - 1)) * w
  const xDay = (i) => pad + (days.length === 1 ? w / 2 : (i / (days.length - 1)) * w)
  const y = (v) => pad + h - Math.max(0, Math.min(1, v)) * h

  const rawLine = history.map((p, i) => `${i ? 'L' : 'M'}${xRaw(i).toFixed(1)},${y(p.risk).toFixed(1)}`).join(' ')
  const dayLine = days.map((d, i) => `${i ? 'L' : 'M'}${xDay(i).toFixed(1)},${y(d.peak).toFixed(1)}`).join(' ')
  const dayArea = `${dayLine} L${xDay(days.length - 1).toFixed(1)},${pad + h} L${pad},${pad + h} Z`

  const firstOOS = history.findIndex((p) => p.is_out_of_sample)
  const anyInSample = firstOOS > 0
  const maxWd = Math.max(...days.map((d) => d.withdrawals), 1)
  const lastDay = days[days.length - 1]

  return (
    <div>
      <svg width={width} height={height} style={{ display: 'block' }}>
        {[0.25, 0.5, 0.75].map((g) => (
          <line key={g} x1={pad} x2={pad + w} y1={y(g)} y2={y(g)} stroke="#24303f" strokeWidth="1" />
        ))}
        {anyInSample && (
          <rect x={pad} y={pad} width={Math.max(xRaw(firstOOS) - pad, 0)} height={h}
                fill="rgba(107,127,150,0.13)" />
        )}
        {/* daily bars of what actually happened, along the base */}
        {days.map((d, i) => d.withdrawals > 0 && (
          <line key={`w${i}`} x1={xDay(i)} x2={xDay(i)} y1={pad + h}
                y2={pad + h - (d.withdrawals / maxWd) * 13}
                stroke="#e07a22" strokeWidth="2.4" opacity="0.55" strokeLinecap="round" />
        ))}
        <path d={dayArea} fill="rgba(61,139,253,0.13)" />
        <path d={rawLine} fill="none" stroke="#3d8bfd" strokeWidth="0.8" opacity="0.34" />
        <path d={dayLine} fill="none" stroke="#5b9dfd" strokeWidth="1.9"
              strokeLinejoin="round" strokeLinecap="round" />
        <circle cx={xDay(days.length - 1)} cy={y(lastDay.peak)} r="3.6"
                fill={riskColor(lastDay.peak)} stroke="#0b0f14" strokeWidth="1.6" />
      </svg>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 9.5,
                    color: 'var(--ink-3)', marginTop: 2 }}>
        <span>{days.length} days ago</span>
        <span><span style={{ color: '#5b9dfd' }}>daily peak risk</span>
              {'  '}<span style={{ color: '#e07a22' }}>actual cash-outs</span></span>
        <span>now</span>
      </div>
      {anyInSample && (
        <div style={{ fontSize: 9.5, color: 'var(--ink-3)', marginTop: 3, lineHeight: 1.4 }}>
          Shaded span predates the test period: calibration data, not out-of-sample.
        </div>
      )}
    </div>
  )
}
