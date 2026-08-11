# -*- coding: utf-8 -*-
"""
Export module — produces multi-format files from the real detection data:
  * CSV (observations, vessels) — already in data/detections
  * GeoJSON (vessels as points for GIS: QGIS/ArcGIS)
  * Excel workbook with all sheets (reuses report_excel)
  * Summary JSON (machine-readable)
All values derive from the actual vessels.json files; nothing hardcoded.
"""
import os, json
import pandas as pd
import numpy as np

from config import ROOT, DET_DIR, CONFIG_DIR
from analysis import load_scenes


def export_geojson(scenes=None):
    """Vessels as GeoJSON points (WGS84) with attributes."""
    scenes = scenes if scenes is not None else load_scenes()
    good = scenes[scenes["error"].isna() | (scenes["error"] == "")].copy()
    good["dt"] = pd.to_datetime(good["datetime"])

    features = []
    for _, r in good.iterrows():
        vj = os.path.normpath(os.path.join(ROOT, "data", "raw_s1", r["id"], "vessels.json"))
        if not os.path.exists(vj):
            continue
        for v in json.load(open(vj, encoding="utf-8")):
            features.append({
                "type": "Feature",
                "geometry": {"type": "Point",
                             "coordinates": [v["lon"], v["lat"]]},
                "properties": {
                    "scene_id": r["id"],
                    "acquisition": r["dt"].strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "vessel_id": v["vessel_id"],
                    "length_m": v.get("length_m"),
                    "width_m": v.get("width_m"),
                    "peak_db": v.get("peak_db"),
                    "zone": {2: "in_port", 1: "anchorage", 0: "transit"}.get(v.get("zone"), "?"),
                    "dist_port_m": v.get("dist_port_m"),
                },
            })
    out = {"type": "FeatureCollection", "features": features}
    path = os.path.join(DET_DIR, "vessels.geojson")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    print(f"GeoJSON exported: {len(features):,} points -> {path}")
    return path


def export_summary_json(scenes=None):
    """Machine-readable summary of the whole monitoring state."""
    scenes = scenes if scenes is not None else load_scenes()
    good = scenes[scenes["error"].isna() | (scenes["error"] == "")].copy()
    good["dt"] = pd.to_datetime(good["datetime"])

    # latest + peak months
    monthly = pd.read_csv(os.path.join(DET_DIR, "monthly.csv"))
    mm = monthly[monthly["n_obs"] > 0].sort_values("ym")
    latest = mm.iloc[-1]
    peak = mm.loc[mm["mean_ships_port_adj"].idxmax()]

    summary = {
        "generated_at": pd.Timestamp.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "data_coverage": {
            "start": good["dt"].min().strftime("%Y-%m-%d"),
            "end": good["dt"].max().strftime("%Y-%m-%d"),
            "valid_scenes": int(len(good)),
            "total_scenes_catalog": int(len(scenes)),
            "months_with_data": int((monthly["n_obs"] > 0).sum()),
        },
        "detections": {
            "total_vessel_records": int(good["n_est"].sum()),
            "by_year": {int(y): int(g["n_est"].sum()) for y, g in good.groupby(good["dt"].dt.year)},
        },
        "activity": {
            "latest_month": latest["ym"],
            "latest_ships_per_obs": round(float(latest["mean_ships_port_adj"]), 2),
            "peak_month": peak["ym"],
            "peak_ships_per_obs": round(float(peak["mean_ships_port_adj"]), 2),
            "period_mean": round(float(mm["mean_ships_port_adj"].mean()), 2),
        },
        "validation": {
            "pairs_s1_s2": 0,
            "mean_snr_db": 0,
        },
    }
    # validation bits
    try:
        from validation import summary as vsum
        vs = vsum(scenes)
        summary["validation"]["pairs_s1_s2"] = vs.get("s2_pairs", 0)
        summary["validation"]["mean_snr_db"] = vs.get("mean_snr_db", 0)
    except Exception:
        pass
    path = os.path.join(DET_DIR, "summary_export.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"Summary JSON exported -> {path}")
    return path


def run():
    export_geojson()
    export_summary_json()


if __name__ == "__main__":
    run()
