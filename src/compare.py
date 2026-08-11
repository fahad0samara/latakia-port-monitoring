# -*- coding: utf-8 -*-
"""
Regional comparison: Port of Latakia vs Port of Tartus vs Port of Baniyas.
Same pipeline, same scenes, same normalization -> like-for-like comparison.
Outputs: comparison charts + a summary table of relative change.
"""
import os, json
import numpy as np
import pandas as pd
import plotly.graph_objects as go

from config import ROOT, DET_DIR, CHART_DIR
from charts import C, FONT, base_layout, add_events, EVENTS

TARTUS_DIR = os.path.join(ROOT, "data", "tartus")
BAN_DIR = os.path.join(ROOT, "data", "baniyas")


def load_series():
    """Monthly series for the three ports (ships/observation in port basin)."""
    lat = pd.read_csv(os.path.join(DET_DIR, "monthly.csv"))
    tar = pd.read_csv(os.path.join(TARTUS_DIR, "tartus_monthly.csv"))
    lat = lat[lat["n_obs"] > 0][["ym", "mean_ships_port_adj", "n_obs"]].rename(
        columns={"mean_ships_port_adj": "latakia", "n_obs": "lat_n"})
    tar = tar[tar["n_obs"] > 0][["ym", "mean_ships_port_adj", "n_obs"]].rename(
        columns={"mean_ships_port_adj": "tartus", "n_obs": "tar_n"})
    df = lat.merge(tar, on="ym", how="outer").sort_values("ym").reset_index(drop=True)
    # Baniyas (only when processed; graceful absence)
    ban_csv = os.path.join(BAN_DIR, "baniyas_monthly.csv")
    if os.path.exists(ban_csv):
        ban = pd.read_csv(ban_csv)
        ban = ban[ban["n_obs"] > 0][["ym", "mean_ships_port_adj", "n_obs"]].rename(
            columns={"mean_ships_port_adj": "baniyas", "n_obs": "ban_n"})
        df = df.merge(ban, on="ym", how="outer")
    else:
        df["baniyas"] = np.nan
        df["ban_n"] = 0
    return df


def chart_comparison(df):
    """Dual-line comparison of the two ports."""
    fig = go.Figure()
    m = df[df["latakia"].notna()]
    fig.add_trace(go.Scatter(x=m["ym"], y=m["latakia"], mode="lines+markers",
                             name="اللاذقية", line=dict(color=C["accent"], width=2.4),
                             marker=dict(size=5.5, color=C["accent"]),
                             hovertemplate="%{x}<br>اللاذقية: %{y:.1f}<extra></extra>"))
    m2 = df[df["tartus"].notna()]
    fig.add_trace(go.Scatter(x=m2["ym"], y=m2["tartus"], mode="lines+markers",
                             name="طرطوس", line=dict(color=C["amber"], width=2.4),
                             marker=dict(size=5.5, color=C["amber"]),
                             hovertemplate="%{x}<br>طرطوس: %{y:.1f}<extra></extra>"))
    if "baniyas" in df.columns and df["baniyas"].notna().any():
        m3 = df[df["baniyas"].notna()]
        fig.add_trace(go.Scatter(x=m3["ym"], y=m3["baniyas"], mode="lines+markers",
                                 name="بانياس", line=dict(color=C["violet"], width=2.2, dash="dot"),
                                 marker=dict(size=5, color=C["violet"]),
                                 hovertemplate="%{x}<br>بانياس: %{y:.1f}<extra></extra>"))
    fig.update_xaxes(tickformat="%Y-%m")
    fig.update_layout(hovermode="x unified")
    return base_layout(fig, "مقارنة النشاط الشهري — اللاذقية · طرطوس · بانياس",
                       ylabel="سفن لكل مشاهدة في الحوض")


def chart_gap(df):
    """Latakia minus Tartus gap (positive = Latakia busier)."""
    g = df.copy()
    g["gap"] = g["latakia"] - g["tartus"]
    g = g.dropna(subset=["gap"])
    fig = go.Figure()
    colors = [C["accent"] if v >= 0 else C["red"] for v in g["gap"]]
    fig.add_trace(go.Bar(x=g["ym"], y=g["gap"], marker_color=colors,
                         hovertemplate="%{x}<br>الفجوة: %{y:+.1f} سفينة لكل مشاهدة<extra></extra>"))
    fig.add_hline(y=0, line_color="rgba(156,163,175,0.4)", line_width=1)
    fig.update_xaxes(tickformat="%Y-%m")
    return base_layout(fig, "فجوة النشاط — اللاذقية ناقص طرطوس",
                       ylabel="سفن لكل مشاهدة")


