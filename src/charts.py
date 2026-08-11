# -*- coding: utf-8 -*-
"""
Plotly charts (interactive HTML + static PNG) for the Latakia port activity
monitoring system. All values come from the real detection dataset.

Unified visual language: dark "mission control" theme, one palette, refined
Arabic typography, no emoji in titles.
"""
import os, json
import numpy as np
import pandas as pd
import plotly.graph_objects as go

from config import DET_DIR, CHART_DIR

# ----------------------------------------------------------------------
# Design tokens (shared with the dashboard)
# ----------------------------------------------------------------------
# Power BI dark theme palette
C = dict(
    bg="#14161A",          # canvas
    panel="#1E2126",       # visual card
    ink="#F0F0F0",         # primary text
    ink_dim="#9CA3AF",     # secondary text
    grid="rgba(156,163,175,0.16)",
    accent="#01B8AA",      # Power BI teal
    amber="#F59E0B",
    emerald="#34D399",
    red="#F87171",
    violet="#A78BFA",
    cyan="#22D3EE",
    slate="#6B7280",
)
PALETTE = [C["accent"], C["amber"], C["emerald"], C["red"], C["violet"], C["cyan"]]
FONT = ("'IBM Plex Sans Arabic','Noto Naskh Arabic','Noto Sans Arabic',"
        "'Segoe UI',Tahoma,Arial,sans-serif")

# ---- context events (documented, real-world, for chart annotation) ------
EVENTS = [
    dict(date="2021-12-07", label="غارة على المرفأ (7 كانون الأول 2021)"),
    dict(date="2021-12-28", label="غارة ثانية على المرفأ (28 كانون الأول 2021)"),
    dict(date="2023-02-06", label="زلزال 6 شباط 2023"),
    dict(date="2024-12-09", label="ضربات على المرفأ (9 كانون الأول 2024)"),
    dict(date="2024-12-10", label="هجوم بحري (10 كانون الأول 2024)"),
]

MONTH_AR = ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو",
            "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]


def base_layout(fig, title, ylabel="", xlabel="", legend=True):
    fig.update_layout(
        title=dict(text=title, x=0.5, xanchor="center",
                   font=dict(size=16.5, family=FONT, color=C["ink"])),
        paper_bgcolor=C["bg"], plot_bgcolor=C["bg"],
        font=dict(family=FONT, color=C["ink"]),
        xaxis=dict(title=xlabel, showgrid=True, gridcolor=C["grid"],
                   zeroline=False, linecolor="rgba(140,163,199,0.25)",
                   tickfont=dict(color=C["ink_dim"])),
        yaxis=dict(title=ylabel, showgrid=True, gridcolor=C["grid"],
                   zeroline=False, linecolor="rgba(140,163,199,0.25)",
                   tickfont=dict(color=C["ink_dim"])),
        margin=dict(l=56, r=24, t=64, b=46),
        hoverlabel=dict(bgcolor=C["panel"], bordercolor="rgba(140,163,199,0.35)",
                        font=dict(family=FONT, color=C["ink"])),
    )
    if legend:
        fig.update_layout(legend=dict(orientation="h", yanchor="bottom", y=1.02,
                                      xanchor="right", x=1, font=dict(color=C["ink_dim"])))
    return fig


def add_events(fig, monthly):
    if "ym" in monthly.columns:
        ym = set(monthly["ym"].astype(str))
    else:
        ym = set(pd.to_datetime(monthly["datetime"]).dt.strftime("%Y-%m"))
    for ev in EVENTS:
        if ev["date"][:7] in ym:
            fig.add_vline(x=ev["date"][:7], line_dash="dot", line_color=C["red"],
                          opacity=0.45, line_width=1)
    return fig


