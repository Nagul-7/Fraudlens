import React, { useState } from 'react'
import { riskColor, riskLabel } from '../risk.js'

const STATUSES = ['all', 'new', 'acknowledged', 'dismissed']

export default function AlertFeed({ feed, role, onOpenReport, onStatus, onDispatch, onClose }) {
  const [filter, setFilter] = useState('all')

  if (role.id === 'BANK') {
    return (
      <div className="feed-drawer">
        <div className="feed-head">
          <h2>Alert feed</h2>
          <button className="btn ghost" onClick={onClose}>Close</button>
        </div>
        <div className="segregation-box">
          <strong>Not available to bank roles.</strong>
          <p>{feed?.note || 'Alerts are crime intelligence and are not exposed to bank roles.'}</p>
          <p>Your institution's operational exposure is shown in the main panel instead.</p>
        </div>
      </div>
    )
  }

  const alerts = (feed?.alerts || []).filter((a) => filter === 'all' || a.status === filter)
  const c = feed?.counts || {}

  return (
    <div className="feed-drawer">
      <div className="feed-head">
        <h2>Alert feed {role.id === 'STATE' && <span className="scope-chip">{role.stateName} only</span>}</h2>
        <button className="btn ghost" onClick={onClose}>Close</button>
      </div>

      <div className="feed-filters">
        {STATUSES.map((s) => (
          <button key={s} className={`chip ${filter === s ? 'on' : ''}`} onClick={() => setFilter(s)}>
            {s} {s === 'all' ? (c.total ?? 0) : (c[s] ?? 0)}
          </button>
        ))}
      </div>

      <div className="feed-list">
        {!alerts.length && (
          <div className="empty" style={{ padding: '16px' }}>
            No {filter === 'all' ? '' : filter} alerts yet. Advance the clock to generate them.
          </div>
        )}
        {alerts.map((a) => (
          <div key={a.alert_id} className={`feed-item st-${a.status}`}>
            <div className="feed-item-top">
              <span className="feed-swatch" style={{ background: riskColor(a.risk) }} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div className="feed-title">
                  {a.district}, {a.state}
                  <span className={`status-pill ${a.status}`}>{a.status}</span>
                </div>
                <div className="feed-sub mono">
                  ALERT-{String(a.alert_id).padStart(5, '0')} &middot;{' '}
                  {new Date(a.window_start).toLocaleString('en-IN',
                    { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', hour12: false })}
                  {' '}&middot; risk {riskLabel(a.risk)}
                </div>
              </div>
            </div>
            <div className="feed-reason">{a.reason_codes?.[0]?.reason || 'Elevated predicted risk'}</div>
            <div className="feed-meta mono">
              {a.money_in_flight_display} in flight &middot; {a.active_chains} chains &middot; rank #{a.rank}
            </div>
            <div className="feed-actions">
              <button className="btn tiny" onClick={() => onOpenReport(a.alert_id)}>Report</button>
              <button className="btn tiny ghost" onClick={() => onDispatch(a.alert_id, 'sms')}>SMS</button>
              <button className="btn tiny ghost" onClick={() => onDispatch(a.alert_id, 'email')}>Email</button>
              {a.status !== 'acknowledged' && (
                <button className="btn tiny ghost" onClick={() => onStatus(a.alert_id, 'acknowledged')}>Ack</button>
              )}
              {a.status !== 'dismissed' && (
                <button className="btn tiny ghost" onClick={() => onStatus(a.alert_id, 'dismissed')}>Dismiss</button>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
