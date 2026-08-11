# -*- coding: utf-8 -*-
"""
Operational KPIs for the Latakia port monitoring system:
  1. Dwell time: match vessels across consecutive scenes (spatial nearest
     neighbour, 400 m) -> persistence distribution, median dwell days.
  2. Berth-line utilization: vessels hull length alongside the quay
     (water-facing edges of the real OSM port polygon) / quay length.
All values derive from the real detection dataset.
"""
import os, json
import numpy as np
import pandas as pd
import plotly.graph_objects as go

from config import S1_DIR, CONFIG_DIR, CHART_DIR
from analysis import load_scenes
from boundaries import build_masks, load_geoms
from charts import C, FONT, base_layout

MATCH_RADIUS_M = 400
MAX_GAP_DAYS = 10


def load_vessels(sid):
    vj = os.path.normpath(os.path.join(S1_DIR, sid, "vessels.json"))
    return json.load(open(vj, encoding="utf-8")) if os.path.exists(vj) else []


def quay_length_m():
    """Water-facing boundary length of the OSM port polygon (approx quay line)."""
    from shapely.geometry import Point
    from shapely.ops import transform as st
    import pyproj
    grid, land, _ = build_masks()
    t = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:32636", always_xy=True)
    port = st(t.transform, load_geoms()["port_boundary"])
    coords = list(port.exterior.coords)
    qlen = 0.0
    for i in range(len(coords) - 1):
        x1, y1 = coords[i]; x2, y2 = coords[i + 1]
        dx, dy = x2 - x1, y2 - y1
        L = np.hypot(dx, dy)
        if L < 1:
            continue
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        nx, ny = -dy / L, dx / L
        for sgn in (1, -1):
            px = int((mx + nx * sgn * 40 - grid["x0"]) // grid["pixel"])
            py = int((grid["y1"] - (my + ny * sgn * 40)) // grid["pixel"])
            if 0 <= px < grid["width"] and 0 <= py < grid["height"] and not land[py, px]:
                qlen += L
                break
    return qlen


def dwell_analysis(scenes=None):
    """Match vessels across consecutive scenes -> dwell stats."""
    scenes = scenes if scenes is not None else load_scenes()
    good = scenes[scenes["error"].isna() | (scenes["error"] == "")].copy()
    good["dt"] = pd.to_datetime(good["datetime"])
    g = good.sort_values("dt")
    gaps = []
    for i in range(len(g) - 1):
        a, b = g.iloc[i], g.iloc[i + 1]
        gap = (b["dt"] - a["dt"]).days
        if gap > MAX_GAP_DAYS:
            continue
        va, vb = load_vessels(a["id"]), load_vessels(b["id"])
        for v in vb:
            best, bd = None, MATCH_RADIUS_M
            for w in va:
                d = np.sqrt(((v["lon"] - w["lon"]) * 88000) ** 2 +
                            ((v["lat"] - w["lat"]) * 111000) ** 2)
                if d < bd:
                    bd, best = d, w
            if best is not None and best["zone"] in (1, 2) and v["zone"] in (1, 2):
                gaps.append(dict(gap_days=gap, zone=v["zone"]))
    df = pd.DataFrame(gaps)
    stats = dict(
        matched_pairs=int(len(df)),
        median_days=float(df["gap_days"].median()) if len(df) else None,
        mean_days=float(df["gap_days"].mean()) if len(df) else None,
        pct_persistent=float((df["gap_days"] >= 4).mean() * 100) if len(df) else None,
    )
    return df, stats


def operational_series(scenes=None, berth_dist=80):
    """Per-scene operational KPIs:
       - berthed: vessels alongside the quay (<= berth_dist m from port boundary)
       - capacity: in-port count vs historical p95 (2022-2024) threshold
    """
    scenes = scenes if scenes is not None else load_scenes()
    good = scenes[scenes["error"].isna() | (scenes["error"] == "")].copy()
    good["dt"] = pd.to_datetime(good["datetime"])
    rows = []
    for _, r in good.iterrows():
        berthed = 0
        for v in load_vessels(r["id"]):
            if v["dist_port_m"] is not None and v["dist_port_m"] <= berth_dist:
                berthed += 1
        rows.append(dict(dt=r["dt"], scene=r["id"], berthed=berthed,
                         in_port=int(r["n_est_in_port"])))
    df = pd.DataFrame(rows).sort_values("dt").reset_index(drop=True)
    df["year"] = df["dt"].dt.year
    df["ym"] = df["dt"].dt.strftime("%Y-%m")
    hist = df[df["year"] <= 2024]["in_port"]
    p95 = float(np.percentile(hist, 95))
    df["over_capacity"] = df["in_port"] > p95
    return df, p95


def chart_berthed(df):
    m = df.groupby("ym").agg(berthed=("berthed", "mean")).reset_index()
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=m["ym"], y=m["berthed"], mode="lines+markers",
                             name="سفن على الأرصفة",
                             line=dict(color=C["accent"], width=2.4),
                             marker=dict(size=5.5, color=C["accent"]),
                             fill="tozeroy", fillcolor="rgba(1,184,170,0.08)",
                             hovertemplate="%{x}<br>%{y:.1f} سفينة على الأرصفة<extra></extra>"))
    fig.update_xaxes(tickformat="%Y-%m")
    return base_layout(fig, "السفن الملاصقة للأرصفة (ضمن 80م من حد المرفأ) — شهريًا",
                       ylabel="سفن لكل مشهد")


# ------------------------------------------------------------------ charts
def chart_dwell(df):
    fig = go.Figure()
    if len(df):
        fig.add_trace(go.Histogram(x=df["gap_days"], nbinsx=10,
                                   marker_color=C["accent"], opacity=0.85,
                                   hovertemplate="%{x} أيام · %{y} زوجًا<extra></extra>"))
    fig.update_xaxes(dtick=1)
    return base_layout(fig, "توزيع مدة بقاء السفينة بين مشهدين متتاليين",
                       xlabel="الأيام بين المشهدين", ylabel="عدد التطابقات")


def run():
    scenes = load_scenes()
    dwell_df, stats = dwell_analysis(scenes)
    op, p95 = operational_series(scenes)
    print("dwell:", json.dumps(stats, ensure_ascii=False))
    print(f"capacity p95 (2022-2024 in-port): {p95}")
    print("by year:")
    agg = op.groupby("year").agg(scenes=("in_port", "count"),
                                 berthed_mean=("berthed", "mean"),
                                 inport_mean=("in_port", "mean"),
                                 over_pct=("over_capacity", "mean")).round(2)
    print(agg.to_string())
    chart_dwell(dwell_df).write_image(os.path.join(CHART_DIR, "dwell.png"),
                                      width=1280, height=560, scale=1.6)
    chart_berthed(op).write_image(os.path.join(CHART_DIR, "berthed.png"),
                                  width=1280, height=560, scale=1.6)
    # persist for report/dashboard
    import json as _j
    _j.dump({"dwell": stats, "capacity_p95": p95},
             open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                               "data", "detections", "insights.json"), "w"))
    print("charts + insights.json saved")


if __name__ == "__main__":
    run()