def chart_monthly_line(monthly):
    m = monthly[monthly["n_obs"] > 0]
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=m["ym"], y=m["mean_ships_port_adj"], mode="lines+markers",
        name="مؤشر النشاط — سفن لكل مشاهدة (مصحح)",
        line=dict(color=C["accent"], width=2.6), marker=dict(size=6.5, color=C["accent"]),
        fill="tozeroy", fillcolor="rgba(56,189,248,0.07)",
        hovertemplate="%{x}<br>%{y:.1f} سفينة لكل مشاهدة<extra></extra>"))
    fig.add_trace(go.Scatter(
        x=m["ym"], y=m["mean_ships_port"], mode="lines",
        name="غير مصحح", line=dict(color=C["slate"], width=1.2, dash="dot"),
        hovertemplate="%{x}<br>%{y:.1f}<extra></extra>"))
    fig.add_trace(go.Bar(
        x=monthly["ym"], y=monthly["n_obs"], name="مشاهدات الشهر",
        marker_color="rgba(56,189,248,0.16)", yaxis="y2",
        hovertemplate="%{x}<br>%{y} مشاهدات<extra></extra>"))
    fig.update_layout(yaxis2=dict(overlaying="y", side="right", showgrid=False,
                                  title="", tickfont=dict(color=C["ink_dim"])),
                      hovermode="x unified")
    fig.update_xaxes(tickformat="%Y-%m")
    add_events(fig, monthly)
    return base_layout(fig, "النشاط الشهري في حوض المرفأ",
                       ylabel="سفن لكل مشاهدة")


def chart_yearly(yearly):
    y = yearly[yearly["data_status"] == "ok"]
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=y["year"].astype(str), y=y["annual_mean_ships_port"],
        name="متوسط النشاط السنوي",
        marker_color=C["accent"], marker_line_color="rgba(255,255,255,0.12)",
        text=[f"{v:.1f}" for v in y["annual_mean_ships_port"]],
        textposition="outside", textfont=dict(color=C["ink"]),
        hovertemplate="%{x}<br>%{y:.1f} سفينة لكل مشاهدة<extra></extra>"))
    fig.add_trace(go.Scatter(
        x=y["year"].astype(str), y=y["annual_mean_adj"],
        name="بعد تصحيح التغطية", mode="lines+markers",
        line=dict(color=C["amber"], width=2), marker=dict(size=7, color=C["amber"])))
    for _, r in y.iterrows():
        if pd.notna(r["yoy_pct"]):
            col = C["emerald"] if r["yoy_pct"] >= 0 else C["red"]
            fig.add_annotation(x=str(r["year"]), y=r["annual_mean_ships_port"],
                               text=f"{r['yoy_pct']:+.0f}%", showarrow=False,
                               yshift=24, font=dict(size=11.5, color=col, family=FONT))
    return base_layout(fig, "النشاط السنوي والتغير بين السنوات", ylabel="سفن لكل مشاهدة")


def chart_monthly_comparison(monthly):
    m = monthly[monthly["n_obs"] > 0]
    years = sorted(m["year"].unique())
    fig = go.Figure()
    for i, y in enumerate(years):
        g = m[m["year"] == y]
        fig.add_trace(go.Bar(
            x=g["month"], y=g["mean_ships_port_adj"], name=str(y),
            marker_color=PALETTE[i % len(PALETTE)],
            hovertemplate=f"{y} · شهر %{{x}}: %{{y:.1f}} سفينة لكل مشاهدة<extra></extra>"))
    fig.update_layout(barmode="group",
                      xaxis=dict(tickmode="array", tickvals=list(range(1, 13)), ticktext=MONTH_AR))
    return base_layout(fig, "المقارنة الشهرية بين السنوات", ylabel="سفن لكل مشاهدة")


def chart_heatmap(monthly):
    m = monthly[monthly["n_obs"] > 0]
    years = sorted(m["year"].unique())
    z = np.full((len(years), 12), np.nan)
    for i, y in enumerate(years):
        for _, r in m[m["year"] == y].iterrows():
            z[i, r["month"] - 1] = r["mean_ships_port_adj"]
    fig = go.Figure(go.Heatmap(
        z=z, x=[str(i) for i in range(1, 13)], y=[str(y) for y in years],
        colorscale=[[0, "#0E1B33"], [0.45, "#155E9E"], [0.75, "#F59E0B"], [1, "#F87171"]],
        zmin=0, zmax=max(8, np.nanmax(z) if np.isfinite(z).any() else 8),
        text=[[f"{v:.1f}" if np.isfinite(v) else "" for v in row] for row in z],
        texttemplate="%{text}", textfont=dict(color="rgba(255,255,255,0.92)", size=11),
        hovertemplate="سنة %{y} · %{x} <br>%{z:.1f} سفينة لكل مشاهدة<extra></extra>",
        colorbar=dict(title="سفن لكل مشاهدة", title_font=dict(size=11, color=C["ink_dim"]),
                      tickfont=dict(color=C["ink_dim"]))))
    fig.update_layout(xaxis=dict(tickmode="array", tickvals=list(range(1, 13)), ticktext=MONTH_AR),
                      yaxis=dict(autorange="reversed"))
    return base_layout(fig, "خريطة النشاط الحرارية — سنة × شهر", legend=False)