def yearly_comparison():
    """Annual means side by side + relative change vs baseline."""
    lat = pd.read_csv(os.path.join(DET_DIR, "yearly.csv"))
    tar = pd.read_csv(os.path.join(TARTUS_DIR, "tartus_yearly.csv"))
    out = pd.DataFrame({
        "year": lat["year"],
        "latakia": lat["annual_mean_adj"],
        "tartus": np.nan,
    })
    tar_map = dict(zip(tar["year"], tar["annual_mean"]))
    out["tartus"] = out["year"].map(tar_map)
    out["baniyas"] = np.nan
    ban_csv = os.path.join(BAN_DIR, "baniyas_yearly.csv")
    if os.path.exists(ban_csv):
        ban = pd.read_csv(ban_csv)
        out["baniyas"] = out["year"].map(dict(zip(ban["year"], ban["annual_mean"])))
    out["gap"] = (out["latakia"] - out["tartus"]).round(1)
    out["lat_yoy"] = lat["yoy_pct"].round(1)
    return out


def summary():
    """Like-for-like change for both ports in 2026 (Jan-Aug) vs 2025 (Jan-Aug)."""
    def _change(path, col):
        m = pd.read_csv(path)
        m = m[m["n_obs"] > 0]
        _end = m["ym"].max()          # last month with data (e.g. 2026-08)
        _y2 = int(_end[:4]); _m2 = int(_end[5:7])
        _y1 = _y2 - 1
        # same months in the previous year (like-for-like window)
        a = m[(m["ym"] >= f"{_y1}-01") & (m["ym"] <= f"{_y1}-{_m2:02d}")][col]
        b = m[(m["ym"] >= f"{_y2}-01") & (m["ym"] <= _end)][col]
        if len(a) and len(b):
            return dict(mean_25=round(float(a.mean()), 2), mean_26=round(float(b.mean()), 2),
                        pct=float((b.mean() - a.mean()) / a.mean() * 100),
                        n25=len(a), n26=len(b))
        return None
    out = dict(
        latakia=_change(os.path.join(DET_DIR, "monthly.csv"), "mean_ships_port_adj"),
        tartus=_change(os.path.join(TARTUS_DIR, "tartus_monthly.csv"), "mean_ships_port_adj"),
    )
    ban_csv = os.path.join(BAN_DIR, "baniyas_monthly.csv")
    out["baniyas"] = _change(ban_csv, "mean_ships_port_adj") if os.path.exists(ban_csv) else None
    return out


def build_charts():
    df = load_series()
    chart_comparison(df).write_image(os.path.join(CHART_DIR, "comparison.png"),
                                     width=1280, height=560, scale=1.6)
    chart_gap(df).write_image(os.path.join(CHART_DIR, "gap.png"),
                              width=1280, height=560, scale=1.6)
    # yearly side-by-side bar
    yc = yearly_comparison()
    fig = go.Figure()
    fig.add_trace(go.Bar(x=yc["year"].astype(str), y=yc["latakia"], name="اللاذقية",
                         marker_color=C["accent"],
                         hovertemplate="اللاذقية %{y:.1f}<extra></extra>"))
    fig.add_trace(go.Bar(x=yc["year"].astype(str), y=yc["tartus"], name="طرطوس",
                         marker_color=C["amber"],
                         hovertemplate="طرطوس %{y:.1f}<extra></extra>"))
    if yc["baniyas"].notna().any():
        fig.add_trace(go.Bar(x=yc["year"].astype(str), y=yc["baniyas"], name="بانياس",
                             marker_color=C["violet"],
                             hovertemplate="بانياس %{y:.1f}<extra></extra>"))
    fig.update_layout(barmode="group")
    fig = base_layout(fig, "متوسط النشاط السنوي — اللاذقية · طرطوس · بانياس", ylabel="سفن لكل مشاهدة")
    fig.write_image(os.path.join(CHART_DIR, "comparison_yearly.png"),
                    width=1280, height=560, scale=1.6)
    print("comparison charts saved")


if __name__ == "__main__":
    build_charts()
    print(json.dumps(summary(), ensure_ascii=False, indent=1))
