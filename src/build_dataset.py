#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Build the final temporal datasets from the corrected detections.

  data/detections/port_activity_dataset.csv  — one row per satellite observation
  data/detections/vessel_locations.csv       — one row per detected vessel

Semantics (fixed after data audit):
  * activity_index = per-OBSERVATION normalized activity = vessels in port /
    port-basin coverage (not the monthly mean repeated on every row).
  * latitude/longitude = mean position of the vessels detected in that
    observation (real coordinates), or the port reference when none detected.
  * vessel_location = path to the per-scene vessel list (traceability).
"""
import os, json
import numpy as np
import pandas as pd

from analysis import load_scenes, build_monthly
from config import DET_DIR

def _port_ref():
    """Centroid of the OSM port boundary (computed, with a documented fallback)."""
    try:
        from shapely.geometry import shape
        from config import OSM_GEOJSON
        for ft in OSM_GEOJSON["features"]:
            if ft["properties"].get("role") == "port_boundary":
                c = shape(ft["geometry"]).centroid
                return dict(lat=c.y, lon=c.x)
    except Exception:
        pass
    return dict(lat=35.5235, lon=35.7709)  # OSM polygon centroid (fallback)


PORT_REF = _port_ref()
PORT_AREA_HA = 200.4                            # OSM polygon area (real)


def build():
    scenes = load_scenes()
    good = scenes[(scenes["error"].isna() | (scenes["error"] == ""))].copy()
    good["dt"] = pd.to_datetime(good["datetime"])

    rows = []
    for _, r in good.iterrows():
        vj = os.path.normpath(os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data", "raw_s1", r["id"], "vessels.json"))
        vs = []
        if os.path.exists(vj):
            vs = json.load(open(vj, encoding="utf-8"))
        if len(vs):
            mlat = float(np.mean([v["lat"] for v in vs]))
            mlon = float(np.mean([v["lon"] for v in vs]))
        else:
            mlat, mlon = PORT_REF["lat"], PORT_REF["lon"]
        cov = float(r.get("cov_port") or r.get("coverage") or 1.0)
        ai = round(float(r["n_est_in_port"]) / max(cov, 0.7), 3) if cov >= 0.7 else None
        rows.append(dict(
            acquisition_date=r["dt"].strftime("%Y-%m-%d"),
            acquisition_time=r["dt"].strftime("%H:%M:%S"),
            satellite="Sentinel-1",
            platform=r["platform"], orbit=r.get("orbit"),
            scene_id=r["id"],
            latitude=round(mlat, 5), longitude=round(mlon, 5),
            vessel_count=int(r["n_est"]),
            vessel_count_in_port=int(r["n_est_in_port"]),
            vessel_count_anchorage=int(r["n_anchorage"]),
            vessel_location=os.path.join("data", "raw_s1", r["id"], "vessels.json"),
            port_area_ha=PORT_AREA_HA,
            activity_index=ai,
            coverage=round(float(r["coverage"]), 3),
            cov_port=round(cov, 3),
            noise_floor_db=float(r["noise_floor_db"]),
            sea_roughness=float(r["sea_roughness"]),
        ))
    out = pd.DataFrame(rows)
    out.to_csv(os.path.join(DET_DIR, "port_activity_dataset.csv"), index=False)

    vrows = []
    for _, r in good.iterrows():
        vj = os.path.normpath(os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data", "raw_s1", r["id"], "vessels.json"))
        if not os.path.exists(vj):
            continue
        for v in json.load(open(vj, encoding="utf-8")):
            vrows.append(dict(
                acquisition_date=r["dt"].strftime("%Y-%m-%d"),
                acquisition_time=r["dt"].strftime("%H:%M:%S"),
                satellite="Sentinel-1", scene_id=r["id"],
                vessel_id=v["vessel_id"], latitude=v["lat"], longitude=v["lon"],
                length_m=v["length_m"], width_m=v["width_m"], peak_db=v["peak_db"],
                zone={0: "transit", 1: "anchorage", 2: "in_port"}[v["zone"]],
                dist_port_m=v["dist_port_m"], demerged=v.get("demerged", False),
                merged=v.get("merged", False), quay_edge=v.get("quay_edge", False),
                cluster_like=bool((v["width_m"] or 0) > 150),
            ))
    pd.DataFrame(vrows).to_csv(os.path.join(DET_DIR, "vessel_locations.csv"), index=False)
    print(f"port_activity_dataset.csv: {len(out)} rows")
    print(f"vessel_locations.csv: {len(vrows)} rows")


if __name__ == "__main__":
    build()
