import React, { useEffect, useState } from 'react'
import RoleSwitcher from './RoleSwitcher.jsx'
import { fmtWindow, pct } from '../risk.js'

// The demo centrepiece. Each advance grades the window that just closed
// against ground truth, and that result flashes when it updates.
export default function TopBar({ clock, grade, onAdvance, onReset, advancing, remaining,
                                 role, roles, setRole, segNote, unread, feedAvailable, onToggleFeed }) {
  const [flash, setFlash] = useState(false)
  useEffect(() => {
    if (!grade) return
    setFlash(true)
    const t = setTimeout(() => setFlash(false), 950)
    return () => clearTimeout(t)
  }, [grade])

  const w = fmtWindow(clock?.window_start)
  const p = grade?.precision
  const tone = p === null || p === undefined ? 'warn' : p >= 0.8 ? 'good' : p >= 0.5 ? 'warn' : 'crit'

  return (
    <div className="topbar">
      <div className="brand">
        <h1>FRAUD<span className="lens">LENS</span></h1>
        <div className="sub">Predictive cash withdrawal intelligence</div>
      </div>

      <div className="clock-block">
        <div>
          <div className="clock-label">Simulated clock</div>
          <div className="clock-value mono">{w.date || '--'}</div>
          <div className="clock-window mono">{w.slot || ''} IST &middot; 6h window</div>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <button className="btn" onClick={onAdvance} disabled={advancing || remaining === 0}>
            {advancing ? 'Scoring...' : 'Advance 6h >'}
          </button>
          <button className="btn ghost" onClick={onReset} disabled={advancing}>Reset</button>
        </div>
      </div>

      {roles?.length > 0 && (
        <RoleSwitcher roles={roles} role={role} setRole={setRole} note={segNote} />
      )}

      <div className={`grade ${flash ? 'flash' : ''}`}>
        {!grade ? (
          <div className="grade-empty">
            Advance the clock to score the next 6-hour window. Each step grades the
            window that just closed against what actually happened.
          </div>
        ) : (
          <>
            <div>
              <div className="clock-label">Window just closed &middot; {fmtWindow(grade.window_start).slot}</div>
              <div className="grade-headline">
                Flagged <strong className="mono">{grade.n_flagged}</strong> districts,{' '}
                <strong className="mono">{grade.n_flagged_correct}</strong> had real cash-outs
                <span style={{ color: 'var(--ink-3)' }}>
                  {' '}&middot; {grade.actual_withdrawal_districts} districts saw one nationwide
                </span>
              </div>
            </div>
            <div>
              <div className={`precision-chip mono ${tone}`}>
                {p === null || p === undefined ? 'n/a' : pct(p, 0)}
              </div>
              <div className="chip-caption">Precision</div>
            </div>
          </>
        )}
      </div>

      <button className="bell" onClick={onToggleFeed}
              title={feedAvailable ? 'Alert feed' : 'Alerts are not available to bank roles'}>
        <span className="bell-icon">&#9788;</span>
        <span className="bell-label">Alerts</span>
        {feedAvailable && unread > 0 && <span className="bell-badge mono">{unread}</span>}
        {!feedAvailable && <span className="bell-lock">restricted</span>}
      </button>
    </div>
  )
}