def chart_change_detection(monthly):
    m = monthly[monthly["n_obs"] > 0].copy()
    m["roll3"] = m["mean_ships_port_adj"].rolling(3, center=True, min_periods=2).mean()
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=m["ym"], y=m["mean_ships_port_adj"], mode="markers",
        name="قيمة شهرية", marker=dict(size=6, color=C["accent"], opacity=0.65),
        hovertemplate="%{x}<br>%{y:.1f} سفينة لكل مشاهدة<extra></extra>"))
    fig.add_trace(go.Scatter(
        x=m["ym"], y=m["roll3"], mode="lines",
        name="متوسط متحرك (3 أشهر)", line=dict(color=C["red"], width=2.4),
        hovertemplate="%{x}<br>%{y:.1f}<extra></extra>"))
    post = m[m["ym"] >= "2024-12"]
    if len(post):
        fig.add_vrect(x0=post["ym"].iloc[0], x1=post["ym"].iloc[-1],
                      fillcolor="rgba(248,113,113,0.05)", line_width=0,
                      annotation_text="ما بعد كانون الأول 2024",
                      annotation_position="top left",
                      annotation_font=dict(color=C["ink_dim"], size=11, family=FONT))
    fig.update_layout(hovermode="x unified")
    fig.update_xaxes(tickformat="%Y-%m")
    add_events(fig, monthly)
    return base_layout(fig, "كشف التغير — القيم الشهرية والمتوسط المتحرك", ylabel="سفن لكل مشاهدة")


def chart_scene_scatter(scenes):
    g = scenes[scenes["error"].isna() | (scenes["error"] == "")]
    fig = go.Figure()
    fig.add_trace(go.Scattergl(
        x=g["datetime"], y=g["n_est_in_port"], mode="markers",
        name="كل مشهد (سفن داخل المرفأ)",
        marker=dict(size=6, color=g["sea_roughness"], colorscale=[[0, "#155E9E"], [1, "#F59E0B"]],
                    colorbar=dict(title="خشونة البحر", title_font=dict(size=11, color=C["ink_dim"]),
                                  tickfont=dict(color=C["ink_dim"])),
                    line=dict(width=0.4, color="rgba(255,255,255,0.35)"), opacity=0.88),
        customdata=np.stack([g["id"], g["coverage"]], axis=-1),
        hovertemplate="%{x|%Y-%m-%d %H:%M}Z<br>سفن في المرفأ: %{y}"
                      "<br><span style='font-size:10px'>%{customdata[0]}</span>"
                      "<br>تغطية: %{customdata[1]:.2f}<extra></extra>"))
    fig.update_xaxes(tickformat="%Y-%m")
    add_events(fig, scenes)
    return base_layout(fig, "جميع المشاهدات الفردية",
                       ylabel="سفن داخل المرفأ")


def chart_mom(monthly):
    m = monthly[monthly["n_obs"] > 0].copy()
    m["mom"] = m["mean_ships_port_adj"].pct_change() * 100
    colors = [C["emerald"] if v >= 0 else C["red"] for v in m["mom"].fillna(0)]
    fig = go.Figure(go.Bar(
        x=m["ym"], y=m["mom"], marker_color=colors,
        hovertemplate="%{x}<br>%{y:+.1f}%<extra></extra>"))
    fig.add_hline(y=0, line_color="rgba(140,163,199,0.4)", line_width=1)
    fig.update_xaxes(tickformat="%Y-%m")
    return base_layout(fig, "التغير الشهري بين الشهور المتتالية", ylabel="%")


def chart_boxplot(scenes):
    """Distribution of per-scene in-port counts by year (box plot)."""
    g = scenes[scenes["error"].isna() | (scenes["error"] == "")].copy()
    g["year"] = pd.to_datetime(g["datetime"]).dt.year
    years = sorted(g["year"].unique())
    fig = go.Figure()
    for i, y in enumerate(years):
        vals = g[g["year"] == y]["n_est_in_port"]
        fig.add_trace(go.Box(y=vals, name=str(y), boxpoints="outliers",
                             marker_color=PALETTE[i % len(PALETTE)],
                             marker=dict(size=3.5, opacity=0.7),
                             line=dict(width=1.6),
                             hovertemplate="%{y} سفينة<extra>" + str(y) + "</extra>"))
    return base_layout(fig, "توزيع السفن لكل مشهد حسب السنة",
                       ylabel="سفن في الحوض")


