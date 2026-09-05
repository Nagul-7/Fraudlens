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

export default function MapView({ geo, riskById, visibleIds, selectedId, onSelect }) {
  const layerRef = useRef(null)

  // Restyle in place when risk or filters change - far cheaper than remounting
  // the 724-polygon layer every window.
  useEffect(() => {
    const layer = layerRef.current
    if (!layer) return
    layer.eachLayer((l) => l.setStyle(styleFor(l.feature)))
  })   // no dep array: styles depend on props that change together

  const styleFor = (feature) => {
    const id = feature.properties.district_id
    const dimmed = visibleIds && !visibleIds.has(id)
    const risk = riskById.get(id)
    const selected = id === selectedId
    return {
      fillColor: dimmed ? '#141b24' : riskColor(risk),
      fillOpacity: dimmed ? 0.30 : 0.87,
      color: selected ? '#ffffff' : '#2b3846',
      weight: selected ? 2.4 : 0.55,
      opacity: dimmed ? 0.35 : 1,
    }
  }

  const onEachFeature = (feature, layer) => {
    const p = feature.properties
    layer.on({
      click: () => onSelect(p.district_id),
      mouseover: (e) => {
        e.target.setStyle({ weight: 2, color: '#dbe6f2' })
        e.target.bringToFront()
      },
      mouseout: (e) => e.target.setStyle(styleFor(feature)),
    })
    layer.bindTooltip(() => {
      const risk = riskById.get(p.district_id)
      return `<div class="tt-name">${p.name}</div>
              <div class="tt-state">${p.state}</div>
              <div class="tt-risk">risk ${riskLabel(risk, 1)}</div>`
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
