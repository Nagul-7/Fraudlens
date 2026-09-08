import React from 'react'
import { riskColor, riskLabel } from '../risk.js'

// What a bank is allowed to see. No reason codes, no complaint details, no
// district ranking - an operational instruction, not the intelligence behind it.
export default function BankPanel({ data, bank, note, stateFilter, onSelectDistrict }) {
  if (!data) return null
  const t = data.totals
  // A bank with nothing in the selected state must say so, never silently fall
  // back to national figures.
  const empty = stateFilter && !data.atm_exposure.length && !data.accounts_holding.length
  return (
    <div className="panel right">
      <div className="detail-head">
        <div className="dname">{bank}</div>
        <div className="dstate">
          Institutional exposure &middot; this window
          {stateFilter && <> &middot; <strong>{stateFilter} only</strong></>}
        </div>
        <div className="bank-totals">
          <div>
            <div className="score-big mono" style={{ fontSize: 27 }}>{t.our_atms_at_risk}</div>
            <div className="score-caption">our ATMs in risk districts</div>
          </div>
          <div>
            <div className="score-big mono" style={{ fontSize: 27, color: 'var(--warn)' }}>
              {t.amount_held_display}
            </div>
            <div className="score-caption">held in our accounts</div>
          </div>
        </div>
      </div>

      <div className="segregation-box compact" title={note}>
        <strong>Restricted view.</strong>
        <p>{note}</p>
      </div>

      {empty && (
        <div className="section">
          <div className="empty-state">
            <strong>No exposure in {stateFilter}</strong>
            <p>{bank} has no ATMs in high-risk districts and no accounts holding
               flagged funds in {stateFilter} this window.</p>
            <p className="empty-hint">Clear the state filter to see national exposure.</p>
          </div>
        </div>
      )}

      <div className="section">
        <h2>Our accounts holding funds &middot; freeze recommendations</h2>
        {!data.accounts_holding.length && (
          <div className="empty">
            No accounts currently holding flagged funds{stateFilter ? ` in ${stateFilter}` : ''}.
          </div>
        )}
        {data.accounts_holding.length > 0 && (
          <table className="tbl">
            <thead>
              <tr><th>Account</th><th>District</th><th className="num">Held</th><th className="num">Age</th></tr>
            </thead>
            <tbody>
              {data.accounts_holding.slice(0, 10).map((a) => (
                <tr key={a.account_id}>
                  <td className="mono">#{a.account_id}</td>
                  <td>{a.district}</td>
                  <td className="num">{a.amount_held_display}</td>
                  <td className={`num ${a.age_hours >= 6 && a.age_hours <= 30 ? 'ripe' : ''}`}>
                    {a.age_hours.toFixed(0)}h
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {data.accounts_holding[0] && (
          <div className="freeze-rec">
            <strong>CFCFRMS:</strong> {data.accounts_holding[0].recommendation}
          </div>
        )}
      </div>

      <div className="section">
        <h2>Our ATMs in high-risk districts</h2>
        {!data.atm_exposure.length && (
          <div className="empty">
            No ATMs in high-risk districts{stateFilter ? ` in ${stateFilter}` : ''} this window.
          </div>
        )}
        {data.atm_exposure.slice(0, 12).map((r) => (
          <div key={r.district_id} className="watch-item" onClick={() => onSelectDistrict(r.district_id)}>
            <span className="watch-swatch" style={{ background: riskColor(r.risk) }} />
            <span className="watch-name">
              <div className="n">{r.district}</div>
              <div className="s">{r.state} &middot; {r.our_atms} of our ATMs</div>
            </span>
            <span className="watch-risk mono">{riskLabel(r.risk)}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