def chart_radar(monthly):
    """Monthly activity profile: 2026 vs 2022-2025 average (seasonal shape)."""
    m = monthly[monthly["n_obs"] > 0]
    past, cur = [], []
    for mo in range(1, 13):
        p = m[(m["month"] == mo) & (m["year"].isin([2022, 2023, 2024, 2025]))]["mean_ships_port_adj"]
        c = m[(m["month"] == mo) & (m["year"] == 2026)]["mean_ships_port_adj"]
        past.append(round(float(p.mean()), 1) if len(p) else None)
        cur.append(round(float(c.mean()), 1) if len(c) else None)
    _vals = [v for v in (past + cur) if v is not None]
    rmax = (max(_vals) * 1.15) if _vals else 10
    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(r=past, theta=MONTH_AR, fill="toself",
                                  name="متوسط 2022–2025",
                                  line=dict(color=C["slate"], width=1.8),
                                  fillcolor="rgba(100,116,139,0.25)",
                                  hovertemplate="%{theta}: %{r}<extra>متوسط 2022–2025</extra>"))
    fig.add_trace(go.Scatterpolar(r=cur, theta=MONTH_AR, fill="toself",
                                  name="2026",
                                  line=dict(color=C["accent"], width=2.4),
                                  fillcolor="rgba(56,189,248,0.30)",
                                  hovertemplate="%{theta}: %{r}<extra>2026</extra>"))
    fig.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0, rmax],
                                                 tickfont=dict(color=C["ink_dim"]),
                                                 gridcolor=C["grid"]),
                                 angularaxis=dict(tickfont=dict(color=C["ink_dim"], size=11),
                                                  gridcolor=C["grid"])),
                      legend=dict(orientation="h", yanchor="bottom", y=1.02,
                                  xanchor="center", x=0.5, font=dict(color=C["ink_dim"])))
    return base_layout(fig, "الملف الموسمي للنشاط — 2026 مقابل متوسط 2022–2025",
                       ylabel="")


def chart_waterfall(yearly):
    """Year-over-year activity waterfall."""
    y = yearly[yearly["data_status"] == "ok"].sort_values("year")
    vals = y["annual_mean_adj"].tolist()
    years = y["year"].astype(str).tolist()
    if len(vals) == 0:
        fig = go.Figure()
        fig.add_annotation(text="لا توجد بيانات ضمن الفلاتر المحددة", showarrow=False,
                           font=dict(size=14, family=FONT, color=C["ink_dim"]))
        return base_layout(fig, "التغير السنوي للنشاط — المخطط التراجعي", ylabel="سفن لكل مشاهدة")
    meas = ["absolute"] + ["relative"] * (len(vals) - 2) + ["total"]
    fig = go.Figure(go.Waterfall(
        x=years, y=vals, measure=meas,
        increasing=dict(marker_color=C["emerald"]),
        decreasing=dict(marker_color=C["red"]),
        totals=dict(marker_color=C["accent"]),
        connector=dict(line=dict(color="rgba(140,163,199,0.4)", width=1)),
        text=[f"{v:.1f}" for v in vals],
        textposition="outside", textfont=dict(color=C["ink"], size=11),
        hovertemplate="%{x}: %{y:.1f} سفينة لكل مشاهدة<extra></extra>"))
    return base_layout(fig, "التغير السنوي للنشاط — المخطط التراجعي",
                       ylabel="سفن لكل مشاهدة")


def chart_bubble(monthly):
    """Monthly port vs anchorage bubble chart (demand pressure view)."""
    m = monthly[monthly["n_obs"] > 0]
    fig = go.Figure()
    for i, y in enumerate(sorted(m["year"].unique())):
        g = m[m["year"] == y]
        fig.add_trace(go.Scatter(
            x=g["mean_ships_port_adj"], y=g["mean_anchorage"],
            mode="markers+text", text=g["month"], textposition="top center",
            textfont=dict(size=9, color=C["ink_dim"]),
            name=str(y),
            marker=dict(size=np.clip(g["n_obs"] * 2.4, 8, 34),
                        color=PALETTE[i % len(PALETTE)], opacity=0.72,
                        line=dict(width=1, color="rgba(255,255,255,0.5)")),
            customdata=np.stack([g["ym"], g["n_obs"]], axis=-1),
            hovertemplate=("شهر %{text} (%{customdata[0]})<br>الحوض: %{x:.1f}"
                           "<br>المرسى: %{y:.1f}<br>مشاهدات: %{customdata[1]}<extra></extra>")))
    fig.add_hline(y=10, line_dash="dot", line_color="rgba(140,163,199,0.35)", line_width=1)
    return base_layout(fig, "ضغط التشغيل — سفن الحوض مقابل سفن المرسى (حجم الفقاعة = المشاهدات)",
                       xlabel="سفن لكل مشاهدة في الحوض", ylabel="سفن لكل مشاهدة في المرسى")


