"""
Real India district geography.

- Downloads a public districts GeoJSON (once) and cleans it: drops the
  state-outline features, de-duplicates, and stamps a district_id on every
  polygon so the dashboard can join risk scores to shapes later.
- Computes a centroid (lat, lon) per district and the K nearest neighbours.

Run alone to just prepare the GeoJSON:  python -m datagen.geo
"""
import json
import os
import urllib.request

import numpy as np
import pandas as pd

from datagen import config as C


def download_geojson():
    """Fetch the raw GeoJSON from the public URL if we don't have it yet."""
    if os.path.exists(C.GEOJSON_RAW_PATH):
        return
    os.makedirs(os.path.dirname(C.GEOJSON_RAW_PATH), exist_ok=True)
    print(f"downloading districts GeoJSON from {C.GEOJSON_URL} ...")
    urllib.request.urlretrieve(C.GEOJSON_URL, C.GEOJSON_RAW_PATH)


def polygon_centroid(geometry):
    """Approximate centroid = mean of the vertices of the largest ring.

    Good enough for placing ATMs and measuring district-to-district distance.
    """
    if geometry["type"] == "Polygon":
        rings = [geometry["coordinates"][0]]
    else:  # MultiPolygon: list of polygons, each a list of rings
        rings = [poly[0] for poly in geometry["coordinates"]]
    biggest = max(rings, key=len)
    pts = np.array(biggest)  # columns are (lon, lat)
    return float(pts[:, 1].mean()), float(pts[:, 0].mean())  # lat, lon


def clean_geojson():
    """Build data/india_districts.geojson with district_id, name, state.

    Returns a DataFrame: district_id, name, state, census_code, lat, lon.
    If the cleaned file already exists we just read it back (works offline).
    """
    if not os.path.exists(C.GEOJSON_PATH):
        download_geojson()
        with open(C.GEOJSON_RAW_PATH) as f:
            raw = json.load(f)

        # Keep only real district polygons (state outlines have no 'district').
        feats = [f for f in raw["features"] if f["properties"].get("district")]
        # Sort so ids are stable, and drop exact (state, district) duplicates.
        feats.sort(key=lambda f: (f["properties"]["st_nm"], f["properties"]["district"]))
        seen, unique = set(), []
        for f in feats:
            key = (f["properties"]["st_nm"], f["properties"]["district"])
            if key not in seen:
                seen.add(key)
                unique.append(f)

        for i, f in enumerate(unique):
            p = f["properties"]
            f["properties"] = {
                "district_id": i,  # 0-based: equals the row index in `districts`
                "name": p["district"],
                "state": p["st_nm"],
                "census_code": p.get("dt_code"),
            }
        with open(C.GEOJSON_PATH, "w") as f:
            json.dump({"type": "FeatureCollection", "features": unique}, f)
        print(f"cleaned GeoJSON: {len(unique)} districts -> {C.GEOJSON_PATH}")

    with open(C.GEOJSON_PATH) as f:
        gj = json.load(f)
    rows = []
    for feat in gj["features"]:
        lat, lon = polygon_centroid(feat["geometry"])
        rows.append({**feat["properties"], "lat": lat, "lon": lon})
    return pd.DataFrame(rows)


def haversine_km(lat1, lon1, lat2, lon2):
    """Great-circle distance in km. Inputs can be numpy arrays (broadcast)."""
    lat1, lon1, lat2, lon2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = (np.sin((lat2 - lat1) / 2) ** 2
         + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2)
    return 2 * 6371.0 * np.arcsin(np.sqrt(a))


def nearest_neighbors(districts, k=C.N_NEIGHBORS):
    """Return a DataFrame (district_id, neighbor_id, distance_km) with the k
    closest districts by centroid distance. Stand-in for shared borders."""
    lat = districts["lat"].to_numpy()
    lon = districts["lon"].to_numpy()
    dist = haversine_km(lat[:, None], lon[:, None], lat[None, :], lon[None, :])
    np.fill_diagonal(dist, np.inf)  # a district is not its own neighbour
    rows = []
    for d in range(len(districts)):
        for nb in np.argsort(dist[d])[:k]:
            rows.append((d, int(nb), round(float(dist[d, nb]), 1)))
    return pd.DataFrame(rows, columns=["district_id", "neighbor_id", "distance_km"])


if __name__ == "__main__":
    df = clean_geojson()
    print(df.head())
    print(f"{len(df)} districts, {df['state'].nunique()} states/UTs")
