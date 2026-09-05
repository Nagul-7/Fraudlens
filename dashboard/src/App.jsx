import React, { useCallback, useEffect, useMemo, useState } from 'react'
import * as api from './api.js'
import TopBar from './components/TopBar.jsx'
import MapView from './components/MapView.jsx'
import Legend from './components/Legend.jsx'
import FilterPanel from './components/FilterPanel.jsx'
import DistrictPanel from './components/DistrictPanel.jsx'
import RoleSwitcher from './components/RoleSwitcher.jsx'
import AlertFeed from './components/AlertFeed.jsx'
import IntelligenceReport from './components/IntelligenceReport.jsx'
import CrossJurisdiction from './components/CrossJurisdiction.jsx'
import BankPanel from './components/BankPanel.jsx'
import Toast from './components/Toast.jsx'
import { pct, riskLabel } from './risk.js'

export default function App() {
  const [boot, setBoot] = useState({ loading: true, error: null })
  const [geo, setGeo] = useState(null)
  const [states, setStates] = useState([])
  const [clock, setClock] = useState(null)
  const [remaining, setRemaining] = useState(null)

  const [heatmap, setHeatmap] = useState(null)
  const [heatmapError, setHeatmapError] = useState(null)
  const [grade, setGrade] = useState(null)
  const [advancing, setAdvancing] = useState(false)

  const [filters, setFilters] = useState({ state: '', category: '', threshold: 0.8, topK: 25 })
  const [roles, setRoles] = useState([])
  const [segNote, setSegNote] = useState('')
  const [role, setRole] = useState({ id: 'I4C', stateName: '', bank: '' })
  const [feed, setFeed] = useState(null)
  const [feedOpen, setFeedOpen] = useState(false)
  const [report, setReport] = useState(null)
  const [xj, setXj] = useState(null)
  const [bankData, setBankData] = useState(null)
  const [toasts, setToasts] = useState([])
  const [selectedId, setSelectedId] = useState(null)
  const [detail, setDetail] = useState(null)
  const [detailState, setDetailState] = useState({ loading: false, error: null })

  // ---- startup: the heavy, once-only fetches -----------------------------
  useEffect(() => {
    (async () => {
      try {
        const [g, s, sim, r] = await Promise.all([
          api.getGeoJSON(), api.getStates(), api.getSimState(), api.getRoles()])
        setGeo(g)
        setStates(s.states)
        setRoles(r.roles)
        setSegNote(r.segregation_note)
        setClock(sim.clock)
        setRemaining(sim.windows_remaining)
        setBoot({ loading: false, error: null })
      } catch (e) {
        setBoot({ loading: false, error: e.message })
      }
    })()
  }, [])

  // ---- heatmap reloads whenever the window or the filters change ---------
  const loadHeatmap = useCallback(async () => {
    if (!clock) return
    try {
      // A State LEA's map is scoped server-side to its own jurisdiction; the
      // state filter is then locked to that value in the UI.
      const scopedState = role.id === 'STATE' ? role.stateName : filters.state
      const h = await api.getHeatmap({
        window: clock.window_idx,
        state: scopedState,
        fraud_category: filters.category,
      })
      setHeatmap(h)
      setHeatmapError(null)
    } catch (e) {
      setHeatmapError(e.message)
    }
  }, [clock, filters.state, filters.category, role.id, role.stateName])

  useEffect(() => { loadHeatmap() }, [loadHeatmap])

  // ---- district drill-down ----------------------------------------------
  useEffect(() => {
    if (selectedId === null || !clock) { setDetail(null); return }
    let cancelled = false
    setDetailState({ loading: true, error: null })
    api.getDistrict(selectedId, { window: clock.window_idx })
      .then((d) => { if (!cancelled) { setDetail(d); setDetailState({ loading: false, error: null }) } })
      .catch((e) => { if (!cancelled) { setDetail(null); setDetailState({ loading: false, error: e.message }) } })
    return () => { cancelled = true }
  }, [selectedId, clock])

  const loadFeed = useCallback(async () => {
    try {
      setFeed(await api.getFeed({ role: role.id, state_name: role.stateName, bank: role.bank }))
    } catch (e) { setHeatmapError(e.message) }
  }, [role.id, role.stateName, role.bank])

  useEffect(() => { loadFeed() }, [loadFeed])

  // role-specific side panels
  useEffect(() => {
    if (!clock) return
    let cancelled = false
    if (role.id === 'STATE' && role.stateName) {
      api.getCrossJurisdiction({ state_name: role.stateName, window: clock.window_idx })
        .then((d) => !cancelled && setXj(d)).catch(() => !cancelled && setXj(null))
    } else setXj(null)
    if (role.id === 'BANK' && role.bank) {
      api.getBankExposure({ bank: role.bank, window: clock.window_idx })
        .then((d) => !cancelled && setBankData(d)).catch(() => !cancelled && setBankData(null))
    } else setBankData(null)
    return () => { cancelled = true }
  }, [role.id, role.stateName, role.bank, clock])

  // Never carry another role's view across a switch.
  useEffect(() => {
    setFeedOpen(false)
    setReport(null)
    setToasts([])
    if (role.id === 'BANK') setSelectedId(null)
  }, [role.id, role.stateName, role.bank])

  const pushToast = (t) => {
    const id = Date.now() + Math.random()
    setToasts((xs) => [...xs, { ...t, id }])
    setTimeout(() => setToasts((xs) => xs.filter((x) => x.id !== id)), 14000)
  }

  const onStatus = async (id, status) => {
    try { await api.setAlertStatus(id, status); loadFeed() }
    catch (e) { setHeatmapError(e.message) }
  }

  const onDispatch = async (id, channel) => {
    try {
      const r = await api.dispatchAlert(id, channel)
      pushToast({ channel, to: r.to, body: r.body, note: r.note, kind: 'ok' })
      loadFeed()
    } catch (e) { setHeatmapError(e.message) }
  }

  const onOpenReport = async (id) => {
    try { setReport(await api.getReport(id)) }
    catch (e) { setHeatmapError(e.message) }
  }

  const onAdvance = async () => {
    setAdvancing(true)
    try {
      const r = await api.advance({ threshold: filters.threshold })
      setClock(r.clock)
      setGrade(r.previous_window)
      setRemaining((n) => (n === null ? null : Math.max(n - r.advanced_by, 0)))
      setHeatmapError(null)
      loadFeed()
    } catch (e) {
      setHeatmapError(e.message)
    } finally {
      setAdvancing(false)
    }
  }

  const onReset = async () => {
    setAdvancing(true)
    try {
      const r = await api.resetClock()
      setClock(r.clock)
      setGrade(null)
      setFeed(null)
      loadFeed()
      const sim = await api.getSimState()
      setRemaining(sim.windows_remaining)
    } catch (e) {
      setHeatmapError(e.message)
    } finally {
      setAdvancing(false)
    }
  }

  // ---- derived views -----------------------------------------------------
  const riskById = useMemo(() => {
    const m = new Map()
    heatmap?.districts.forEach((d) => m.set(d.district_id, d.risk))
    return m
  }, [heatmap])

  const visibleIds = useMemo(() => {
    // A bank may only see risk for districts where it actually has ATMs;
    // everything else is dimmed, so the national picture is never on screen.
    if (role.id === 'BANK') {
      return bankData ? new Set(bankData.own_district_ids) : new Set()
    }
    if (!heatmap) return null
    if (!filters.state && !filters.category) return null      // nothing dimmed
    return new Set(heatmap.districts.map((d) => d.district_id))
  }, [heatmap, filters.state, filters.category, role.id, bankData])

  const watchlist = useMemo(
    () => (heatmap ? heatmap.districts.slice(0, filters.topK) : []),
    [heatmap, filters.topK],
  )

  // ---- render ------------------------------------------------------------
  if (boot.loading) {
    return (
      <div className="app">
        <div className="center-msg"><div className="spinner" /><p>Loading FraudLens...</p></div>
      </div>
    )
  }
  if (boot.error) {
    return (
      <div className="app">
        <Banner />
        <div className="center-msg">
          <h2>Cannot reach the FraudLens API</h2>
          <p>The dashboard is running, but the backend did not respond. Start it with:</p>
          <p><code>uvicorn api.main:app --port 8000</code></p>
          <div className="err-box mono" style={{ maxWidth: 620 }}>{boot.error}</div>
          <button className="btn" onClick={() => window.location.reload()}>Retry</button>
        </div>
        <Footer clock={null} />
      </div>
    )
  }

  return (
    <div className="app">
      <Banner />
      <TopBar clock={clock} grade={grade} onAdvance={onAdvance} onReset={onReset}
              advancing={advancing} remaining={remaining}
              role={role} roles={roles} setRole={setRole} segNote={segNote}
              unread={feed?.counts?.new ?? 0}
              feedAvailable={role.id !== 'BANK'}
              onToggleFeed={() => setFeedOpen((v) => !v)} />
      {heatmapError && <div className="err-box">{heatmapError}</div>}

      <div className={`body-row ${(selectedId === null && role.id !== 'BANK') ? 'no-detail' : ''}`
                       + (role.id === 'STATE' ? ' wide-left' : '')}>
        <div className="panel left">
          <FilterPanel
            states={states} filters={filters} setFilters={setFilters}
            heatmap={heatmap} watchlist={watchlist}
            selectedId={selectedId} onSelect={setSelectedId}
            lockedState={role.id === 'STATE' ? role.stateName : null}
            bankMode={role.id === 'BANK'}
          />
          {role.id === 'STATE' && (
            <CrossJurisdiction data={xj} stateName={role.stateName}
                               onSelectDistrict={setSelectedId} />
          )}
        </div>

        <div className="map-wrap">
          <MapView geo={geo} riskById={riskById} visibleIds={visibleIds}
                   selectedId={selectedId} onSelect={setSelectedId} />
          <Legend nVisible={heatmap?.n_districts ?? 0} nTotal={724}
                  categoryActive={!!filters.category} />
          <div className="map-overlay map-hint">
            {role.id === 'BANK'
              ? `Showing only districts where ${role.bank} operates ATMs`
              : 'Click any district for the full intelligence panel'}
          </div>
          <div className="map-overlay map-stats">
            {role.id === 'BANK' ? (
              <>
                <div className="stat-row">
                  <span className="k">Our ATMs at risk</span>
                  <span className="v mono">{bankData?.totals.our_atms_at_risk ?? '--'}</span>
                </div>
                <div className="stat-row">
                  <span className="k">Districts shown</span>
                  <span className="v mono">{bankData?.own_district_ids?.length ?? '--'}</span>
                </div>
                <div className="stat-row">
                  <span className="k">In our accounts</span>
                  <span className="v mono">{bankData?.totals.amount_held_display ?? '--'}</span>
                </div>
              </>
            ) : (
              <>
                <div className="stat-row">
                  <span className="k">Districts</span>
                  <span className="v mono">{heatmap?.n_districts ?? '--'}</span>
                </div>
                <div className="stat-row">
                  <span className="k">Peak risk</span>
                  <span className="v mono">{heatmap ? riskLabel(heatmap.risk_max, 1) : '--'}</span>
                </div>
                <div className="stat-row">
                  <span className="k">Windows left</span>
                  <span className="v mono">{remaining ?? '--'}</span>
                </div>
              </>
            )}
          </div>
        </div>

        {role.id === 'BANK'
          ? <BankPanel data={bankData} bank={role.bank} note={segNote}
                       onSelectDistrict={setSelectedId} />
          : selectedId !== null && (
              <DistrictPanel detail={detail} loading={detailState.loading}
                             error={detailState.error} onClose={() => setSelectedId(null)} />
            )}
      </div>

      {feedOpen && (
        <AlertFeed feed={feed} role={role} onClose={() => setFeedOpen(false)}
                   onOpenReport={onOpenReport} onStatus={onStatus} onDispatch={onDispatch} />
      )}
      {report && <IntelligenceReport report={report} onClose={() => setReport(null)} />}
      <Toast toasts={toasts} onDismiss={(id) => setToasts((xs) => xs.filter((x) => x.id !== id))} />

      <Footer clock={clock} role={role} />
    </div>
  )
}

const Banner = () => (
  <div className="synthetic-banner">
    SYNTHETIC DATA &middot; OUT-OF-SAMPLE PREDICTIONS ON HELD-OUT TEST MONTHS (NOV-DEC 2025)
    &middot; NOT REAL COMPLAINTS, ACCOUNTS OR TRANSACTIONS
  </div>
)

const Footer = ({ clock, role }) => (
  <div className="footer">
    <span>
      FraudLens v0.1 &middot; prototype for SIH26184 &middot; LightGBM, isotonic-calibrated
      {role && <> &middot; role {role.id}{role.stateName ? ` (${role.stateName})` : ''}{role.bank ? ` (${role.bank})` : ''}</>}
    </span>
    <span className="mono">
      {clock ? `window ${clock.window_idx} · ${clock.is_out_of_sample ? 'out-of-sample' : 'in-sample'}` : 'disconnected'}
    </span>
  </div>
)