def chart_length_hist(scenes):
    """Vessel length distribution histogram."""
    import json as _json
    from config import S1_DIR
    g = scenes[scenes["error"].isna() | (scenes["error"] == "")].copy()
    L = []
    for _, r in g.iterrows():
        vj = os.path.normpath(os.path.join(S1_DIR, r["id"], "vessels.json"))
        if not os.path.exists(vj):
            continue
        for v in _json.load(open(vj, encoding="utf-8")):
            if v.get("length_m"):
                L.append(v["length_m"])
    L = np.array(L)
    if len(L) == 0:
        fig = go.Figure()
        fig.add_annotation(text="لا توجد سفن ضمن الفلاتر المحددة", showarrow=False,
                           font=dict(size=14, family=FONT, color=C["ink_dim"]))
        return base_layout(fig, "توزيع أطوال السفن المكتشفة", xlabel="الطول (م)", ylabel="عدد السجلات")
    fig = go.Figure(go.Histogram(x=L, nbinsx=34, marker_color=C["accent"], opacity=0.85,
                                 marker_line=dict(width=0.4, color=C["bg"]),
                                 hovertemplate="الطول %{x:.0f}م · %{y} سفينة<extra></extra>"))
    fig.add_vline(x=np.median(L), line_dash="dash", line_color=C["amber"], line_width=1.5)
    return base_layout(fig, "توزيع أطوال السفن المكتشفة",
                       xlabel="الطول (م)", ylabel="عدد السجلات")


def chart_donut(scenes):
    """Zone composition donut."""
    import json as _json
    from config import S1_DIR
    g = scenes[scenes["error"].isna() | (scenes["error"] == "")].copy()
    cnt = {2: 0, 1: 0, 0: 0}
    for _, r in g.iterrows():
        vj = os.path.normpath(os.path.join(S1_DIR, r["id"], "vessels.json"))
        if not os.path.exists(vj):
            continue
        for v in _json.load(open(vj, encoding="utf-8")):
            cnt[v["zone"]] = cnt.get(v["zone"], 0) + 1
    if sum(cnt.values()) == 0:
        fig = go.Figure()
        fig.add_annotation(text="لا توجد سفن ضمن الفلاتر المحددة", showarrow=False,
                           font=dict(size=14, family=FONT, color=C["ink_dim"]))
        return base_layout(fig, "توزيع السفن حسب المنطقة", legend=False)
    fig = go.Figure(go.Pie(
        labels=["داخل الحوض", "المرسى / الاقتراب", "مياه العبور"],
        values=[cnt[2], cnt[1], cnt[0]], hole=0.58,
        marker=dict(colors=["#FB7185", "#A78BFA", "#38BDF8"],
                    line=dict(color=C["bg"], width=2)),
        textinfo="label+percent", textfont=dict(size=11.5, color="#0B1220"),
        hovertemplate="%{label}<br>%{value:,} سجلًا (%{percent})<extra></extra>"))
    fig.update_layout(showlegend=False,
                      annotations=[dict(text=f"{sum(cnt.values()):,}<br><span style='font-size:11px'>سجلًا</span>",
                                        x=0.5, y=0.5, showarrow=False,
                                        font=dict(size=17, family=FONT, color=C["ink"]))])
    return base_layout(fig, "توزيع السفن حسب المنطقة", legend=False)


