# -*- coding: utf-8 -*-
"""
Anomaly detection module for the Latakia port monitoring system.

Methods:
  1. EWMA control chart — detects level shifts in the monthly activity series.
  2. CUSUM — detects sustained small shifts.
  3. Z-score on the latest observation vs the historical baseline.
All outputs are derived from the real detection dataset; nothing hardcoded.
"""
import json, os
import numpy as np
import pandas as pd

from config import DET_DIR, CHART_DIR
from analysis import load_scenes, build_monthly


def ewma_series(values, lam=0.25):
    """Exponentially weighted moving average of a series."""
    out = np.empty(len(values))
    out[0] = values[0]
    for i in range(1, len(values)):
        out[i] = lam * values[i] + (1 - lam) * out[i - 1]
    return out


def detect_anomalies(scenes=None):
    """Run EWMA + CUSUM on the monthly adjusted series. Returns events list."""
    scenes = scenes if scenes is not None else load_scenes()
    monthly = build_monthly(scenes)
    m = monthly[monthly["n_obs"] > 0].sort_values("ym").reset_index(drop=True)
    vals = m["mean_ships_port_adj"].values
    if len(vals) < 6:
        return [], m

    # baseline = first 24 months (2022-2023) as the stable reference
    n_base = min(24, len(vals) - 1)
    base = vals[:n_base]
    mu, sd = float(np.mean(base)), float(np.std(base))
    if sd < 1e-9:
        sd = 1.0

    # ---- EWMA ----
    ew = ewma_series(vals, lam=0.25)
    ew_sd = sd * np.sqrt(0.25 / (2 - 0.25))
    ew_events = []
    for i in range(n_base, len(vals)):
        z = (ew[i] - mu) / ew_sd
        if abs(z) > 3:
            ew_events.append(dict(
                ym=m.loc[i, "ym"], method="EWMA", z_score=round(float(z), 2),
                value=round(float(vals[i]), 2),
                type="ارتفاع" if vals[i] > mu else "انخفاض"))

    # ---- CUSUM (two-sided) ----
    k = 0.5 * sd
    h = 5 * sd
    c_plus = c_minus = 0.0
    cusum_events = []
    for i in range(n_base, len(vals)):
        c_plus = max(0, c_plus + (vals[i] - mu) / sd - k)
        c_minus = max(0, c_minus - (vals[i] - mu) / sd - k)
        if c_plus > h:
            cusum_events.append(dict(ym=m.loc[i, "ym"], method="CUSUM",
                                     type="ارتفاع مستمر", value=round(float(vals[i]), 2)))
            c_plus = 0
        if c_minus > h:
            cusum_events.append(dict(ym=m.loc[i, "ym"], method="CUSUM",
                                     type="انخفاض مستمر", value=round(float(vals[i]), 2)))
            c_minus = 0

    # ---- latest z-score ----
    latest = vals[-1]
    latest_z = (latest - mu) / sd

    result = dict(
        baseline_mu=round(mu, 2), baseline_sd=round(sd, 2),
        latest=round(float(latest), 2), latest_ym=m.loc[len(vals) - 1, "ym"],
        latest_z=round(float(latest_z), 2),
        events=ew_events + cusum_events,
    )
    return result, m


