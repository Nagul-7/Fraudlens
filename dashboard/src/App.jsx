import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
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
  const [allScores, setAllScores] = useState(null)   // unfiltered, for map tooltips
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
  const heatmapSeq = useRef(0)     // newest heatmap request wins; see loadHeatmap
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

  // Who is asking. Sent with EVERY data request so the server scopes the
  // response itself: what a role may not see is never sent, rather than sent
  // and hidden here. (Empty values are dropped by the query-string builder.)
  const roleParams = useMemo(
    () => ({ role: role.id, state_name: role.stateName, bank: role.bank }),
    [role.id, role.stateName, role.bank])

  // ---- heatmap reloads whenever the window or the filters change ---------
  const loadHeatmap = useCallback(async () => {
    if (!clock) return
    // Requests can overlap (a role switch while one is in flight). Only the
    // newest may write state, or a slow response from the PREVIOUS role could
    // land after the switch and put out-of-scope scores back on screen.
    const mine = ++heatmapSeq.current
    try {
      const h = await api.getHeatmap({
        window: clock.window_idx,
        // A State LEA's state travels as the role's state_name. The filter
        // dropdown is locked to it, and a stale value left over from an earlier
        // role must never ride along - the server would (rightly) refuse it.
        state: role.id === 'STATE' ? '' : filters.state,
        fraud_category: filters.category,
        ...roleParams,
      })
      if (mine !== heatmapSeq.current) return
      setHeatmap(h)
      // Filters dim districts but do not un-score them, so for I4C the tooltip
      // is fed the full unfiltered set. That second, national request is made
      // ONLY for I4C: a State LEA or a bank builds its scores from the scoped
      // response alone, so nothing outside its scope is ever fetched.
      if (role.id === 'I4C' && (filters.state || filters.category)) {
        const all = await api.getHeatmap({ window: clock.window_idx, role: 'I4C' })
        if (mine !== heatmapSeq.current) return
        setAllScores(all)
      } else {
        setAllScores(h)
      }
      setHeatmapError(null)
    } catch (e) {
      if (mine === heatmapSeq.current) setHeatmapError(e.message)
    }
  }, [clock, filters.state, filters.category, role.id, roleParams])

  useEffect(() => { loadHeatmap() }, [loadHeatmap])

  // ---- district drill-down ----------------------------------------------
  useEffect(() => {
    // Banks have no district drill-down (it is crime intelligence), so none is requested.
    if (selectedId === null || !clock || role.id === 'BANK') { setDetail(null); return }
    let cancelled = false
    setDetailState({ loading: true, error: null })
    api.getDistrict(selectedId, { window: clock.window_idx, ...roleParams })
      .then((d) => { if (!cancelled) { setDetail(d); setDetailState({ loading: false, error: null }) } })
      .catch((e) => { if (!cancelled) { setDetail(null); setDetailState({ loading: false, error: e.message }) } })
    return () => { cancelled = true }
  }, [selectedId, clock, role.id, roleParams])

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
      // the category filter scopes the referral inbox too, not just the map
      api.getCrossJurisdiction({ state_name: role.stateName, window: clock.window_idx,
                                 fraud_category: filters.category })
        .then((d) => !cancelled && setXj(d)).catch(() => !cancelled && setXj(null))
    } else setXj(null)
    if (role.id === 'BANK' && role.bank) {
      // the state filter scopes ATMs, accounts and the district count together
      api.getBankExposure({ bank: role.bank, window: clock.window_idx,
                            state_name: filters.state })
        .then((d) => !cancelled && setBankData(d)).catch(() => !cancelled && setBankData(null))
    } else setBankData(null)
    return () => { cancelled = true }
  }, [role.id, role.stateName, role.bank, clock, filters.state, filters.category])

  // Never carry another role's view across a switch.
  //
  // This used to clear the open district only for the Bank role, which left a
  // real hole: sign in as I4C, open a district anywhere in the country, switch
  // to a State LEA, and that district's full intelligence panel stayed on
  // screen even when it sat outside the state's jurisdiction. The panel had been
  // fetched under the earlier role, and a stale panel that a user cannot
  // distinguish from a live one is exactly the thing role segregation is
  // supposed to prevent. The selection is now dropped on any change of role or
  // jurisdiction. (/districts/{id} is now role-scoped on the server as well, so
  // a re-fetch under the new role would be refused, not merely hidden.)
  useEffect(() => {
    setFeedOpen(false)
    setReport(null)
    setToasts([])
    setSelectedId(null)
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
      const r = await api.advance({ threshold: filters.threshold, ...roleParams })
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
  // Scores for the map: keyed by the same district_id the GeoJSON features
  // carry, and built from the UNFILTERED set so every district resolves.
  const riskById = useMemo(() => {
    const m = new Map()
    ;(allScores ?? heatmap)?.districts.forEach((d) => m.set(d.district_id, d.risk))
    return m
  }, [allScores, heatmap])

  const visibleIds = useMemo(() => {
    // A bank may only see risk for districts where it actually has ATMs;
    // everything else is dimmed, so the national picture is never on screen.
    if (role.id === 'BANK') {
      return bankData ? new Set(bankData.own_district_ids) : new Set()
    }
    if (!heatmap) return null
    // A State LEA's jurisdiction comes from the ROLE, not from the filter
    // dropdown - the dropdown only displays it, locked. Testing filters.state
    // alone meant a state officer's map fell through to "nothing dimmed" and
    // painted every district in the country, while the panels beside it were
    // correctly scoped to their state. The server was right and the map was
    // not, which is the worst version of this bug: it looks authoritative.
    // `heatmap` is already server-scoped for this role, so its districts are
    // exactly what this user is entitled to see.
    const roleScoped = role.id === 'STATE' && !!role.stateName
    if (!roleScoped && !filters.state && !filters.category) return null
    return new Set(heatmap.districts.map((d) => d.district_id))
  }, [heatmap, filters.state, filters.category, role.id, role.stateName, bankData])

  // district_id -> state, from the GeoJSON the map already holds
  const stateOfDistrict = useMemo(
    () => new Map((geo?.features ?? []).map((f) => [f.properties.district_id, f.properties.state])),
    [geo])

  // Only open a district this role may see. Banks have no drill-down at all;
  // a State LEA may open only its own state's districts.
  const selectDistrict = useCallback((id) => {
    if (role.id === 'BANK') return
    if (role.id === 'STATE' && stateOfDistrict.get(id) !== role.stateName) return
    setSelectedId(id)
  }, [role.id, role.stateName, stateOfDistrict])

  // What the map tooltip says about a district the role may not see: a LABEL,
  // never a number.
  const scope = useMemo(() => {
    if (role.id === 'STATE') {
      return { label: 'Outside your jurisdiction', isOut: (p) => p.state !== role.stateName }
    }
    if (role.id === 'BANK') {
      const own = new Set(bankData?.own_district_ids ?? [])
      return { label: 'Outside your footprint', isOut: (p) => !own.has(p.district_id) }
    }
    return null
  }, [role.id, role.stateName, bankData])

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
            selectedId={selectedId} onSelect={selectDistrict}
            lockedState={role.id === 'STATE' ? role.stateName : null}
            bankMode={role.id === 'BANK'}
            inbox={role.id === 'STATE' ? (
              <CrossJurisdiction data={xj} stateName={role.stateName}
                                 category={filters.category}
                                 onSelectDistrict={null} />
            ) : null}
          />
        </div>

        <div className="map-wrap">
          <MapView geo={geo} riskById={riskById} visibleIds={visibleIds}
                   selectedId={selectedId} onSelect={selectDistrict} scope={scope} />
          <Legend nVisible={heatmap?.n_districts ?? 0} nTotal={724}
                  categoryActive={!!filters.category} />
          <div className="map-overlay map-hint">
            {role.id === 'BANK'
              ? `Showing only districts where ${role.bank} has ATMs or exposed accounts`
                + (filters.state ? ` in ${filters.state}` : '')
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
                  <span className="v mono">{heatmap ? riskLabel(heatmap.risk_max) : '--'}</span>
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
                       stateFilter={filters.state} onSelectDistrict={null} />
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