def chart_s1s2(pairs):
    """S1 vs S2 validation scatter."""
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=pairs["s1_port"], y=pairs["s2_port"], mode="markers",
        name="أزواج تحقق", marker=dict(size=9, color=pairs["cloud_pct"],
                                       colorscale=[[0, "#34D399"], [1, "#F59E0B"]],
                                       colorbar=dict(title="غيوم %",
                                                     title_font=dict(size=10, color=C["ink_dim"]),
                                                     tickfont=dict(color=C["ink_dim"])),
                                       opacity=0.85, line=dict(width=0.4, color="white")),
        customdata=np.stack([pairs["s1_date"].astype(str), pairs["gap_hours"]], axis=-1),
        hovertemplate=("S1: %{x} · S2: %{y}<br>التاريخ: %{customdata[0]}"
                       "<br>الفارق: %{customdata[1]} ساعة<extra></extra>")))
    mx = max(pairs["s1_port"].max(), pairs["s2_port"].max())
    fig.add_trace(go.Scatter(x=[0, mx], y=[0, mx], mode="lines",
                             name="خط التطابق y=x",
                             line=dict(color="rgba(140,163,199,0.5)", dash="dash", width=1)))
    return base_layout(fig, "التحقق المتقاطع — Sentinel-1 مقابل Sentinel-2 (منطقة الحوض)",
                       xlabel="سفن في الحوض (S1 رادار)", ylabel="سفن في الحوض (S2 بصري)")


def chart_gauge(monthly):
    """KPI gauge: current activity vs historical baseline."""
    m = monthly[monthly["n_obs"] > 0]
    _c = m[m["year"] == 2026]["mean_ships_port_adj"]
    _b = m[m["year"].isin([2022, 2023, 2024, 2025])]["mean_ships_port_adj"]
    if len(_c) == 0 or len(_b) == 0:
        fig = go.Figure()
        fig.add_annotation(text="لا توجد بيانات ضمن الفلاتر المحددة", showarrow=False,
                           font=dict(size=14, family=FONT, color=C["ink_dim"]))
        return base_layout(fig, "مؤشر النشاط الحالي مقابل خط الأساس", legend=False)
    cur = round(float(_c.mean()), 2)
    base = round(float(_b.mean()), 2)
    fig = go.Figure(go.Indicator(
        mode="gauge+number+delta",
        value=cur,
        number=dict(suffix=" سفن لكل مشاهدة", font=dict(size=26, family=FONT, color=C["ink"])),
        delta=dict(reference=base, relative=True, valueformat=".0%",
                   increasing=dict(color=C["emerald"]), decreasing=dict(color=C["red"]),
                   font=dict(size=16, family=FONT)),
        gauge=dict(axis=dict(range=[0, max(28, cur * 1.25)],
                             tickfont=dict(color=C["ink_dim"])),
                   bar=dict(color=C["accent"], thickness=0.32),
                   bgcolor="rgba(15,23,40,0.6)",
                   borderwidth=1, bordercolor=C["line"] if "line" in C else "#1C2740",
                   steps=[dict(range=[0, base], color="rgba(56,189,248,0.10)"),
                          dict(range=[base, max(28, cur * 1.25)], color="rgba(245,158,11,0.12)")])))
    fig.update_layout(margin=dict(l=40, r=40, t=50, b=20), paper_bgcolor=C["bg"],
                      plot_bgcolor=C["bg"])
    return base_layout(fig, "مؤشر النشاط الحالي (2026) مقابل خط الأساس 2022–2025", legend=False)


def save_all(monthly, yearly, scenes, chart_dir=None):
    charts = dict(
        monthly_line=chart_monthly_line(monthly),
        yearly=chart_yearly(yearly),
        monthly_comparison=chart_monthly_comparison(monthly),
        heatmap=chart_heatmap(monthly),
        change=chart_change_detection(monthly),
        scatter=chart_scene_scatter(scenes),
        mom=chart_mom(monthly),
        boxplot=chart_boxplot(scenes),
        radar=chart_radar(monthly),
        waterfall=chart_waterfall(yearly),
        bubble=chart_bubble(monthly),
        hist_length=chart_length_hist(scenes),
        donut=chart_donut(scenes),
        gauge=chart_gauge(monthly),
    )
    chart_dir = chart_dir or CHART_DIR
    os.makedirs(chart_dir, exist_ok=True)
    for name, fig in charts.items():
        fig.write_html(os.path.join(chart_dir, f"{name}.html"),
                       include_plotlyjs="cdn", full_html=True,
                       config={"displaylogo": False, "displayModeBar": False})
        try:
            fig.write_image(os.path.join(chart_dir, f"{name}.png"),
                            width=1280, height=560, scale=1.6)
        except Exception as e:
            print("png fail", name, e)
    return charts


if __name__ == "__main__":
    import sys
    sys.path.insert(0, ".")
    from analysis import load_scenes, build_monthly, build_yearly
    scenes = load_scenes()
    monthly = build_monthly(scenes)
    yearly = build_yearly(monthly)
    save_all(monthly, yearly, scenes)
    print("charts saved to", CHART_DIR)
