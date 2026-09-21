import React, { useEffect, useMemo, useRef } from 'react'
import { MapContainer, GeoJSON, useMap, ZoomControl } from 'react-leaflet'
import { riskColor, riskLabel } from '../risk.js'

const INDIA_CENTER = [22.6, 82.0]

function FitIndia({ geo }) {
  const map = useMap()
  useEffect(() => {
    if (!geo) return
    // Fit the mainland once on load so the map fills its panel. The far-flung
    // island groups are excluded from the fit, else India shrinks to make room
    // for empty ocean; they are still on the map, just outside the initial view.
    map.fitBounds([[7.5, 68.0], [35.8, 97.5]], { padding: [12, 12] })
  }, [geo])       // eslint-disable-line react-hooks/exhaustive-deps
  return null
}

export default function MapView({ geo, riskById, visibleIds, selectedId, onSelect, scope }) {
  const layerRef = useRef(null)

  // The GeoJSON layer is created once (memoised on `geo`), so `onEachFeature`
  // runs once too and any prop it closes over is frozen at first render - when
  // the heatmap had not loaded and riskById was empty. That is why the tooltip
  // used to read "risk --" forever. Keep the latest lookup in a ref so the
  // tooltip callback reads current data instead of the mount-time snapshot.
  const riskRef = useRef(riskById)
  riskRef.current = riskById
  // Same reason for the role's scope: which districts are out of bounds.
  const scopeRef = useRef(scope)
  scopeRef.current = scope
  // ...and for the click handler. onSelect changes with the role (a State LEA
  // may open only its own state's districts), so a handler frozen at mount
  // would keep the first render's rules - from when the role was I4C.
  const selectRef = useRef(onSelect)
  selectRef.current = onSelect

  // Restyle in place when risk or filters change - far cheaper than remounting
  // the 724-polygon layer every window.
  useEffect(() => {
    const layer = layerRef.current
    if (!layer) return
    layer.eachLayer((l) => l.setStyle(styleFor(l.feature)))
  })   // no dep array: styles depend on props that change together

  // mouseout also restores a district's style, so it needs the CURRENT scores,
  // filters and selection, not the mount-time snapshot (see styleRef below).
  const styleFor = (feature) => {
    const id = feature.properties.district_id
    const dimmed = visibleIds && !visibleIds.has(id)
    const risk = riskById.get(id)
    const selected = id === selectedId
    return {
      fillColor: dimmed ? '#f0efea' : riskColor(risk),
      fillOpacity: dimmed ? 0.55 : 0.92,
      color: selected ? '#191917' : '#d9d6cc',
      weight: selected ? 2.4 : 0.6,
      opacity: dimmed ? 0.45 : 1,
    }
  }

  const styleRef = useRef(styleFor)
  styleRef.current = styleFor

  const onEachFeature = (feature, layer) => {
    const p = feature.properties
    layer.on({
      click: () => selectRef.current(p.district_id),
      mouseover: (e) => {
        e.target.setStyle({ weight: 2, color: '#191917' })
        e.target.bringToFront()
      },
      mouseout: (e) => e.target.setStyle(styleRef.current(feature)),
    })
    layer.bindTooltip(() => {
      // riskRef and scopeRef, not the props: see the note above.
      const sc = scopeRef.current
      const risk = riskRef.current.get(p.district_id)
      // Out of scope: say so with a label. Never show a number the role may not
      // have. In scope but genuinely unscored: "no score". Otherwise the score.
      const line = sc && sc.isOut(p) ? sc.label
        : risk === undefined ? 'no score'
        : `risk ${riskLabel(risk)}`
      return `<div class="tt-name">${p.name}</div>
              <div class="tt-state">${p.state}</div>
              <div class="tt-risk">${line}</div>`
    }, { className: 'district-tooltip', sticky: true })
  }

  const geoLayer = useMemo(() => {
    if (!geo) return null
    return (
      <GeoJSON
        data={geo}
        ref={layerRef}
        style={styleFor}
        onEachFeature={onEachFeature}
      />
    )
  }, [geo])       // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <MapContainer
      center={INDIA_CENTER}
      zoom={5}
      minZoom={4}
      maxZoom={9}
      zoomControl={false}
      attributionControl={true}
      preferCanvas={true}
    >
      {geoLayer}
      <ZoomControl position="bottomright" />
      <FitIndia geo={geo} />
    </MapContainer>
  )
}