def chart_ewma(scenes=None):
    """EWMA control chart: raw monthly + EWMA line + control limits."""
    import plotly.graph_objects as go
    from charts import C, FONT, base_layout

    scenes = scenes if scenes is not None else load_scenes()
    monthly = build_monthly(scenes)
    m = monthly[monthly["n_obs"] > 0].sort_values("ym").reset_index(drop=True)
    vals = m["mean_ships_port_adj"].values
    n_base = min(24, len(vals) - 1)
    mu = float(np.mean(vals[:n_base]))
    sd = float(np.std(vals[:n_base])) or 1.0
    ew = ewma_series(vals, 0.25)
    ew_sd = sd * np.sqrt(0.25 / (2 - 0.25))

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=m["ym"], y=vals, mode="markers", name="قيمة شهرية",
                             marker=dict(size=6, color=C["slate"], opacity=0.7),
                             hovertemplate="%{x}<br>%{y:.1f}<extra></extra>"))
    fig.add_trace(go.Scatter(x=m["ym"], y=ew, mode="lines", name="المتوسط المتحرك المرجح (λ=0.25)",
                             line=dict(color=C["accent"], width=2.4),
                             hovertemplate="%{x}<br>المتوسط المتحرك المرجح: %{y:.1f}<extra></extra>"))
    fig.add_trace(go.Scatter(x=m["ym"], y=[mu + 3 * ew_sd] * len(vals), mode="lines",
                             name="حد التحكم العلوي (+3σ)", line=dict(color=C["red"], dash="dash", width=1.2)))
    fig.add_trace(go.Scatter(x=m["ym"], y=[mu - 3 * ew_sd] * len(vals), mode="lines",
                             name="حد التحكم السفلي (−3σ)", line=dict(color=C["red"], dash="dash", width=1.2)))
    fig.add_trace(go.Scatter(x=m["ym"], y=[mu] * len(vals), mode="lines",
                             name="خط الأساس", line=dict(color=C["amber"], dash="dot", width=1)))
    fig.update_xaxes(tickformat="%Y-%m")
    return base_layout(fig, "مخطط التحكم EWMA — كشف الانحرافات عن خط الأساس",
                       ylabel="سفن لكل مشاهدة")


def chart_cusum(scenes=None):
    """CUSUM chart."""
    import plotly.graph_objects as go
    from charts import C, FONT, base_layout

    scenes = scenes if scenes is not None else load_scenes()
    monthly = build_monthly(scenes)
    m = monthly[monthly["n_obs"] > 0].sort_values("ym").reset_index(drop=True)
    vals = m["mean_ships_port_adj"].values
    n_base = min(24, len(vals) - 1)
    mu = float(np.mean(vals[:n_base]))
    sd = float(np.std(vals[:n_base])) or 1.0
    k = 0.5
    c_plus = c_minus = 0.0
    cp, cm = [], []
    for i in range(len(vals)):
        v = (vals[i] - mu) / sd
        c_plus = max(0, c_plus + v - k)
        c_minus = max(0, c_minus - v - k)
        cp.append(c_plus); cm.append(c_minus)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=m["ym"], y=cp, mode="lines", name="المجموع التراكمي الموجب (ارتفاع)",
                             line=dict(color=C["red"], width=2), fill="tozeroy",
                             fillcolor="rgba(248,113,113,0.08)",
                             hovertemplate="%{x}<br>%{y:.2f}<extra></extra>"))
    fig.add_trace(go.Scatter(x=m["ym"], y=cm, mode="lines", name="المجموع التراكمي السالب (انخفاض)",
                             line=dict(color=C["emerald"], width=2),
                             hovertemplate="%{x}<br>%{y:.2f}<extra></extra>"))
    fig.add_hline(y=5, line_dash="dash", line_color="rgba(156,163,175,0.5)",
                  annotation_text="حد القرار h=5")
    fig.update_xaxes(tickformat="%Y-%m")
    return base_layout(fig, "مخطط CUSUM — تراكم الانحرافات عن خط الأساس", ylabel="CUSUM")


def run():
    res, m = detect_anomalies()
    print(json.dumps(res, ensure_ascii=False, indent=1))
    # save for dashboard/report
    with open(os.path.join(DET_DIR, "anomalies.json"), "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    chart_ewma().write_image(os.path.join(CHART_DIR, "ewma.png"), width=1280, height=560, scale=1.6)
    chart_cusum().write_image(os.path.join(CHART_DIR, "cusum.png"), width=1280, height=560, scale=1.6)
    print("charts saved")


if __name__ == "__main__":
    import os
    from config import CHART_DIR
    run()
