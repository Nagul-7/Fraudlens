import React from 'react'
import Sparkline from './Sparkline.jsx'
import { riskColor, riskLabel, rupees } from '../risk.js'

const shortTime = (ts) => {
  const d = new Date(String(ts).replace(' ', 'T'))
  return `${String(d.getDate()).padStart(2, '0')} ${d.toLocaleString('en-IN', { month: 'short' })} ` +
         `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

export default function DistrictPanel({ detail, loading, error, onClose }) {
  if (loading && !detail) {
    return (
      <div className="panel right">
        <div className="center-msg"><div className="spinner" /><p>Loading district...</p></div>
      </div>
    )
  }
  if (error) {
    return (
      <div className="panel right">
        <div className="detail-head">
          <div className="dname">District unavailable</div>
          <button className="btn ghost" style={{ marginTop: 10 }} onClick={onClose}>Close</button>
        </div>
        <div className="err-box">{error}</div>
      </div>
    )
  }
  if (!detail) return null

  const d = detail
  const chains = d.live_chains
  return (
    <div className="panel right">
      <div className="detail-head">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 10 }}>
          <div>
            <div className="dname">{d.name}</div>
            <div className="dstate" style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '4px 9px' }}>
              {d.state}
              {/* is_hotspot is the static list of historically known mule corridors, NOT the model's
                  ranked watchlist. The old label ("Not on watchlist") contradicted the watchlist beside
                  it: a district ranked #1 was tagged as not being on it. */}
              <span className={`tag ${d.is_hotspot ? 'hot' : 'cold'}`}
                    title="Whether this district is one of the historically known mule corridors. Independent of its current risk rank.">
                {d.is_hotspot ? 'Known corridor' : 'Not a known corridor'}
              </span>
            </div>
          </div>
          <button className="btn ghost" onClick={onClose}>Close</button>
        </div>

        <div className="detail-scores">
          <div>
            <div className="score-big mono" style={{ color: riskColor(d.risk) }}>{riskLabel(d.risk)}</div>
            <div className="score-caption">Risk this window</div>
          </div>
          <div>
            <div style={{ fontSize: 22, fontWeight: 650 }} className="mono">#{d.rank}</div>
            <div className="score-caption">of 724</div>
          </div>
        </div>
      </div>

      <div className="section">
        <h2>Why this score</h2>
        {!d.reason_codes?.length && <div className="empty">No feature pushed this score up.</div>}
        {d.reason_codes?.map((r, i) => (
          <div className="reason" key={i}>
            <div className="txt">{r.reason}</div>
            <div className="meta mono">
              <span>{r.feature}</span>
              <span>+{r.contribution.toFixed(2)} log-odds</span>
            </div>
          </div>
        ))}
      </div>

      <div className="section">
        <h2>Recommended action</h2>
        <ol className="action-list">
          {d.recommended_action?.map((a, i) => <li key={i}>{a}</li>)}
        </ol>
      </div>

      <div className="section">
        <h2>30-day risk history</h2>
        <Sparkline history={d.risk_history} />
      </div>

      <div className="section">
        <h2>Money in flight now</h2>
        <div className="stat-row">
          <span className="k">Active mule chains</span>
          <span className="v mono">{chains.n_chains}</span>
        </div>
        <div className="stat-row">
          <span className="k">Accounts holding funds</span>
          <span className="v mono">{chains.n_accounts}</span>
        </div>
        <div className="stat-row">
          <span className="k">Total in flight</span>
          <span className="v mono" style={{ color: chains.money_in_flight > 0 ? 'var(--warn)' : 'inherit' }}>
            {chains.money_in_flight_display}
          </span>
        </div>
        {chains.chains?.length > 0 && (
          <table className="tbl" style={{ marginTop: 10 }}>
            <thead>
              <tr><th>Complaint</th><th>Type</th><th className="num">Held</th>
                  <th className="num">Age</th><th className="num">Hop</th></tr>
            </thead>
            <tbody>
              {chains.chains.slice(0, 8).map((c) => (
                <tr key={c.complaint_id}>
                  <td className="mono">#{c.complaint_id}</td>
                  <td>{c.fraud_category}</td>
                  <td className="num">{c.amount_held_display}</td>
                  <td className={`num ${c.age_hours >= 8 && c.age_hours <= 20 ? 'ripe' : ''}`}>
                    {c.age_hours.toFixed(0)}h
                  </td>
                  <td className="num">{c.hop}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {chains.chains?.length > 0 && (
          <div style={{ fontSize: 9.5, color: 'var(--ink-3)', marginTop: 6, lineHeight: 1.45 }}>
            Amber ages sit in the 8-20h band around the ~14h median from fraud to
            first ATM withdrawal.
          </div>
        )}
      </div>

      <div className="section">
        <h2>Recent cash-outs here &middot; 7 days</h2>
        {!d.recent_withdrawals?.length && <div className="empty">None recorded before this window.</div>}
        {d.recent_withdrawals?.length > 0 && (
          <table className="tbl">
            <thead><tr><th>When</th><th>ATM</th><th className="num">Amount</th></tr></thead>
            <tbody>
              {d.recent_withdrawals.slice(0, 6).map((w) => (
                <tr key={w.withdrawal_id}>
                  <td className="mono">{shortTime(w.timestamp)}</td>
                  <td className="mono">#{w.atm_id}</td>
                  <td className="num">{rupees(w.amount)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="section">
        <h2>Complaints filed here &middot; 7 days</h2>
        {!d.recent_complaints?.length && <div className="empty">None recorded before this window.</div>}
        {d.recent_complaints?.length > 0 && (
          <table className="tbl">
            <thead><tr><th>Reported</th><th>Type</th><th className="num">Loss</th></tr></thead>
            <tbody>
              {d.recent_complaints.slice(0, 6).map((c) => (
                <tr key={c.complaint_id}>
                  <td className="mono">{shortTime(c.reported_at)}</td>
                  <td>{c.fraud_category}</td>
                  <td className="num">{rupees(c.amount)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="section">
        <h2>ATM coverage</h2>
        <div className="stat-row">
          <span className="k">ATMs in district</span>
          <span className="v mono">{d.atms.count}</span>
        </div>
        {Object.entries(d.atms.banks || {}).slice(0, 5).map(([b, n]) => (
          <div className="stat-row" key={b}>
            <span className="k">{b}</span><span className="v mono">{n}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
