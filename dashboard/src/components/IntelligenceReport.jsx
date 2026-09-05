import React from 'react'
import { rupees } from '../risk.js'

// Deliverable (c): a printable intelligence report. Deliberately laid out like
// a filed document rather than a dashboard panel - reference number, evidence
// as numbered findings, tables, and a footer that states the data is synthetic,
// which model produced it and when.
export default function IntelligenceReport({ report, onClose }) {
  if (!report) return null
  const a = report.alert
  const win = new Date(a.window_start)
  const winEnd = new Date(win.getTime() + 6 * 3600 * 1000)
  const fmt = (d) => d.toLocaleString('en-IN',
    { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false })

  return (
    <div className="report-overlay" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="report-scroll">
        <div className="report-toolbar no-print">
          <button className="btn" onClick={() => window.print()}>Print / Save as PDF</button>
          <button className="btn ghost" onClick={onClose}>Close</button>
        </div>

        <article className="report">
          <header className="report-head">
            <div className="report-crest">
              <div className="crest-mark">FL</div>
              <div>
                <div className="crest-org">Indian Cyber Crime Coordination Centre &middot; FraudLens</div>
                <div className="crest-title">Predictive Cash-Out Intelligence Report</div>
              </div>
            </div>
            <div className="report-ref">
              <div className="ref-num mono">{report.reference}</div>
              <div className="ref-class">FOR OFFICIAL USE &middot; DEMONSTRATION</div>
            </div>
          </header>

          <table className="report-facts">
            <tbody>
              <tr>
                <th>District</th><td>{a.district}</td>
                <th>State</th><td>{a.state}</td>
              </tr>
              <tr>
                <th>Prediction window</th><td colSpan={3} className="mono">{fmt(win)} to {fmt(winEnd)} IST (6 hours)</td>
              </tr>
              <tr>
                <th>Risk score</th><td className="mono">{(a.risk * 100).toFixed(1)}% (calibrated)</td>
                <th>National rank</th><td className="mono">{a.rank} of 724 districts</td>
              </tr>
              <tr>
                <th>Money in flight</th>
                <td className={a.active_chains ? 'mono' : undefined}>
                  {a.active_chains
                    ? a.money_in_flight_display
                    : 'None currently parked here'}
                </td>
                <th>Active mule chains</th>
                <td className={a.active_chains ? 'mono' : undefined}>
                  {a.active_chains
                    ? `${a.active_chains} chains / ${a.active_accounts} accounts`
                    : 'Alert driven by recent cash-out activity'}
                </td>
              </tr>
              <tr>
                <th>Alert status</th><td>{a.status}</td>
                <th>ATMs in district</th><td className="mono">{report.atm_count}</td>
              </tr>
            </tbody>
          </table>

          <section>
            <h3>1. Basis for this assessment</h3>
            <p className="report-lead">
              The following factors contributed most to the risk score for this
              district and window. Each is measured from events visible strictly
              before the window opened.
            </p>
            <ol className="findings">
              {a.reason_codes?.map((c, i) => (
                <li key={i}>
                  {c.reason}
                  <span className="finding-meta mono"> [{c.feature}, weight +{c.contribution.toFixed(2)}]</span>
                </li>
              ))}
            </ol>
          </section>

          <section>
            <h3>2. Funds currently held in this district</h3>
            {!report.active_chains?.length && <p className="report-lead">No active chains recorded for this window.</p>}
            {report.active_chains?.length > 0 && (
              <table className="report-table">
                <thead>
                  <tr>
                    <th>Complaint</th><th>Fraud type</th><th>Origin district</th>
                    <th className="num">Amount held</th><th className="num">Chain age</th>
                    <th className="num">Hop</th><th className="num">Accounts</th>
                  </tr>
                </thead>
                <tbody>
                  {report.active_chains.slice(0, 15).map((c) => (
                    <tr key={c.complaint_id}>
                      <td className="mono">#{c.complaint_id}</td>
                      <td>{c.fraud_category}</td>
                      <td>{c.victim_district}, {c.victim_state}</td>
                      <td className="num">{c.amount_held_display}</td>
                      <td className="num">{c.age_hours.toFixed(0)}h</td>
                      <td className="num">{c.hop}</td>
                      <td className="num">{c.n_accounts}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>

          <section>
            <h3>3. ATMs to be covered</h3>
            <table className="report-table">
              <thead><tr><th>ATM ID</th><th>Bank</th><th className="num">Latitude</th><th className="num">Longitude</th></tr></thead>
              <tbody>
                {report.atms.slice(0, 12).map((m) => (
                  <tr key={m.atm_id}>
                    <td className="mono">#{m.atm_id}</td><td>{m.bank}</td>
                    <td className="num">{m.lat}</td><td className="num">{m.lon}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {report.atm_count > report.atms.length && (
              <p className="report-lead">
                Showing {report.atms.length} of {report.atm_count} ATMs in this district.
              </p>
            )}
          </section>

          <section>
            <h3>4. Recommended action</h3>
            <ol className="findings">
              {a.recommended_action?.map((r, i) => <li key={i}>{r}</li>)}
            </ol>
          </section>

          {a.dispatched?.length > 0 && (
            <section>
              <h3>5. Dispatch log</h3>
              <table className="report-table">
                <thead><tr><th>Channel</th><th>Recipient</th><th>Time</th><th>Status</th></tr></thead>
                <tbody>
                  {a.dispatched.map((d, i) => (
                    <tr key={i}>
                      <td>{d.channel.toUpperCase()}</td><td>{d.to}</td>
                      <td className="mono">{d.sent_at}</td><td>{d.note}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          )}

          <footer className="report-foot">
            <div className="synthetic-stamp">{report.data_notice}</div>
            <div className="foot-grid mono">
              <span>Model: {report.model_version}</span>
              <span>Generated: {report.generated_at}</span>
              <span>Reference: {report.reference}</span>
              <span>Alert raised: {a.created_at}</span>
            </div>
          </footer>
        </article>
      </div>
    </div>
  )
}
