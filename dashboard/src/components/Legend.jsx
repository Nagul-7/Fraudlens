import React from 'react'
import { RISK_STOPS } from '../risk.js'

export default function Legend({ nVisible, nTotal, categoryActive }) {
  return (
    <div className="map-overlay legend">
      <h3>Predicted cash-out risk</h3>
      <div className="legend-scale">
        {RISK_STOPS.map((s) => <div key={s.at} style={{ background: s.color }} />)}
      </div>
      <div className="legend-ticks mono">
        <span>0%</span><span>20%</span><span>40%</span><span>60%</span><span>80%</span><span>100%</span>
      </div>
      <div className="legend-note">
        Calibrated probability that at least one fraud cash-out occurs in this
        district during the 6-hour window.
        {nVisible < nTotal && (
          <> <br />Dimmed districts are filtered out{categoryActive ? ' (no chains of the selected fraud type)' : ''}.</>
        )}
      </div>
    </div>
  )
}
