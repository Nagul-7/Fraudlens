import React, { useCallback, useEffect, useMemo, useState } from 'react'
import * as api from './api.js'
import TopBar from './components/TopBar.jsx'
import MapView from './components/MapView.jsx'
import Legend from './components/Legend.jsx'
import FilterPanel from './components/FilterPanel.jsx'
import DistrictPanel from './components/DistrictPanel.jsx'
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
  const [selectedId, setSelectedId] = useState(null)
  const [detail, setDetail] = useState(null)
  const [detailState, setDetailState] = useState({ loading: false, error: null })

  // ---- startup: the heavy, once-only fetches -----------------------------
  useEffect(() => {
    (async () => {
      try {
        const [g, s, sim] = await Promise.all([api.getGeoJSON(), api.getStates(), api.getSimState()])
        setGeo(g)
        setStates(s.states)
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
      const h = await api.getHeatmap({
        window: clock.window_idx,
        state: filters.state,
        fraud_category: filters.category,
      })
      setHeatmap(h)
      setHeatmapError(null)
    } catch (e) {
      setHeatmapError(e.message)
    }
  }, [clock, filters.state, filters.category])

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

  const onAdvance = async () => {
    setAdvancing(true)
    try {
      const r = await api.advance({ threshold: filters.threshold })
      setClock(r.clock)
      setGrade(r.previous_window)
      setRemaining((n) => (n === null ? null : Math.max(n - r.advanced_by, 0)))
      setHeatmapError(null)
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
    if (!heatmap) return null
    if (!filters.state && !filters.category) return null      // nothing dimmed
    return new Set(heatmap.districts.map((d) => d.district_id))
  }, [heatmap, filters.state, filters.category])

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
              advancing={advancing} remaining={remaining} />
      {heatmapError && <div className="err-box">{heatmapError}</div>}

      <div className={`body-row ${selectedId === null ? 'no-detail' : ''}`}>
        <FilterPanel
          states={states} filters={filters} setFilters={setFilters}
          heatmap={heatmap} watchlist={watchlist}
          selectedId={selectedId} onSelect={setSelectedId}
        />

        <div className="map-wrap">
          <MapView geo={geo} riskById={riskById} visibleIds={visibleIds}
                   selectedId={selectedId} onSelect={setSelectedId} />
          <Legend nVisible={heatmap?.n_districts ?? 0} nTotal={724}
                  categoryActive={!!filters.category} />
          <div className="map-overlay map-hint">
            Click any district for the full intelligence panel
          </div>
          <div className="map-overlay map-stats">
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
          </div>
        </div>

        {selectedId !== null && (
          <DistrictPanel detail={detail} loading={detailState.loading}
                         error={detailState.error} onClose={() => setSelectedId(null)} />
        )}
      </div>

      <Footer clock={clock} />
    </div>
  )
}

const Banner = () => (
  <div className="synthetic-banner">
    SYNTHETIC DATA &middot; OUT-OF-SAMPLE PREDICTIONS ON HELD-OUT TEST MONTHS (NOV-DEC 2025)
    &middot; NOT REAL COMPLAINTS, ACCOUNTS OR TRANSACTIONS
  </div>
)

const Footer = ({ clock }) => (
  <div className="footer">
    <span>FraudLens v0.1 &middot; prototype for SIH26184 &middot; LightGBM, isotonic-calibrated</span>
    <span className="mono">
      {clock ? `window ${clock.window_idx} · ${clock.is_out_of_sample ? 'out-of-sample' : 'in-sample'}` : 'disconnected'}
    </span>
  </div>
)
