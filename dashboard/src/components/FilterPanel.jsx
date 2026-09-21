import React from 'react'
import { riskColor, riskLabel, pct } from '../risk.js'

const CATEGORIES = [
  ['', 'All fraud types'],
  ['UPI', 'UPI fraud'],
  ['investment', 'Investment scam'],
  ['card', 'Card fraud'],
  ['loan_app', 'Loan app'],
  ['digital_arrest', 'Digital arrest'],
]

// Renders a fragment, not its own `.panel`: App wraps this in the single scrolling
// left panel. A second `.panel.left` here made two nested scroll containers, and the
// inner one shrank to fit and clipped the filters under whatever followed it.
// `inbox` is an optional block (the State LEA referral inbox) placed above the
// watchlist so it stays in view instead of sitting below a long list.
export default function FilterPanel({
  states, filters, setFilters, heatmap, watchlist, selectedId, onSelect, lockedState,
  bankMode, inbox,
}) {
  const set = (patch) => setFilters((f) => ({ ...f, ...patch }))
  const above = heatmap ? heatmap.districts.filter((d) => d.risk >= filters.threshold).length : 0

  return (
    <>
      <div className="section">
        <h2>Filters</h2>

        <div className="field">
          <label>State</label>
          {lockedState ? (
            <>
              <select value={lockedState} disabled>
                <option value={lockedState}>{lockedState}</option>
              </select>
              <div style={{ fontSize: 10, color: 'var(--ink-3)', marginTop: 5, lineHeight: 1.45 }}>
                Locked to your jurisdiction. Other states are withheld by the
                server, not hidden by this filter.
              </div>
            </>
          ) : (
            <select value={filters.state} onChange={(e) => set({ state: e.target.value })}>
              <option value="">All India ({states.length} states/UTs)</option>
              {states.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          )}
        </div>

        <div className="field">
          <label>Fraud category</label>
          <select value={filters.category} onChange={(e) => set({ category: e.target.value })}>
            {CATEGORIES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
          {filters.category && (
            <div style={{ fontSize: 10, color: 'var(--ink-3)', marginTop: 5, lineHeight: 1.45 }}>
              Shows districts holding money from this fraud type. Risk scores are
              not per-category, so the ranking is unchanged.
            </div>
          )}
        </div>

        {/* threshold and watchlist size are intelligence controls, not bank tools */}
        {!bankMode && (
        <>
        <div className="field">
          <div className="range-row">
            <label>Alert threshold</label>
            <span className="range-val mono">{pct(filters.threshold, 0)}</span>
          </div>
          <input type="range" min="0" max="0.95" step="0.05" value={filters.threshold}
                 onChange={(e) => set({ threshold: Number(e.target.value) })} />
          <div style={{ fontSize: 10.5, color: 'var(--ink-3)' }}>
            <span className="mono">{above}</span> districts at or above this now
          </div>
        </div>

        <div className="field">
          <label>Watchlist size (top-K)</label>
          <div className="kchips">
            {[10, 25, 50].map((k) => (
              <div key={k} className={`kchip ${filters.topK === k ? 'on' : ''}`}
                   onClick={() => set({ topK: k })}>{k}</div>
            ))}
          </div>
          <div style={{ fontSize: 10.5, color: 'var(--ink-3)', marginTop: 5 }}>
            {(filters.topK / 724 * 100).toFixed(1)}% of India's 724 districts
          </div>
        </div>
        </>
        )}
      </div>

      {/* National statistics and the ranked watchlist are crime intelligence.
          A bank role gets neither - its own exposure is in the right panel. */}
      {bankMode ? (
        <div className="section">
          <div className="segregation-box compact" style={{ margin: 0 }}>
            <strong>National view withheld</strong>
            <p>District rankings, risk statistics and the national watchlist are
               crime intelligence and are not available to bank roles.</p>
            <p>Your institution's ATM and account exposure is shown on the right.</p>
          </div>
        </div>
      ) : (
      <>
      <div className="section">
        <h2>This window</h2>
        <div className="stat-row">
          <span className="k">Districts scored</span>
          <span className="v mono">{heatmap ? heatmap.n_districts : '--'}</span>
        </div>
        <div className="stat-row">
          <span className="k">Highest risk</span>
          <span className="v mono">{heatmap ? riskLabel(heatmap.risk_max) : '--'}</span>
        </div>
        <div className="stat-row">
          <span className="k">Above threshold</span>
          <span className="v mono">{heatmap ? above : '--'}</span>
        </div>
      </div>

      {inbox}

      <div className="section" style={{ flex: 1 }}>
        <h2>Watchlist &middot; top {filters.topK}</h2>
        {!watchlist.length && <div className="empty">No districts match these filters.</div>}
        {watchlist.map((d) => (
          <div key={d.district_id}
               className={`watch-item ${d.district_id === selectedId ? 'sel' : ''}`}
               onClick={() => onSelect(d.district_id)}>
            <span className="watch-rank mono">{d.rank}</span>
            <span className="watch-swatch" style={{ background: riskColor(d.risk) }} />
            <span className="watch-name">
              <div className="n">{d.name}</div>
              <div className="s">{d.state}</div>
            </span>
            <span className="watch-risk mono">{riskLabel(d.risk)}</span>
          </div>
        ))}
      </div>
      </>
      )}
    </>
  )
}
