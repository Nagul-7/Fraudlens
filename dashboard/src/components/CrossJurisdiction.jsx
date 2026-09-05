import React from 'react'
import { riskColor, riskLabel } from '../risk.js'

// The coordination story: a state sees money from ITS OWN complaints heading
// into another state's districts. The origin state cannot act there, and the
// destination state does not yet know the case exists. This panel is the
// referral that closes that gap.
export default function CrossJurisdiction({ data, stateName, onSelectDistrict }) {
  if (!data) return null
  return (
    <div className="section">
      <h2>Cross-jurisdiction referrals</h2>
      <div className="xj-summary">
        <div>
          <div className="xj-big mono">{data.n_referrals}</div>
          <div className="score-caption">chains leaving {stateName}</div>
        </div>
        <div>
          <div className="xj-big mono" style={{ color: 'var(--warn)' }}>{data.total_amount_display}</div>
          <div className="score-caption">in flight out of state</div>
        </div>
      </div>
      <p className="xj-note">
        Money from complaints filed in {stateName} is now sitting in accounts in
        other states. {stateName} cannot act there; the destination state does not
        yet know the case exists. Each row is a referral to send.
      </p>
      {!data.referrals.length && <div className="empty">No outbound chains in this window.</div>}
      {data.referrals.length > 0 && (
        <table className="tbl xj-table">
          <thead>
            <tr><th>Referral &middot; origin to destination</th>
                <th className="num">Held</th><th className="num">Age</th></tr>
          </thead>
          <tbody>
            {data.referrals.slice(0, 10).map((r, i) => (
              <tr key={`${r.complaint_id}-${i}`} className="xj-row"
                  onClick={() => onSelectDistrict(r.dest_district_id)}
                  title={`Complaint #${r.complaint_id} (${r.fraud_category}) filed in `
                         + `${r.origin_district}; money now in ${r.dest_district}, `
                         + `${r.dest_state} (risk ${riskLabel(r.dest_risk)})`}>
                <td>
                  <div className="xj-route">
                    <span>{r.origin_district}</span>
                    <span className="xj-arrow">&rarr;</span>
                    <span className="xj-dest">{r.dest_district}</span>
                    <span className="xj-dot" style={{ background: riskColor(r.dest_risk) }} />
                  </div>
                  <div className="xj-sub mono">
                    #{r.complaint_id} {r.fraud_category} &middot; into {r.dest_state}
                    {' '}&middot; dest risk {riskLabel(r.dest_risk)}
                  </div>
                </td>
                <td className="num">{r.amount_held_display}</td>
                <td className={`num ${r.age_hours >= 8 && r.age_hours <= 20 ? 'ripe' : ''}`}>
                  {r.age_hours.toFixed(0)}h
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
