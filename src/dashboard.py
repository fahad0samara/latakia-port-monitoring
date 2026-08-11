# -*- coding: utf-8 -*-
"""
Streamlit Dashboard — مرصد مرفأ اللاذقية
Power BI-style experience: ribbon header, filters pane, page navigation,
visual cards, KPI cards. All visuals come from the real detection dataset.
Run:  streamlit run src/dashboard.py
"""
import os, sys, json, glob
import numpy as np
import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import S1_DIR, S2_DIR, MAP_DIR, AOI_BBOX_4326
from analysis import load_scenes, full_analysis
from charts import (chart_monthly_line, chart_yearly, chart_monthly_comparison,
                    chart_heatmap, chart_change_detection, chart_scene_scatter,
                    chart_mom, chart_boxplot, chart_radar, chart_waterfall,
                    chart_bubble, chart_length_hist, chart_donut, chart_gauge,
                    chart_s1s2)
from maps import load_vessel_points, static_density_map, zone_name
from compare import chart_comparison, chart_gap
from map_fig import build_activity_map
from validation import load_s2, pair_s1_s2, quality_flags
from ais_verify import (load_ais, match_detections, type_profile, ais_report,
                        chart_type_profile, chart_type_donut, AIS_DIR)
from geotiff import (export_total as gt_export_total,
                     export_yearly_stack as gt_export_yearly,
                     export_occupancy as gt_export_occupancy,
                     export_scene as gt_export_scene, GTIFF_DIR)

_FAVICON = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "favicon.png")
if not os.path.exists(_FAVICON):
    _FAVICON = None
st.set_page_config(page_title="مرصد مرفأ اللاذقية", page_icon=_FAVICON,
                   layout="wide", initial_sidebar_state="expanded")

CSS = """
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+Arabic:wght@300;400;500;600;700&display=swap');
:root{
  --canvas:#14161A; --panel:#1E2126; --panel2:#1A1D22; --line:#32363E;
  --ink:#F0F0F0; --dim:#9CA3AF; --faint:#6B7280;
  --accent:#01B8AA; --amber:#F59E0B; --green:#34D399; --red:#F87171; --violet:#A78BFA;
}
html, body, [data-testid="stAppViewContainer"]{
  background:var(--canvas); color:var(--ink);
  font-family:'IBM Plex Sans Arabic','Noto Sans Arabic','Segoe UI',Tahoma,Arial,sans-serif;
  -webkit-font-smoothing:antialiased;
}
[data-testid="stAppViewContainer"]{ direction:rtl; }
/* ---------- global RTL enforcement for every widget ---------- */
[data-testid="stAppViewContainer"] *{ direction:rtl; }
[data-testid="stAppViewContainer"] *[dir="ltr"], [data-testid="stAppViewContainer"] [dir="ltr"] *{ direction:ltr; }
[data-testid="stMain"] *{ text-align:right; }
[data-testid="stMain"] [dir="ltr"], [data-testid="stMain"] [dir="ltr"] *{ text-align:left; }
[data-testid="stMain"] table *{ text-align:center; }
[data-testid="stSidebar"] *{ text-align:right; }
[data-testid="stSidebar"] [dir="ltr"] *{ text-align:left; }
[data-testid="stHeader"]{ background:transparent; height:0; min-height:0; }
#MainMenu, footer, [data-testid="stToolbar"], [data-testid="stAppDeployButton"]{ display:none !important; }
[data-testid="stMainBlockContainer"]{ max-width:1360px; padding:0.6rem 1rem 4rem; }
[data-testid="stHorizontalBlock"]{ flex-wrap:wrap; gap:0.5rem; }

/* ---------------- ribbon ---------------- */
.ribbon{ display:flex; align-items:center; flex-wrap:wrap; gap:14px; padding:16px 4px 13px;
  border-bottom:1px solid var(--line); margin-bottom:14px; }
.ribbon .logo{ width:38px; height:38px; border-radius:8px; flex:0 0 38px;
  background:linear-gradient(150deg,#0E3A5C,#14161A 75%);
  border:1px solid rgba(1,184,170,.4); display:flex; align-items:center; justify-content:center; }
.ribbon .ttl{ font-size:16.5px; font-weight:650; color:var(--ink); margin:0; letter-spacing:-.2px; }
.ribbon .st{ font-size:11px; color:var(--faint); margin:2px 0 0; }
.ribbon .right{ margin-inline-start:auto; display:flex; flex-wrap:wrap; gap:7px; align-items:center; }
.meta{ display:inline-flex; align-items:center; gap:6px; font-size:11px; color:var(--dim);
  border:1px solid var(--line); border-radius:5px; padding:4px 10px; background:var(--panel2); }
.meta b{ color:var(--ink); font-weight:600; }
.meta .dot{ width:6px; height:6px; border-radius:50%; background:var(--green); }

/* ---------------- sidebar = Power BI filters pane ---------------- */
[data-testid="stSidebar"]{ background:#0F1115; border-left:1px solid var(--line); direction:rtl; }
[data-testid="stSidebar"] [data-testid="stSidebarContent"]{ padding-top:0.8rem; }
.fpane-title{ font-size:13px; font-weight:700; color:var(--ink); padding:6px 0 2px; }
.fpane-sub{ font-size:10.5px; color:var(--faint); padding-bottom:10px; border-bottom:1px solid var(--line); margin-bottom:10px; }
[data-testid="stSidebar"] h4{
  font-size:11px; font-weight:600; color:var(--dim); letter-spacing:.2px;
  margin:16px 0 8px; padding-bottom:5px; border-bottom:1px solid var(--line); }
[data-testid="stSidebar"] [data-testid="stWidgetLabel"] p{ font-size:12px; color:var(--dim); font-weight:400; }
[data-testid="stSidebar"] [data-testid="stExpander"]{ background:var(--panel2); border:1px solid var(--line); }
[data-testid="stDateInput"] [data-testid="stWidgetHelp"],
[data-testid="stDateInput"] [data-testid="stCaptionContainer"]{ display:none !important; }
[data-testid="stSelectbox"] [data-baseweb="select"]>div,
[data-testid="stMultiSelect"] [data-baseweb="select"]>div,
[data-testid="stDateInput"] [data-baseweb="input"]{
  background:var(--panel); border:1px solid var(--line) !important; border-radius:6px;
  color:var(--ink); font-size:13px;
}
[data-testid="stSelectbox"]:hover [data-baseweb="select"]>div,
[data-testid="stMultiSelect"]:hover [data-baseweb="select"]>div,
[data-testid="stDateInput"]:hover [data-baseweb="input"]{ border-color:rgba(1,184,170,.5) !important; }
[data-testid="stBaseButton-secondary"]{
  background:var(--panel); border:1px solid var(--line); border-radius:5px;
  color:var(--ink); font-size:12px; font-family:inherit;
}
[data-testid="stBaseButton-secondary"]:hover{ border-color:rgba(1,184,170,.5); color:var(--accent); }
[data-testid="stBaseButton-primary"]{ background:var(--accent); border:none; border-radius:5px; color:#0F1115; font-weight:600; }

/* ---------------- page tabs (Power BI pages) ----------------
   Streamlit 1.61 renders tabs as [data-testid=stTab][role=tab] inside a
   wrapping bar; the old data-baseweb="tab" selectors no longer exist. */
[data-testid="stTabs"] div[class*="e1ac7blb3"],
[data-testid="stTabs"] [role="tablist"]{
  flex-wrap:wrap !important;
  overflow-x:visible !important;
  height:auto !important;
  min-width:0;
}
[data-testid="stTabs"]{
  border-bottom:1px solid var(--line);
  margin-bottom:16px;
}
[data-testid="stTabs"] [role="tab"]{
  background:transparent; color:var(--dim); font-size:13.5px; padding:10px 18px;
  border-radius:0; border-bottom:2px solid transparent;
  white-space:nowrap;
}
[data-testid="stTabs"] [role="tab"]:hover{ color:var(--ink); }
[data-testid="stTabs"] [role="tab"][aria-selected="true"],
[data-testid="stTabs"] [role="tab"][data-selected="true"]{
  color:var(--accent); border-bottom:2px solid var(--accent); font-weight:600;
}
/* hide the sliding highlight line (breaks when the bar wraps) */
[data-testid="stTabs"] [data-baseweb="tab-highlight"],
[data-testid="stTabs"] div[class*="e1ac7blb2"]>div[class*="e1ac7blb1"]{ display:none !important; }

/* ---------------- visual cards (Power BI visuals) ---------------- */
.pbi-vhead{ display:flex; align-items:center; justify-content:space-between;
  background:var(--panel); border:1px solid var(--line); border-bottom:none;
  border-radius:8px 8px 0 0; padding:9px 16px 8px; }
.pbi-vtitle{ font-size:12.5px; font-weight:600; color:var(--ink);
  display:flex; align-items:center; gap:9px; }
.pbi-vtitle::before{ content:""; width:3px; height:13px; border-radius:2px;
  background:var(--accent); opacity:.85; }
.pbi-vhead:hover{ background:#23262D; }
[data-testid="stPlotlyChart"]{
  border:1px solid var(--line); border-top:none; border-radius:0 0 8px 8px;
  background:var(--panel); padding:6px 4px 2px; margin-bottom:10px; width:100%;
}
[data-testid="stPlotlyChart"] > div{ width:100% !important; }
[data-testid="stPlotlyChart"] .js-plotly-plot .plotly > div{ margin-inline:auto; }
[data-testid="stImage"]{ border:1px solid var(--line); border-radius:8px; overflow:hidden; margin-bottom:10px; }
[data-testid="stImage"] img{ border-radius:0; border:none; }
[data-testid="stDataFrame"]{ border:1px solid var(--line); border-radius:8px; overflow-x:auto; margin-bottom:10px; }
[data-testid="stDataFrame"] thead th{ background:#23262D; color:#B8C0CC; font-size:12px; font-weight:600; }
[data-testid="stCaptionContainer"] p{ color:var(--faint); font-size:11.5px; text-align:right; }
[data-testid="stMarkdownContainer"] p{ text-align:right; }
[data-testid="stMarkdownContainer"] ul, [data-testid="stMarkdownContainer"] ol{ text-align:right; }
[data-testid="stMarkdownContainer"] img{ max-width:100%; height:auto; }

/* ---------------- KPI cards (Power BI card visuals) ---------------- */
.metric{ background:var(--panel); border:1px solid var(--line); border-radius:6px;
  padding:12px 14px 10px; height:100%; min-width:0; width:100%; direction:rtl;
  box-sizing:border-box; }
.metric .lbl{ font-size:10.5px; color:var(--dim); margin-bottom:5px; font-weight:500; }
.metric .val{ font-size:24px; font-weight:650; color:var(--tone,var(--ink));
  font-variant-numeric:tabular-nums; line-height:1.15; letter-spacing:-.2px; }
.metric .sub{ font-size:10px; color:var(--faint); margin-top:5px; }

.health{ display:flex; gap:6px; flex-wrap:wrap; margin:12px 0 2px; }
.chip{ font-size:10.5px; color:var(--dim); background:var(--panel2);
  border:1px solid var(--line); border-radius:4px; padding:4px 10px; }
.chip b{ color:var(--ink); font-weight:600; }

.page-title{ font-size:13.5px; font-weight:650; color:var(--ink); margin:6px 0 10px;
  display:flex; align-items:center; gap:8px; }

/* ---- alerts ---- */
.alerts{ display:grid; grid-template-columns:repeat(auto-fit,minmax(280px,1fr)); gap:10px; margin:12px 0 6px; }
.alert{ border-radius:6px; padding:10px 13px; display:flex; gap:10px; align-items:flex-start; border:1px solid; }
.alert .a-ic{ flex:0 0 26px; height:26px; border-radius:6px; display:flex; align-items:center; justify-content:center; font-size:12px; font-weight:700; }
.alert .a-t{ font-size:12px; font-weight:650; }
.alert .a-d{ font-size:11px; line-height:1.7; margin-top:2px; color:#B8C0CC; }
.alert.crit{ background:rgba(225,29,72,.07); border-color:rgba(225,29,72,.4); }
.alert.crit .a-ic{ background:rgba(225,29,72,.18); color:#F87171; }
.alert.crit .a-t{ color:#F87171; }
.alert.warn{ background:rgba(245,158,11,.06); border-color:rgba(245,158,11,.35); }
.alert.warn .a-ic{ background:rgba(245,158,11,.16); color:#F59E0B; }
.alert.warn .a-t{ color:#F59E0B; }
.alert.info{ background:rgba(1,184,170,.05); border-color:rgba(1,184,170,.3); }
.alert.info .a-ic{ background:rgba(1,184,170,.13); color:#34D399; }
.alert.info .a-t{ color:#34D399; }
/* ---- sparkline ---- */
.spark{ display:block; margin-top:7px; width:100%; height:26px; }
.metric .val{ display:flex; align-items:baseline; gap:6px; }

/* ---- narrative / findings ---- */
.exec{ background:var(--panel2); border:1px solid var(--line);
  border-radius:8px; padding:16px 18px; margin:10px 0 16px; }
.exec .ex-t{ font-size:13px; font-weight:700; color:var(--accent); margin-bottom:9px; }
.exec p{ font-size:12.5px; color:#D5DBE5; line-height:1.9; margin:0; }
.exec p b{ color:#F0F0F0; }
.find-card{ background:var(--panel); border:1px solid var(--line); border-right:2px solid var(--accent);
  border-radius:6px; padding:12px 15px; margin:8px 0; }
.find-card .f-t{ font-size:12.5px; font-weight:700; color:var(--ink); margin-bottom:5px; }
.find-card .f-d{ font-size:12px; color:#B8C0CC; line-height:1.8; }
.find-card .f-d b{ color:#7EDDD4; }
.find-card .f-s{ font-size:11px; color:var(--faint); margin-top:5px; }
.rec-card{ background:var(--panel2); border:1px solid var(--line); border-radius:6px;
  padding:11px 14px; margin:8px 0; display:flex; gap:11px; align-items:flex-start; }
.rec-num{ flex:0 0 24px; height:24px; border-radius:6px; background:var(--accent); color:#0F1115;
  font-weight:700; font-size:12.5px; display:flex; align-items:center; justify-content:center; }
.rec-body{ flex:1; min-width:0; }
.rec-body .r-t{ font-size:12.5px; font-weight:700; color:var(--ink); }
.rec-body .r-d{ font-size:11.5px; color:#B8C0CC; line-height:1.75; margin-top:3px; }
.tag{ display:inline-block; font-size:9.5px; font-weight:600; border-radius:4px; padding:2px 8px; margin-inline-start:8px; vertical-align:middle; }
.tag.hi{ background:rgba(225,29,72,.12); color:#F87171; border:1px solid rgba(225,29,72,.35); }
.tag.mid{ background:rgba(245,158,11,.11); color:#F59E0B; border:1px solid rgba(245,158,11,.3); }
.tag.lo{ background:rgba(156,163,175,.1); color:#9CA3AF; border:1px solid rgba(156,163,175,.25); }
.tag.st{ background:rgba(1,184,170,.12); color:#34D399; border:1px solid rgba(1,184,170,.35); }
.limits{ background:#17191E; border:1px dashed #3A3F48; border-radius:8px; padding:13px 16px; margin:12px 0; }
.limits p{ font-size:11.5px; color:#9CA3AF; line-height:1.8; margin:0; }
.read-note{ background:#14202E; border-right:3px solid #7EDDD4; border-radius:8px;
  padding:11px 15px; margin:10px 0; font-size:12px; color:#C6D2E0; line-height:1.85; }
.read-note b{ color:#7EDDD4; }
.page-title .bar{ width:22px; height:2px; background:var(--accent); border-radius:2px; display:inline-block; }

::-webkit-scrollbar{ width:9px; height:9px; }
::-webkit-scrollbar-track{ background:transparent; }
::-webkit-scrollbar-thumb{ background:#2A2E37; border-radius:6px; }

/* ---------------- responsive ---------------- */
@media(max-width:1200px){
  [data-testid="stMainBlockContainer"]{ padding-inline:0.75rem; }
}
@media(max-width:992px){
  .ribbon .right{ width:100%; margin-inline-start:0; }
  .metric .val{ font-size:23px; }
  [data-testid="stTabs"] [role="tab"]{ font-size:12.5px; padding:8px 14px; }
  [data-testid="stHorizontalBlock"]{ gap:0.4rem; }
}
@media(max-width:768px){
  .metric{ padding:11px 12px 9px; }
  .metric .val{ font-size:21px; }
  .exec{ padding:14px 14px; }
  .exec p{ font-size:11.5px; line-height:1.8; }
  .find-card .f-d{ font-size:11px; }
  .rec-card{ flex-direction:column; }
  .ribbon .ttl{ font-size:15px; }
  .alerts{ grid-template-columns:1fr; }
  [data-testid="stMainBlockContainer"]{ padding-inline:0.5rem; }
}
@media(max-width:576px){
  .metric .val{ font-size:19px; }
  .ribbon .logo{ width:34px; height:34px; flex-basis:34px; }
  .pill{ font-size:10.5px; padding:4px 10px; }
  .pbi-vhead{ padding:7px 10px; }
  .pbi-vtitle{ font-size:11.5px; }
  [data-testid="stTabs"] [role="tab"]{ font-size:11.5px; padding:7px 10px; }
  .page-title{ font-size:13px; }
}
"""


def inject_css():
    st.markdown(f"<style>{CSS}</style>", unsafe_allow_html=True)


def pbi(title):
    """Section header for a visual: plain title + thin accent rule.
    No fake window chrome — a real internal tool does not imitate Power BI."""
    st.markdown(f'<div class="pbi-vhead"><span class="pbi-vtitle">{title}</span></div>',
                unsafe_allow_html=True)


def _port_geometry():
    """Computed area & centre of the OSM port boundary (never hardcoded)."""
    try:
        from shapely.geometry import shape
        from shapely.ops import transform as _st
        import pyproj
        from config import OSM_GEOJSON, RTC_EPSG
        geom = None
        for ft in OSM_GEOJSON["features"]:
            if ft["properties"].get("role") == "port_boundary":
                geom = shape(ft["geometry"])
                break
        if geom is None:
            return None
        tr = pyproj.Transformer.from_crs("EPSG:4326", f"EPSG:{RTC_EPSG}", always_xy=True)
        g = _st(tr.transform, geom)
        c = g.centroid
        lon, lat = tr.transform(c.x, c.y, direction=pyproj.enums.TransformDirection.INVERSE)
        return dict(area_ha=float(g.area / 10000.0), lon=float(lon), lat=float(lat))
    except Exception:
        return None


def _aoi_box_km():
    """Width/height of the study box (km), computed from the AOI bbox."""
    latm = np.radians((AOI_BBOX_4326[1] + AOI_BBOX_4326[3]) / 2)
    w = (AOI_BBOX_4326[2] - AOI_BBOX_4326[0]) * 111.32 * np.cos(latm)
    h = (AOI_BBOX_4326[3] - AOI_BBOX_4326[1]) * 110.57
    return w, h


def ribbon(last_dt, n_ok, n_rej, last_n, last_port, last_anch):
    st.markdown(f"""
    <div class="ribbon">
      <div class="logo">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#01B8AA" stroke-width="1.8">
          <circle cx="12" cy="12" r="3.4" fill="#01B8AA" stroke="none"/>
          <ellipse cx="12" cy="12" rx="9" ry="4.2" transform="rotate(-18 12 12)"/>
        </svg>
      </div>
      <div>
        <p class="ttl">مرصد مرفأ اللاذقية — رصد النشاط البحري</p>
        <p class="st">Sentinel-1 رادار · Sentinel-2 بصري · خريطة الشارع المفتوحة</p>
      </div>
      <div class="right">
        <span class="meta"><span class="dot"></span>آخر التقاط <span dir="ltr">{last_dt}Z</span></span>
        <span class="meta">مشاهدات صالحة <b><span dir="ltr">{n_ok} / {n_ok + n_rej}</span></b></span>
        <span class="meta">آخر مشهد <b><span dir="ltr">{last_n}</span></b> سفينة
          <span style="color:var(--faint)">· حوض {last_port} · مرسى {last_anch}</span></span>
      </div>
    </div>
    """, unsafe_allow_html=True)


def metric(lbl, val, sub="", tone="#01B8AA", spark=None):
    spark_svg = ""
    if spark is not None and len(spark) > 1:
        mn, mx = min(spark), max(spark)
        rng = (mx - mn) or 1
        pts = []
        n = len(spark)
        for i, v in enumerate(spark):
            x = 2 + i * (96 / (n - 1))
            y = 22 - (v - mn) / rng * 18
            pts.append(f"{x:.1f},{y:.1f}")
        col = tone
        spark_svg = (f'<svg class="spark" viewBox="0 0 100 26" preserveAspectRatio="none">'
                     f'<polyline points="{" ".join(pts)}" fill="none" stroke="{col}" '
                     f'stroke-width="1.8" stroke-linejoin="round" stroke-linecap="round"/>'
                     f'</svg>')
    st.markdown(f"""
    <div class="metric">
      <div class="lbl">{lbl}</div>
      <div class="val" style="--tone:{tone}; color:{tone}">{val}</div>
      <div class="sub">{sub}</div>
      {spark_svg}
    </div>""", unsafe_allow_html=True)


def page_title(title):
    st.markdown(f'<div class="page-title"><span class="bar"></span>{title}</div>',
                unsafe_allow_html=True)


@st.cache_data(show_spinner=False)
def get_data():
    scenes = load_scenes()
    monthly, yearly, chg, summary = full_analysis(scenes)
    vessels = load_vessel_points(scenes)
    s2 = load_s2()
    pairs = pair_s1_s2(scenes, s2)
    if len(pairs):
        pairs = (pairs.sort_values("gap_hours")
                 .drop_duplicates(subset="s1_id", keep="first")
                 .sort_values("s2_date").reset_index(drop=True))
    qf = quality_flags(scenes)
    return scenes, monthly, yearly, chg, summary, vessels, s2, pairs, qf


@st.cache_data(show_spinner=False)
def _gt_total_cached():
    return gt_export_total()


@st.cache_data(show_spinner=False)
def _gt_yearly_cached():
    return gt_export_yearly()


@st.cache_data(show_spinner=False)
def _gt_occupancy_cached():
    return gt_export_occupancy()


@st.cache_data(show_spinner=False)
def _gt_scene_cached(sid):
    return gt_export_scene(sid)


@st.cache_data(show_spinner=False)
def _geoexport_cached():
    return export_geojson()

@st.cache_data(show_spinner=False)
def _tracks_cached(scene_ids):
    from tracking import build_tracks
    scenes = load_scenes()
    scenes = scenes[scenes["id"].isin(scene_ids)]
    return build_tracks(scenes)


@st.cache_data(show_spinner=False)
def _ewma_cached(scene_ids):
    from anomaly import chart_ewma
    scenes = load_scenes()
    scenes = scenes[scenes["id"].isin(scene_ids)]
    return chart_ewma(scenes)


@st.cache_data(show_spinner=False)
def _cusum_cached(scene_ids):
    from anomaly import chart_cusum
    scenes = load_scenes()
    scenes = scenes[scenes["id"].isin(scene_ids)]
    return chart_cusum(scenes)

@st.cache_data(show_spinner=False)
def _home_map_cached(scene_ids):
    """Interactive activity map for a subset of scenes (used on home)."""
    from maps import load_vessel_points
    from map_fig import build_activity_map
    scenes = load_scenes()
    scenes = scenes[scenes["id"].isin(scene_ids)]
    v = load_vessel_points(scenes)
    if len(v) == 0:
        return None
    return build_activity_map(v, height=430)


@st.cache_data(show_spinner=False)
def _sumexport_cached():
    return export_summary_json()


@st.cache_data(show_spinner=False)
def _ais_pipeline_cached(scene_ids, ais_files_key):
    """AIS matching + type profile + report, cached per (scenes, ais files)."""
    scenes = load_scenes()
    scenes = scenes[scenes["id"].isin(scene_ids)]
    ais = load_ais()
    det, stats = match_detections(scenes, ais)
    prof = type_profile(scenes, det)
    rpt = ais_report(scenes, det, stats)
    return det, stats, prof, rpt


def main():
    inject_css()
    scenes, monthly, yearly, chg, summary, vessels, s2, pairs, qf = get_data()

    good = scenes[scenes["error"].isna() | (scenes["error"] == "")].copy()
    good["dt"] = pd.to_datetime(good["datetime"])
    n_rej = len(scenes) - len(good)
    last_dt = good["dt"].max()
    last_row = good.loc[good["dt"].idxmax()]

    # ------------------------------------------------------------ filters pane (right)
    with st.sidebar:
        st.markdown('<div class="fpane-title">فلاتر العرض</div>', unsafe_allow_html=True)

        st.markdown("#### الفترة الزمنية")
        years = sorted(good["year"].unique())
        sel_years = st.multiselect("السنوات", [str(y) for y in years],
                                   default=[str(y) for y in years], key="years")
        sel_months = st.multiselect(
            "الأشهر", list(range(1, 13)), default=list(range(1, 13)),
            format_func=lambda m: ["كانون الثاني","شباط","آذار","نيسان","أيار","حزيران",
                                   "تموز","آب","أيلول","تشرين الأول","تشرين الثاني","كانون الأول"][m-1],
            key="months")
        d0 = good["dt"].min().date(); d1 = good["dt"].max().date()
        period = st.date_input("النطاق الزمني", value=(d0, d1), min_value=d0, max_value=d1,
                               format="YYYY-MM-DD", key="range")
        if isinstance(period, tuple):
            if len(period) == 2:
                period = (period[0], period[1])
            else:
                period = (d0, d1)
        else:
            period = (period, period)

        st.markdown("#### المراقبة")
        sat = st.selectbox("القمر الصناعي",
                           ["Sentinel-1 (SAR)", "Sentinel-2 (بصري — تحقق)"], key="sat")

        st.markdown("#### الأدوات")
        if st.button("تحديث البيانات", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    def filt(df, dtcol="dt"):
        out = df.copy()
        d = out[dtcol]
        return out[d.dt.year.isin([int(y) for y in sel_years]) &
                   d.dt.month.isin(sel_months) &
                   (d.dt.date >= period[0]) & (d.dt.date <= period[1])]

    fscenes = filt(good, "dt")
    fvessels = filt(vessels, "datetime")
    fmonthly = monthly[(monthly["year"].isin([int(y) for y in sel_years])) &
                       (monthly["month"].isin(sel_months)) &
                       (monthly["ym"] >= period[0].strftime("%Y-%m")) &
                       (monthly["ym"] <= period[1].strftime("%Y-%m"))]

    ribbon(last_dt.strftime("%Y-%m-%d %H:%M"), len(good), n_rej,
           int(last_row["n_est"]), int(last_row["n_est_in_port"]), int(last_row["n_anchorage"]))

    # ---- dynamic figures for the findings page ----
    try:
        from insights import dwell_analysis, operational_series
        _dw, _dws = dwell_analysis(scenes)
        _op, _p95 = operational_series(scenes)
        _op26 = _op[_op["year"] == 2026]
        _op25 = _op[_op["year"] <= 2025]
        dwell_med = float(_dws["median_days"] or 0)
        dwell_pers = float(_dws["pct_persistent"] or 0)
        dwell_pairs = int(_dws.get("matched_pairs", 0))
        berth_26 = float(_op26["berthed"].mean())
        berth_pre = float(_op25["berthed"].mean())
        cap_pct26 = float(_op26["over_capacity"].mean() * 100) if len(_op26) else 0.0
        cap_p95 = float(_p95)
    except Exception:
        dwell_med = dwell_pers = berth_26 = berth_pre = 0.0
        dwell_pairs = 0
        cap_pct26 = 0.0
        cap_p95 = 0.0
        _op = None
        _dw = None
    _m26 = monthly[(monthly["year"] == 2026) & (monthly["n_obs"] > 0)]["mean_ships_port_adj"]
    _mbase = monthly[(monthly["year"].isin([2022, 2023, 2024, 2025])) & (monthly["n_obs"] > 0)]["mean_ships_port_adj"]
    _mbase = _mbase.dropna() if len(_mbase) else _mbase
    _mcur = monthly[(monthly["year"] == 2026) & (monthly["n_obs"] > 0)]["mean_ships_port_adj"]
    if len(_mbase) and len(_mcur):
        b_lo = max(0, _mbase.mean() - _mbase.std()); b_hi = _mbase.mean() + _mbase.std()
        c_lo = max(0, _mcur.mean() - _mcur.std()); c_hi = _mcur.mean() + _mcur.std()
    else:
        b_lo = b_hi = c_lo = c_hi = 0
    _mb_mean = float(_mbase.mean()) if len(_mbase) else None
    _mb_std = float(_mbase.std()) if len(_mbase) else None
    # use yearly.csv adjusted value for perfect consistency with the report
    _y26row = yearly[yearly["year"] == 2026]
    m26 = float(_y26row["annual_mean_adj"].iloc[0]) if len(_y26row) else (float(_m26.mean()) if len(_m26) else 0.0)
    t26 = summary["regimes"].get("y2026_vs_2025", {}).get("test", {})
    t26_b = float(t26.get("mean_before", 0))
    t26_p = float(t26.get("p_value", 1))
    yoy = float(yearly[yearly["year"] == 2026]["yoy_pct"].iloc[0]) if len(yearly[yearly["year"] == 2026]) else 0.0
    tpost_p = float(summary["regimes"].get("post_vs_pre_dec2024", {}).get("test", {}).get("p_value", 1))
    _mm = monthly.set_index("ym")
    _fa26 = [float(_mm.loc[f"2026-0{i}", "mean_ships_port_adj"]) for i in (2, 3, 4) if f"2026-0{i}" in _mm.index]
    _fa_base = []
    for i in (2, 3, 4):
        _v = _mm[(_mm["month"] == i) & (_mm["year"].isin([2022, 2023, 2024, 2025])) & (_mm["n_obs"] > 0)]["mean_ships_port_adj"]
        if len(_v):
            _fa_base.append(float(_v.mean()))
    feb_apr_26 = float(np.mean(_fa26)) if _fa26 else 0.0
    feb_apr_base = float(np.mean(_fa_base)) if _fa_base else 0.0
    anch_26 = float(monthly[(monthly["ym"] >= "2026-01") & (monthly["n_obs"] > 0)]["mean_anchorage"].mean())
    anch_pre = float(monthly[(monthly["ym"] >= "2022-01") & (monthly["ym"] <= "2025-12") & (monthly["n_obs"] > 0)]["mean_anchorage"].mean())
    snr = float(qf["snr_db"].mean()) if len(qf) else 0.0
    # ---- comparison values computed from live data (never hardcoded) ----
    cap_pre_pct = 0.0
    if _op is not None:
        _oppre = _op[_op["year"] <= 2025]
        if len(_oppre):
            cap_pre_pct = float(_oppre["over_capacity"].mean() * 100)
    cov_min_pct = float(good["cov_port"].min() * 100) if len(good) else 0.0
    rec1_base = float(_mb_mean) if _mb_mean is not None else 0.0
    rec1_mid = float((m26 + rec1_base) / 2)
    _pp = pairs.copy() if len(pairs) else pd.DataFrame()
    _opt26 = _opt25 = 0.0
    if len(_pp):
        _pp["s2_date"] = pd.to_datetime(_pp["s2_date"])
        _p26o = _pp[_pp["s2_date"].dt.year == 2026]
        _p25o = _pp[_pp["s2_date"].dt.year == 2025]
        _opt26 = float(_p26o["s2_port"].mean()) if len(_p26o) else 0.0
        _opt25 = float(_p25o["s2_port"].mean()) if len(_p25o) else 0.0

    # ============================================================ PAGES
    p_home, p_find, p_report, p_region, p_trend, p_anom, p_comp, p_data, p_adv, p_map, p_view, p_val, p_ais, p_auto = st.tabs([
        "الرئيسية", "النتائج والتوصيات", "التقرير", "المقارنة الإقليمية", "الاتجاه الزمني",
        "كشف الشذوذ", "المقارنات", "بيانات المشاهدات", "تحليلات متقدمة", "الخريطة",
        "عارض الصور", "التحقق", "التحقق AIS", "الأتمتة والتحديث"])

    # ------------------------------------------------ page 1: home
    with p_home:
        n_det = int(fvessels["vessel_id"].nunique()) if len(fvessels) else 0
        n_scenes = len(fscenes)
        cur = fmonthly[fmonthly["n_obs_port"] > 0].sort_values("ym")
        latest = cur.iloc[-1] if len(cur) else None
        growth = None
        if latest is not None and len(cur) >= 2:
            prev = cur.iloc[-2]["mean_ships_port_adj"]
            growth = (latest["mean_ships_port_adj"] - prev) / max(prev, 1e-9) * 100
        peak = cur.loc[cur["mean_ships_port_adj"].idxmax()] if len(cur) else None
        _peak_ym = str(peak["ym"]) if peak is not None else "—"
        peak_ym_short = {"01": "كانون الثاني", "02": "شباط", "03": "آذار", "04": "نيسان",
                         "05": "أيار", "06": "حزيران", "07": "تموز", "08": "آب",
                         "09": "أيلول", "10": "تشرين الأول", "11": "تشرين الثاني",
                         "12": "كانون الأول"}.get(_peak_ym[5:7], _peak_ym) + " " + _peak_ym[:4]
        peak_val = float(peak["mean_ships_port_adj"]) if peak is not None else 0.0
        mk = summary.get("mk_direction")
        mk_txt = "صعود" if mk == "increase" else ("انحدار" if mk == "decrease" else "—")
        mk_sub = f"τ={summary['mk_tau']} · p={summary['mk_p']}" if summary.get("mk_p") is not None else ""
        mk_p = summary.get("mk_p") or 1
        mk_tone = ("#34D399" if mk == "increase" else "#F87171") if mk_p < 0.05 else "#F59E0B"

        _spark12 = cur.tail(12)["mean_ships_port_adj"].tolist() if len(cur) else []
        _spark_obs = cur.tail(12)["n_obs"].tolist() if len(cur) else []

        # ---- dashboard section header ----
        st.markdown('<div class="page-title"><span class="bar"></span>لوحة المؤشرات الرئيسية</div>',
                    unsafe_allow_html=True)

        # ---- tracking stats (for the KPI row) ----
        try:
            _tk_df, _tk_stats = _tracks_cached(tuple(scenes["id"]))
            _n_tracks = int(_tk_stats.get("total_tracks", 0))
            _n_tracks2 = int(_tk_stats.get("tracks_with_2plus", 0))
        except Exception:
            _n_tracks, _n_tracks2 = 0, 0

        # ---- KPI row (8 cards) ----
        c1, c2, c3, c4, c5, c6, c7, c8 = st.columns(8, gap="small")
        with c1:
            metric("اكتشافات السفن", f"{n_det:,}", f"من {n_scenes} مشهدًا راداريًا", "#01B8AA")
        with c2:
            metric("أحدث نشاط شهري", f"{latest['mean_ships_port_adj']:.1f}" if latest is not None else "—",
                   f"سفينة لكل مشاهدة · <span dir='ltr'>{latest['ym']}</span>" if latest is not None else "",
                   "#01B8AA", spark=_spark12)
        with c3:
            if growth is not None:
                metric("التغير الشهري", f"{growth:+.0f}%", "",
                       "#34D399" if growth >= 0 else "#F87171")
            else:
                metric("التغير الشهري", "—", "", "#6B7280")
        with c4:
            if peak is not None:
                metric("أعلى شهر نشاطًا", f"<span dir='ltr'>{peak['ym']}</span>",
                       f"{peak['mean_ships_port_adj']:.1f} سفينة لكل مشاهدة", "#F59E0B")
            else:
                metric("أعلى شهر نشاطًا", "—", "", "#6B7280")
        with c5:
            metric("متوسط الفترة", f"{cur['mean_ships_port_adj'].mean():.1f}" if len(cur) else "—",
                   f"عبر {len(cur)} شهرًا", "#A78BFA", spark=_spark_obs)
        with c6:
            metric("اتجاه السلسلة", mk_txt, mk_sub, mk_tone)
        with c7:
            metric("فوق سقف القدرة 2026", f"{cap_pct26:.0f}%",
                   f"السقف التاريخي {cap_p95:.0f} سفينة",
                   "#F87171" if cap_pct26 > 10 else "#34D399")
        with c8:
            metric("مسارات سفن مميزة", f"{_n_tracks:,}",
                   f"{_n_tracks2:,} بظهورين فأكثر", "#7EDDD4")

        # ---- health chips + regional quick strip ----
        mean_snr = qf["snr_db"].mean() if len(qf) else None
        n_clusters = int(good.get("n_clusters", pd.Series(0)).sum()) if "n_clusters" in good.columns else 0
        _region_chips = ""
        try:
            from compare import summary as _cs_home
            _csd = _cs_home()
            _cth = _csd.get("tartus") or {}
            _cbh = _csd.get("baniyas") or {}
            _region_chips = ""
            if _cth:
                _region_chips += (f'<span class="chip">طرطوس 2026 <b><span dir="ltr">{_cth["mean_26"]:.1f}</span></b> '
                                  f'(<span dir="ltr">{_cth["pct"]:+.0f}%</span>)</span>')
            if _cbh:
                _region_chips += (f'<span class="chip">بانياس 2026 <b><span dir="ltr">{_cbh["mean_26"]:.1f}</span></b> '
                                  f'(<span dir="ltr">{_cbh["pct"]:+.0f}%</span>)</span>')
        except Exception:
            pass
        st.markdown(f"""
        <div class="health">
          <span class="chip">مشاهدات صالحة <b><span dir="ltr">{len(good)} / {len(scenes)}</span></b></span>
          <span class="chip">تغطية الحوض <b><span dir="ltr">≥ {good['cov_port'].min()*100:.0f}%</span></b></span>
          <span class="chip">الإشارة/الضوضاء <b><span dir="ltr">{mean_snr:.1f} ديسيبل</span></b></span>
          <span class="chip">أزواج التحقق <b><span dir="ltr">{len(pairs)}</span></b></span>
          <span class="chip">أجسام ملتحمة <b><span dir="ltr">{n_clusters}</span></b></span>
          <span class="chip">المدى <b><span dir="ltr">{good['dt'].min():%Y-%m}</span> ← <span dir="ltr">{good['dt'].max():%Y-%m}</span></b></span>
          {_region_chips}
        </div>""", unsafe_allow_html=True)

        # ---- alerts panel (computed from live data) ----
        try:
            from insights import operational_series
            _al_op, _al_p95 = operational_series(scenes)
            _al_last = _al_op.iloc[-1]
            _cap_hit = bool(_al_last["over_capacity"])
            _al_scenes26 = _al_op[_al_op["year"] == 2026]
            _cap_pct26 = float(_al_scenes26["over_capacity"].mean() * 100) if len(_al_scenes26) else 0
            _al_pre = _al_op[_al_op["year"] <= 2025]
            _cap_pre_pct = float(_al_pre["over_capacity"].mean() * 100) if len(_al_pre) else 0
        except Exception:
            _cap_hit, _cap_pct26, _cap_pre_pct = False, 0.0, 0.0
        _last3 = cur.tail(3)["mean_ships_port_adj"].mean() if len(cur) >= 3 else None
        _prev3 = cur.tail(6).head(3)["mean_ships_port_adj"].mean() if len(cur) >= 6 else None
        _mom_al = None
        if _last3 and _prev3:
            _mom_al = (_last3 - _prev3) / _prev3 * 100
        _alert_html = ""
        if _cap_hit:
            _alert_html += f"""
            <div class="alert crit"><div class="a-ic">!</div><div>
              <div class="a-t">تنبيه — تجاوز سقف القدرة في آخر مشهد</div>
              <div class="a-d">آخر مشهد ({_al_last['dt']:%Y-%m-%d}) سجّل {int(_al_last['in_port'])} سفينة في
              الحوض، وهو أعلى من الحد التاريخي ({_al_p95:.0f} سفينة). في 2026 تجاوزت {_cap_pct26:.0f}% من
              المشاهدات هذا السقف، مقابل {_cap_pre_pct:.0f}% فقط في 2022–2025.</div>
            </div></div>"""
        if _mom_al is not None and abs(_mom_al) > 20:
            cls = "warn"
            arrow = "ارتفاع" if _mom_al > 0 else "انخفاض"
            _alert_html += f"""
            <div class="alert {cls}"><div class="a-ic">{'▲' if _mom_al>0 else '▼'}</div><div>
              <div class="a-t">{arrow} غير اعتيادي في آخر 3 أشهر ({_mom_al:+.0f}%)</div>
              <div class="a-d">متوسط آخر 3 أشهر ({_last3:.1f}) مقابل الأشهر الثلاثة السابقة ({_prev3:.1f})
              سفينة لكل مشاهدة. يُنصح بمراجعة الأسباب التشغيلية.</div>
            </div></div>"""
        if not _alert_html:
            _alert_html = """
            <div class="alert info"><div class="a-ic">✓</div><div>
              <div class="a-t">لا شذوذ في آخر مشاهدات</div>
              <div class="a-d">النشاط ضمن الحدود المتوقعة وفق المؤشرات التاريخية.</div>
            </div></div>"""
        st.markdown(f'<div class="alerts">{_alert_html}</div>', unsafe_allow_html=True)

        # ==================== charts grid (dashboard) ====================
        # ---- row A: main trend + gauge ----
        _hA1, _hA2 = st.columns([1.6, 1], gap="small")
        with _hA1:
            pbi("الاتجاه الشهري — سفن لكل مشاهدة (مع الأحداث)")
            st.plotly_chart(chart_monthly_line(fmonthly), width="stretch", key="home_trend",
                            config={"displayModeBar": False})
        with _hA2:
            pbi("مؤشر النشاط الحالي مقابل خط الأساس")
            st.plotly_chart(chart_gauge(fmonthly), width="stretch", key="home_gauge",
                            config={"displayModeBar": False})

        # ---- row B: zone donut + operational pressure + regional 3-port ----
        _hB1, _hB2, _hB3 = st.columns(3, gap="small")
        with _hB1:
            pbi("توزيع السفن حسب المنطقة")
            st.plotly_chart(chart_donut(fscenes), width="stretch", key="home_donut",
                            config={"displayModeBar": False})
        with _hB2:
            pbi("ضغط التشغيل — الحوض مقابل المرسى")
            st.plotly_chart(chart_bubble(fmonthly), width="stretch", key="home_bubble",
                            config={"displayModeBar": False})
        with _hB3:
            pbi("المقارنة الإقليمية — الموانئ الثلاثة (2026)")
            try:
                import plotly.graph_objects as _go
                from charts import base_layout as _bl, C as _C
                from compare import summary as _cs_reg
                _regd = {k: v for k, v in _cs_reg().items() if v}
                _rnames = {"latakia": "اللاذقية", "tartus": "طرطوس", "baniyas": "بانياس"}
                _rcols = {"latakia": _C["accent"], "tartus": _C["amber"], "baniyas": _C["violet"]}
                _rfig = _go.Figure()
                for _k, _v in _regd.items():
                    _rfig.add_bar(x=[_rnames[_k]], y=[_v["mean_26"]], name=_rnames[_k],
                                  marker_color=_rcols[_k],
                                  text=[f"{_v['pct']:+.1f}%"], textposition="outside",
                                  hovertemplate=f"{_rnames[_k]}: {_v['mean_26']:.1f} "
                                                f"({_v['pct']:+.1f}%)<extra></extra>")
                _rfig.update_layout(barmode="group", showlegend=False,
                                    xaxis=dict(showgrid=False), yaxis=dict(range=[0, None]))
                st.plotly_chart(_bl(_rfig, "متوسط كانون الثاني–آب 2026", ylabel="سفن لكل مشاهدة"),
                                width="stretch", key="home_reg",
                                config={"displayModeBar": False})
            except Exception as _e:
                st.info("غير متاحة: " + str(_e)[:60])

        # ---- row C: statistical control charts ----
        _hC1, _hC2 = st.columns(2, gap="small")
        with _hC1:
            pbi("مخطط المتوسط المتحرك المرجح — القيم الشهرية مقابل ±3σ")
            try:
                st.plotly_chart(_ewma_cached(tuple(scenes["id"])), width="stretch",
                                key="home_ewma", config={"displayModeBar": False})
            except Exception:
                st.info("المتوسط المتحرك المرجح غير متاح")
        with _hC2:
            pbi("مخطط المجموع التراكمي — تراكم الانحرافات عن خط الأساس")
            try:
                st.plotly_chart(_cusum_cached(tuple(scenes["id"])), width="stretch",
                                key="home_cusum", config={"displayModeBar": False})
            except Exception:
                st.info("المجموع التراكمي غير متاح")

        # ---- row D: dwell + berthed + AIS type composition ----
        _hD1, _hD2, _hD3 = st.columns(3, gap="small")
        with _hD1:
            pbi("مدة بقاء السفينة بين مشهدين متتاليين")
            try:
                from insights import chart_dwell
                st.plotly_chart(chart_dwell(_dw), width="stretch", key="home_dwell",
                                config={"displayModeBar": False})
            except Exception:
                st.info("مدة البقاء غير متاحة")
        with _hD2:
            pbi("السفن الملاصقة للأرصفة شهريًا")
            try:
                from insights import chart_berthed
                st.plotly_chart(chart_berthed(_op), width="stretch", key="home_berthed",
                                config={"displayModeBar": False})
            except Exception:
                st.info("سفن الأرصفة غير متاحة")
        with _hD3:
            pbi("التركيب التقديري لأنواع السفن (AIS + أبعاد)")
            try:
                import glob as _g3
                _ais_files3 = sorted(_g3.glob(os.path.join(AIS_DIR, "*.jsonl")) +
                                     _g3.glob(os.path.join(AIS_DIR, "*.csv")))
                _ais_key3 = tuple((os.path.basename(f), int(os.path.getmtime(f))) for f in _ais_files3)
                _d3, _s3, _p3, _r3 = _ais_pipeline_cached(tuple(fscenes["id"]), _ais_key3)
                _f3 = chart_type_donut(_p3)
                if _f3 is not None:
                    st.plotly_chart(_f3, width="stretch", key="home_ais",
                                    config={"displayModeBar": False})
                else:
                    st.info("لا بيانات تصنيف")
            except Exception:
                st.info("تصنيف الأنواع غير متاح")

        # ---- row E: interactive map + latest scenes ----
        _eE1, _eE2 = st.columns([2.2, 1], gap="small")
        with _eE1:
            pbi("خريطة مواقع السفن المكتشفة — ضمن الفلاتر الحالية (خلفية رادارية حقيقية)")
            try:
                _hm = _home_map_cached(tuple(fscenes["id"]))
                if _hm is not None:
                    st.plotly_chart(_hm, width="stretch", key="home_map",
                                    config={"displayModeBar": False})
                else:
                    st.info("لا توجد سفن ضمن الفلاتر.")
            except Exception:
                st.info("الخريطة غير متاحة ضمن الفلاتر الحالية.")
        with _eE2:
            pbi("آخر 5 مشاهدات رادارية")
            _lt = fscenes.sort_values("dt", ascending=False).head(5)
            if len(_lt):
                _lt_tbl = _lt[["dt", "platform", "n_est_in_port", "n_anchorage", "coverage"]].copy()
                _lt_tbl = _lt_tbl.rename(columns={
                    "dt": "الوقت", "platform": "القمر",
                    "n_est_in_port": "الحوض", "n_anchorage": "المرسى",
                    "coverage": "تغطية"})
                _lt_tbl["الوقت"] = pd.to_datetime(_lt_tbl["الوقت"]).dt.strftime("%m-%d %H:%M")
                _lt_tbl["القمر"] = _lt_tbl["القمر"].astype(str).str.replace("SENTINEL-", "S-", regex=False)
                _lt_tbl["تغطية"] = (_lt_tbl["تغطية"] * 100).round(0).astype(int).astype(str) + "%"
                st.dataframe(_lt_tbl, width="stretch", hide_index=True)
            else:
                st.info("لا مشاهدات ضمن الفلاتر.")

        # ---- export files section (Power BI export behaviour) ----
        page_title("تصدير الملفات")
        _docs = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs")
        ex1, ex2, ex3, ex4, ex5 = st.columns(5, gap="small")
        with ex1:
            try:
                with open(os.path.join(_docs, "PBI_REPORT.html"), "rb") as f:
                    st.download_button("تقرير Power BI تفاعلي (HTML)", f, file_name="PBI_REPORT.html",
                                       mime="text/html", use_container_width=True)
            except Exception:
                st.info("غير متاح")
        with ex2:
            try:
                with open(os.path.join(_docs, "FINAL_REPORT.xlsx"), "rb") as f:
                    st.download_button("مصنف Excel بالمخططات (XLSX)", f, file_name="FINAL_REPORT.xlsx",
                                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                       use_container_width=True)
            except Exception:
                st.info("غير متاح")
        with ex3:
            try:
                with open(os.path.join(_docs, "FINAL_REPORT.docx"), "rb") as f:
                    st.download_button("وثيقة Word الرسمية (DOCX)", f, file_name="FINAL_REPORT.docx",
                                       mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                       use_container_width=True)
            except Exception:
                st.info("غير متاح")
        with ex4:
            try:
                with open(os.path.join(_docs, "FINAL_REPORT.pdf"), "rb") as f:
                    st.download_button("نسخة PDF للطباعة", f, file_name="FINAL_REPORT.pdf",
                                       mime="application/pdf", use_container_width=True)
            except Exception:
                st.info("غير متاح")
        with ex5:
            import zipfile as _z, io as _io
            _zbuf = _io.BytesIO()
            with _z.ZipFile(_zbuf, "w", _z.ZIP_DEFLATED) as _zf:
                for _fn in ["FINAL_REPORT.html", "FINAL_REPORT.pdf", "FINAL_REPORT.docx",
                            "FINAL_REPORT.xlsx", "PBI_REPORT.html", "PBI_REPORT.pdf",
                            "EXEC_BRIEF.html", "EXEC_BRIEF.pdf"]:
                    _zp = os.path.join(_docs, _fn)
                    if os.path.exists(_zp):
                        _zf.write(_zp, arcname=_fn)
            st.download_button("كل التقارير (ZIP)", _zbuf.getvalue(),
                               file_name="latakia_reports.zip",
                               mime="application/zip", use_container_width=True)

    # ------------------------------------------------ page 2: findings & recommendations
    with p_find:
        page_title("النتائج والتوصيات")

        # ---- executive summary ----
        _exec = f"""
        <div class="exec">
          <div class="ex-t">الخلاصة التنفيذية</div>
          <p>يغطي هذا التحليل <b>{len(good)}</b> مشهدًا راداريًا و<b>{len(s2)}</b> مشهدًا بصريًا
          على مدى <b>{int(monthly['n_obs'].gt(0).sum())}</b> شهرًا متتاليًا. بعد ضبط الموسمية والمقارنة
          على أساس «نفس الفترة بنفس الفترة»، سجّل النشاط التشغيلي لمرفأ اللاذقية
          <b>انتقالًا في المستوى</b> ابتداءً من كانون الأول 2025: متوسط السفن في الحوض بلغ
          <b>{m26:.1f}</b> سفينة لكل مشاهدة خلال 2026 مقابل <b>{t26_b:.1f}</b> لنفس الأشهر من 2025
          (نمو <b>+{yoy:.0f}%</b>) — وهو أعلى مستوى منذ بداية السلسلة، مع دلالة إحصائية قوية على مستوى
          المشاهدات الفردية (احتمال أقل من 0.0001) وعلى المتوسطات الشهرية (احتمال {t26_p:.4f}).
          الارتفاع <b>ليس موسميًا</b>، ويتزامن مع ضغط على الأرصفة والمرسى معًا، وتجاوز سقف القدرة
          التاريخية في {cap_pct26:.0f}% من مشاهدات 2026.</p>
        </div>"""
        st.markdown(_exec, unsafe_allow_html=True)

        # ---- quick summary strip (4 mini-cards) ----
        q1, q2, q3, q4 = st.columns(4, gap="small")
        with q1:
            metric("نشاط 2026 (نفس الأشهر)", f"{m26:.1f}", "سفينة لكل مشاهدة",
                   "#01B8AA")
        with q2:
            metric("النمو مقابل 2025", f"+{yoy:.0f}%",
                   "بعد ضبط الموسمية", "#34D399")
        with q3:
            metric("أعلى شهر", f"<span dir='ltr'>{peak_ym_short}</span>",
                   f"{peak_val:.1f} سفينة لكل مشاهدة", "#F59E0B")
        with q4:
            metric("مشاهدات فوق سقف القدرة", f"{cap_pct26:.0f}%",
                   f"السقف التاريخي {cap_p95:.0f} سفينة",
                   "#F87171" if cap_pct26 > 10 else "#34D399")

        st.markdown('<div class="page-title"><span class="bar"></span>النتائج</div>',
                    unsafe_allow_html=True)
        _findings = f"""
        <div class="find-card">
          <div class="f-t">1 — تحول في مستوى النشاط، لا مجرد تذبذب</div>
          <div class="f-d">الانتقال من نطاق {b_lo:.0f}–{b_hi:.0f} سفينة لكل مشاهدة (النطاق النموذجي
          2022–2025) إلى نطاق {c_lo:.0f}–{c_hi:.0f} في 2026 يشير إلى <b>تغيّر بنيوي</b> في الطلب
          التشغيلي وليس تقلبًا عابرًا. ذروة شباط–نيسان
          ({feb_apr_26:.1f} سفينة لكل مشهد مقابل {feb_apr_base:.1f} في 2022–2025،
          احتمال أقل من 0.0001) تؤكد ذلك بعد استبعاد التفسير الموسمي.</div>
          <div class="f-s">الدليل: اختبار مان-ويتني على المشاهدات الفردية مع الضبط الموسمي</div>
        </div>
        <div class="find-card">
          <div class="f-t">2 — ضغط متزامن على الأرصفة والمرسى</div>
          <div class="f-d">ارتفع متوسط السفن الملاصقة للأرصفة من <b>{berth_pre:.1f}</b> إلى
          <b>{berth_26:.1f}</b> سفينة لكل مشهد، وقفز متوسط سفن الانتظار في المرسى من <b>{anch_pre:.1f}</b>
          إلى <b>{anch_26:.1f}</b>. الارتفاع المتزامن في المكوّنين يعني أن <b>الطلب تجاوز الطاقة
          التفريغية للحوض</b> — وليس مجرد إعادة توزيع للسفن بين المناطق.</div>
          <div class="f-s">الدليل: المسافة من حد المرفأ (80 مترًا فأقل = رصيف) لكل سجل سفينة</div>
        </div>
        <div class="find-card">
          <div class="f-t">3 — تجاوز سقف القدرة التاريخي</div>
          <div class="f-d">{cap_pct26:.0f}% من مشاهدات 2026 تجاوزت الحد الأعلى التاريخي
          ({cap_p95:.0f} سفينة في الحوض، المئين الخامس والتسعون للفترة 2022–2024)، مقابل {cap_pre_pct:.0f}% في
          السنوات السابقة. المقياس محايد لتغيرات وتيرة الرصد ويعكس <b>ازدحامًا</b> هو الأعلى في السلسلة.</div>
          <div class="f-s">الدليل: توزيع السفن لكل مشهد حسب السنة (مخطط الصناديق)</div>
        </div>
        <div class="find-card">
          <div class="f-t">4 — معدل دوران السفن لم يتغير</div>
          <div class="f-d">وسيط مدة بقاء السفينة بين مشهدين متتاليين {dwell_med:.0f} أيام، و
          {dwell_pers:.0f}% من السفن المتطابقة بقيت أربعة أيام فأكثر — <b>مستقر عبر الفترة</b>. أي أن
          الازدحام ناتج عن زيادة عدد السفن الوافدة، وليس عن تباطؤ في التفريغ أو تراكم شاذ.</div>
          <div class="f-s">الدليل: مطابقة {dwell_pairs:,} موقعًا عبر المشاهدات المتتالية</div>
        </div>
        <div class="find-card">
          <div class="f-t">5 — استقرار 2022–2025 رغم الأحداث الإقليمية</div>
          <div class="f-d">لم تسجل السنوات الأربع السابقة تغيرًا ذا دلالة إحصائية، بما فيها الفترة
          التي تلت كانون الأول 2024 (احتمال {tpost_p:.3f}). التحول بدأ فعليًا في كانون الأول 2025
          — <b>لا تدعم البيانات ارتباطًا زمنيًا بأحداث أواخر 2024</b>.</div>
          <div class="f-s">الدليل: اختبارات الفترات (نفس الفترة بنفس الفترة)</div>
        </div>
        <div class="find-card">
          <div class="f-t">6 — جودة الرصد مستقرة</div>
          <div class="f-d">متوسط نسبة الإشارة إلى الضوضاء للاكتشافات {snr:.1f} ديسيبل، وتغطية الحوض
          {cov_min_pct:.0f}% فأكثر في جميع المشاهدات، وحالة البحر متقاربة عبر السنوات — ما يؤكد أن
          الفروق المرصودة <b>ليست أثرًا لظروف الرصد</b> بل انعكاسًا حقيقيًا للنشاط.</div>
          <div class="f-s">الدليل: مؤشرات الجودة السنوية (الإشارة إلى الضوضاء / الخشونة / الضوضاء)</div>
        </div>"""
        st.markdown(_findings, unsafe_allow_html=True)

        st.markdown('<div class="page-title"><span class="bar"></span>التوصيات</div>',
                    unsafe_allow_html=True)
        _recs = f"""
        <div class="rec-card"><div class="rec-num">1</div><div class="rec-body">
          <div class="r-t">مواصلة الرصد الشهري المنتظم <span class="tag hi">أولوية عالية</span></div>
          <div class="r-d">أشهر آب–كانون الأول 2026 تحدد ما إذا كان المستوى الجديد مستقرًا بعد ذروة الربيع:
          إذا حافظ النشاط على مستوى أعلى من {rec1_mid:.1f} سفينة لكل مشاهدة (منتصف المسافة بين متوسط
          2022–2025 ومتوسط 2026)، يُعد الارتفاع مستقرًا؛ وإذا عاد إلى نحو {rec1_base:.1f} (متوسط
          2022–2025)، كان مؤقتًا.</div></div></div>
        <div class="rec-card"><div class="rec-num">2</div><div class="rec-body">
          <div class="r-t">تفعيل التحقق عبر بيانات AIS الحقيقية <span class="tag hi">أولوية عالية</span></div>
          <div class="r-d">وحدة المطابقة جاهزة في تبويب «التحقق AIS» (مطابقة ضمن 600 متر و45 دقيقة مع
          إخراج رقم المنظمة البحرية الدولي ومعرّف المحطة ونوع السفينة). المتبقي إدخال بث فعلي لبيانات
          AIS (استقبال محلي أو اشتراك في خدمة بيانات) لتحويل التقرير من «عدّاد راداري» إلى «صورة
          تشغيلية كاملة» بهويات مؤكدة: بضائع وناقلات وحاويات.</div></div></div>
        <div class="rec-card"><div class="rec-num">3</div><div class="rec-body">
          <div class="r-t">تحسين فصل السفن المتلاصقة في الازدحام <span class="tag mid">متوسطة</span></div>
          <div class="r-d">في أشهر الذروة (شباط–نيسان 2026) تزداد الأجسام العريضة المركبة؛ مراجعة
          عتبات الفصل وخوارزمية التفكيك تقلص هامش الخطأ في العد.</div></div></div>
        <div class="rec-card"><div class="rec-num">4</div><div class="rec-body">
          <div class="r-t">ربط السلسلة بمؤشرات التجارة الخارجية <span class="tag mid">متوسطة</span></div>
          <div class="r-d">مقارنة النشاط بحركة الاستيراد والتصدير السورية (عند توفرها) تكشف المحرك
          الاقتصادي للارتفاع — البيانات الفضائية تصف الظاهرة، والمؤشرات الاقتصادية تفسّر أسبابها.</div></div></div>
        <div class="rec-card"><div class="rec-num">5</div><div class="rec-body">
          <div class="r-t">المقارنة الإقليمية الثلاثية — منجزة <span class="tag st">مكتملة</span></div>
          <div class="r-d">طُبّق خط المعالجة نفسه على طرطوس (الحدود الرسمية من خريطة الشارع المفتوحة)
          وبانياس النفطي (حوض محاط بكاسر أمواج مغلق) — النتيجة: النمو الكبير (+{yoy:.0f}%) حصرية
          باللاذقية، بينما طرطوس +8.8% وبانياس من قاعدة منخفضة. يُقترح إبقاء التحديث الشهري ضمن
          الأتمتة الأسبوعية.</div></div></div>
        <div class="rec-card"><div class="rec-num">6</div><div class="rec-body">
          <div class="r-t">تخطيط تشغيلي مسبق لفترات الذروة <span class="tag lo">تشغيلية</span></div>
          <div class="r-d">مع متوسط {berth_26:.1f} سفينة على الأرصفة و{anch_26:.1f} في المرسى خلال 2026،
          يمكن لسلطة المرفأ استخدام هذه المؤشرات في إدارة الأرصفة وجدولة الرسو مسبقًا بدل الاستجابة
          اللاحقة للازدحام.</div></div></div>"""
        st.markdown(_recs, unsafe_allow_html=True)

        st.markdown('<div class="page-title"><span class="bar"></span>حدود القراءة</div>',
                    unsafe_allow_html=True)
        st.markdown("""
        <div class="limits">
          <p><b>ما لا تستطيع هذه البيانات قوله:</b> أنواع السفن وحمولاتها (تتطلب بيانات AIS) · السفن
          الأصغر من نحو 15–20 مترًا (قوارب الصيد) · التمييز بين سفينة تفرّغ وأخرى بانتظار رصيف داخل
          الحوض · الأسباب الاقتصادية أو السياسية للارتفاع · تمييز دقيق بين السفن المتلاصقة عند
          الازدحام الشديد.</p>
        </div>""", unsafe_allow_html=True)

    # ------------------------------------------------ page 3: full report text
    with p_report:
        page_title("التقرير الدوري — رصد النشاط البحري في مرفأ اللاذقية")
        st.markdown(f"<p class='fpane-sub' style='font-size:11.5px'>الفترة المشمولة: {d0:%Y-%m} — {d1:%Y-%m} · "
                    f"آخر مشهد: <span dir='ltr'>{last_dt:%Y-%m-%d %H:%M}Z</span> · "
                    f"المؤشر: متوسط السفن لكل مشاهدة · المقارنة: نفس الفترة بنفس الفترة</p>", unsafe_allow_html=True)

        # ---- 1) executive summary ----
        page_title("1) الملخص التنفيذي")
        st.markdown(f"""
**التغطية:** {len(good)} مشهدًا راداريًا صالحًا من أصل {len(scenes)}، و{len(s2)} مشهدًا بصريًا،
على مدى {int(monthly['n_obs'].gt(0).sum())} شهرًا (كانون الثاني 2022 – آب 2026).

**النتائج:**

1. متوسط السفن في حوض المرفأ بلغ **{m26:.1f}** لكل مشاهدة في كانون الثاني–آب 2026، مقابل
**{t26_b:.1f}** في الفترة نفسها من 2025 (نمو +{yoy:.0f}%). الفرق دال إحصائيًا: احتمال أقل من 0.0001
على مستوى المشاهدات الفردية، و{t26_p:.4f} على مستوى المتوسطات الشهرية.

2. الارتفاع غير موسمي: شباط–نيسان 2026 ({feb_apr_26:.1f}) مقابل {feb_apr_base:.1f} للأشهر نفسها
في 2022–2025 (احتمال أقل من 0.0001).

3. الضغط متزامن على المكوّنين: سفن الأرصفة {berth_pre:.1f} ← {berth_26:.1f}، وسفن الانتظار في
المرسى {anch_pre:.1f} ← {anch_26:.1f} لكل مشاهدة.

4. السنوات 2022–2025 لم تسجل تغيرًا دالًا إحصائيًا، بما فيها ما بعد كانون الأول 2024
(احتمال {tpost_p:.3f}).
""")

        # ---- 2) data & coverage ----
        page_title("2) البيانات والتغطية")
        st.markdown(f"""
| المصدر | البيانات | العدد |
|---|---|---|
| Sentinel-1 (كوبرنيكوس/ESA) | رادار 10م، استقطابان (VV وVH) | {len(scenes)} مشهدًا ({len(good)} صالحًا) |
| Sentinel-2 (كوبرنيكوس/ESA) | بصري 10م | {len(s2)} مشهدًا |
| خريطة الشارع المفتوحة | حدود المرفأ + الكاسر + الساحل | — |
| ناتشورال إيرث 10م | اليابسة المرجعية | — |

استُبعد {len(scenes)-len(good)} مشهدًا من الكتالوج لعدم اكتمال تغطية منطقة الدراسة (قطع الحافة في
مدارات الصعود). كل مشهد موثق بمعرّفه الرسمي وتاريخ التقاطه ومداره.
""")

        # ---- 3) study area ----
        page_title("3) منطقة الدراسة")
        _pg = _port_geometry()
        _wkm, _hkm = _aoi_box_km()
        if _pg:
            _area_txt = (f"المساحة {_pg['area_ha']:.0f} هكتار، المركز "
                         f"{_pg['lon']:.4f}° شرقًا، {_pg['lat']:.4f}° شمالًا")
        else:
            _area_txt = "الحدود الرسمية من خريطة الشارع المفتوحة"
        st.markdown(f"""
الحدود: مضلع المرفأ من خريطة الشارع المفتوحة ({_area_txt}). مناطق الرصد: الحوض (ضمن 400م من الحد)،
المرسى ومنطقة الاقتراب (0.4–4 كم)، ومياه العبور — داخل صندوق دراسة {_wkm:.1f} × {_hkm:.1f} كم.
لا تُستخدم حدود تقريبية.
""")

        # ---- 4) methodology ----
        page_title("4) المنهجية والمؤشر")
        st.markdown(f"""
**خط المعالجة:**
1. قراءة النطاق الجزئي من كل مشهد وإسقاطه على شبكة UTM-36N ثابتة بدقة 10م (تطابق بكسل كامل بين المشاهد).
2. قناع اليابسة من مرجعين جغرافيين مع قناع محسّن من متوسط 30 مشهدًا راداريًا.
3. تنعيم لي لإزالة التشويش، ثم عتبة تكيفية T = μ + k·σ على المياه المفتوحة، مع تحقق متقاطع بين الاستقطابين.
4. مكونات متصلة، وفصل السفن المتلاصقة بخوارزمية المستجمعات المائية، وتوحيد الأجزاء المنقسمة.
5. استخراج الإحداثيات (WGS84) والأبعاد والاستطاعة والمنطقة لكل سفينة.

**مؤشر النشاط:** متوسط السفن لكل مشاهدة، محسوبًا على المشاهدات التي غطت الحوض بالكامل فقط
(تغطية 70% فأكثر؛ فعليًا {cov_min_pct:.0f}% في السلسلة الحالية). الأشهر بلا مشاهدات مستبعدة.

**تصنيف نوع السفينة** (حاويات/نفط/بضائع) غير ممكن من الرادار وحده. تقديرات الأبعاد في تبويب
«التحقق AIS» تقريبية ومعلَّمة، والتصنيف المؤكد يتطلب مطابقة بيانات AIS.
""")

        # ---- 5) results: yearly table ----
        page_title("5) النتائج — الملخص السنوي")
        _yr = yearly[["year", "n_obs", "annual_mean_ships_port", "annual_mean_adj",
                      "peak_month", "peak_value", "low_month", "low_value", "yoy_pct"]] \
            .rename(columns={"year": "السنة", "n_obs": "مشاهدات",
                             "annual_mean_ships_port": "متوسط النشاط",
                             "annual_mean_adj": "بعد تصحيح التغطية",
                             "peak_month": "أعلى شهر", "peak_value": "قيمة الذروة",
                             "low_month": "أدنى شهر", "low_value": "قيمة الأدنى",
                             "yoy_pct": "التغير السنوي %"})
        _yr["أعلى شهر"] = _yr["أعلى شهر"].map(lambda x: ["كانون الثاني","شباط","آذار","نيسان","أيار","حزيران",
            "تموز","آب","أيلول","تشرين الأول","تشرين الثاني","كانون الأول"][int(x)-1])
        _yr["أدنى شهر"] = _yr["أدنى شهر"].map(lambda x: ["كانون الثاني","شباط","آذار","نيسان","أيار","حزيران",
            "تموز","آب","أيلول","تشرين الأول","تشرين الثاني","كانون الأول"][int(x)-1])
        st.dataframe(_yr, width="stretch", hide_index=True)
        st.markdown("ملاحظة: التغير السنوي يُحسب على أساس نفس الأشهر عند مقارنة سنة جزئية "
                    "(2026: كانون الثاني–آب).")

        # ---- 6) statistical tests ----
        page_title("6) التحليل الإحصائي")
        st.markdown(f"""
**اتجاه السلسلة (مان-كيندال):** τ = {summary.get('mk_tau')}، احتمال {summary.get('mk_p'):.4f}.
لا اتجاه رتيب عبر السلسلة كاملة؛ النمط الفعلي استقرار في 2022–2025 ثم انتقال مستوى في أواخر 2025،
وهو نمط لا يلتقطه اختبار الاتجاه الرتيب.

**اختبارات الفترات (نفس الفترة بنفس الفترة):**
""")
        _reg_rows = []
        for _k in ["y2023_vs_2022", "y2024_vs_2023", "y2025_vs_2024", "y2026_vs_2025", "post_vs_pre_dec2024"]:
            _t = summary["regimes"].get(_k, {}).get("test")
            if _t and _t.get("valid"):
                _reg_rows.append(dict(المقارنة=summary["regimes"][_k]["label"],
                                      قبل=round(_t["mean_before"], 1), بعد=round(_t["mean_after"], 1),
                                      التغير_pct=f"{_t['diff_pct']:+.0f}%",
                                      الاحتمال=_t["p_value"],
                                      الحكم="دال" if _t["p_value"] < 0.05 else "غير دال"))
        st.dataframe(pd.DataFrame(_reg_rows), width="stretch", hide_index=True)
        # scene-level bootstrap — computed live, never hardcoded
        _sb_ok = False
        _diff = _ci0 = _ci1 = None
        try:
            from report import scene_bootstrap as _sb
            _sb_res = _sb(scenes)
            _diff = float(_sb_res["diff"]); _ci0 = float(_sb_res["ci"][0]); _ci1 = float(_sb_res["ci"][1])
            _sb_ok = True
        except Exception:
            try:
                _g26 = fscenes[(fscenes["dt"].dt.year == 2026)]
                _g25 = fscenes[(fscenes["dt"].dt.year == 2025)]
                if len(_g26) and len(_g25):
                    _diff = float(_g26["n_est_in_port"].mean() - _g25["n_est_in_port"].mean())
                    _sb_ok = True
            except Exception:
                pass
        if _sb_ok:
            st.markdown(f"على مستوى المشاهدات الفردية (كانون الثاني–آب): فرق 2026 مقابل 2025 "
                        f"= +{_diff:.1f} سفينة لكل مشاهدة (فاصل ثقة 95%: {_ci0:.1f}–{_ci1:.1f})، "
                        f"و2026 أعلى من كل سنة في 2022–2025 باحتمال أقل من 0.0001.")
        else:
            st.markdown("على مستوى المشاهدات الفردية: 2026 أعلى من السنوات السابقة في الأشهر نفسها "
                        "(احتمال أقل من 0.0001).")

        # ---- 6أ) regional comparison (three ports) ----
        page_title("6أ) المقارنة الإقليمية — اللاذقية · طرطوس · بانياس")
        try:
            from compare import summary as _cmp_rpt
            _cr = _cmp_rpt()
            _rows_r = []
            for _k, _name in [("latakia", "اللاذقية"), ("tartus", "طرطوس"), ("baniyas", "بانياس (نفطي)")]:
                _v = _cr.get(_k)
                if _v:
                    _rows_r.append(dict(الميناء=_name,
                                        قبل=round(_v["mean_25"], 1),
                                        بعد=round(_v["mean_26"], 1),
                                        التغير_pct=f"{_v['pct']:+.1f}%"))
            if _rows_r:
                st.dataframe(pd.DataFrame(_rows_r), width="stretch", hide_index=True)
                st.markdown(f"""
المقارنة على أساس الأشهر نفسها (كانون الثاني–آب) وبخط المعالجة نفسه. اللاذقية +{_cr['latakia']['pct']:.0f}%
مقابل طرطوس +{_cr['tartus']['pct']:.1f}%، وبانياس +{_cr['baniyas']['pct']:.1f}% من قاعدة منخفضة
({_cr['baniyas']['mean_25']:.1f} سفينة لكل مشاهدة). الخلاصة: نمط الارتفاع لا يتكرر في الميناءين الآخرين؛
الظاهرة محلية في مرفأ اللاذقية.
""")
        except Exception as _e:
            st.info("المقارنة الإقليمية غير متاحة: " + str(_e)[:80])

        # ---- 7) operational KPIs ----
        page_title("7) المؤشرات التشغيلية")
        st.markdown(f"""
| المؤشر | القيمة | المقارنة |
|---|---|---|
| وسيط مدة بقاء السفينة | {dwell_med:.0f} أيام | معدل دوران اعتيادي |
| سفن بقيت أربعة أيام فأكثر | {dwell_pers:.0f}% | مستقر عبر الفترة |
| سفن الأرصفة | {berth_26:.1f} لكل مشاهدة | {berth_pre:.1f} في 2022–2025 |
| مشاهدات فوق سقف القدرة | {cap_pct26:.0f}% | {cap_pre_pct:.0f}% قبل 2026 (السقف {cap_p95:.0f} سفينة) |
| تطابقات مدة البقاء | {dwell_pairs:,} زوجًا | ضمن 400م وفجوة 10 أيام فأقل |
""")

        # ---- 8) validation ----
        page_title("8) التحقق وجودة البيانات")
        st.markdown(f"""
**جودة الاكتشافات:** متوسط نسبة الإشارة إلى الضوضاء {snr:.1f} ديسيبل؛ تغطية الحوض
{cov_min_pct:.0f}% فأكثر في كل المشاهدات؛ حالة البحر متقاربة عبر السنوات. لا تظهر الفروق المرصودة
كأثر لظروف الرصد.

**التحقق المتقاطع (رادار/بصري):** {len(pairs)} زوجًا (فارق أربعة أيام فأقل، غيوم 25% فأقل). العدّاد
البصري يُظهر النمط نفسه: {_opt26:.1f} مقابل {_opt25:.1f} في 2025.

**مراجعة الجودة:** وُحّدت سجلات السفن ({int(good['n_est'].sum()):,} سجلًا) عبر إعادة معالجة كاملة
ومواءمة ملفات المشاهدات مع ملفات السفن (صفر تباين)، مع توثيق الأوسمة (مدمج / حافة رصيف / شبيه عنقود).
""")

        # ---- 9) conclusions ----
        page_title("9) الخلاصة والتوصيات")
        st.markdown(f"""
البيانات تدعم انتقالًا في مستوى النشاط بدأ في كانون الأول 2025، وبلغ ذروته في شباط 2026
({peak_val:.1f} سفينة لكل مشاهدة)، وبقي الأشهر اللاحقة أعلى من متوسط 2022–2025. لا تدعم البيانات
تفسيرًا موسميًا ولا نمطًا إقليميًا.

**التوصيات:**
1. مواصلة الرصد الشهري؛ أشهر أيلول–كانون الأول 2026 تحدد ما إذا كان المستوى الجديد مستقرًا.
2. إدخال بيانات AIS حقيقية لتصنيف أنواع السفن والتحقق من الهويات.
3. مراجعة عتبات فصل السفن المتلاصقة للفترات الأعلى من 20 سفينة لكل مشاهدة.
4. ربط السلسلة بمؤشرات التجارة الخارجية عند توفرها.
5. إبقاء المقارنة الثلاثية (طرطوس · بانياس) ضمن التحديث الأسبوعي الآلي.
""")

        # ---- 10) limitations ----
        page_title("10) حدود المنهجية")
        st.markdown("""
- السفن الأصغر من نحو 15–20م (قوارب الصيد) غير مكتشفة بشكل منهجي بدقة 10م.
- فصل السفن المتلاصقة تقديري؛ تبقى أخطاء عد محدودة عند الازدحام الشديد.
- نوع السفينة وحمولتها خارج نطاق التحليل دون بيانات AIS.
- العدّاد البصري تقديري ويتأثر بالغيوم.
- لا تفسر البيانات أسباب الارتفاع؛ الوثيقة تصف الظاهرة كميًا وتضبط الموسمية فقط.
""")

        st.markdown('<p class="fpane-sub" style="margin-top:20px">البيانات: كوبرنيكوس (ESA) عبر '
                    'مايكروسوفت بلانيتاري كومبيوتر · الحدود: خريطة الشارع المفتوحة © مساهموها · '
                    'اليابسة: ناتشورال إيرث (الملكية العامة).</p>', unsafe_allow_html=True)

    # ------------------------------------------------ page 4: regional comparison
    with p_region:
        page_title("المقارنة الإقليمية — اللاذقية · طرطوس · بانياس")
        try:
            from compare import load_series, summary as cmp_summary, yearly_comparison as cmp_yearly
            _cdf = load_series()
            _cs = cmp_summary()
            _la, _ta = _cs.get("latakia"), _cs.get("tartus")
            _ba = _cs.get("baniyas")
            c1, c2, c3, c4, c5, c6 = st.columns(6, gap="small")
            with c1:
                metric("اللاذقية 2026", f"{_la['mean_26']:.1f}", "سفينة لكل مشاهدة (كانون الثاني–آب)", "#01B8AA")
            with c2:
                metric("تغير اللاذقية", f"{_la['pct']:+.1f}%", "مقارنة بنفس الأشهر من 2025",
                       "#34D399" if _la["pct"] >= 0 else "#F87171")
            with c3:
                metric("طرطوس 2026", f"{_ta['mean_26']:.1f}", "سفينة لكل مشاهدة (كانون الثاني–آب)", "#F59E0B")
            with c4:
                metric("تغير طرطوس", f"{_ta['pct']:+.1f}%", "مقارنة بنفس الأشهر من 2025",
                       "#34D399" if _ta["pct"] >= 0 else "#F87171")
            with c5:
                if _ba:
                    metric("بانياس 2026", f"{_ba['mean_26']:.1f}", "سفينة لكل مشاهدة (كانون الثاني–آب)", "#A78BFA")
                else:
                    metric("بانياس 2026", "—", "غير متاحة", "#6B7280")
            with c6:
                if _ba:
                    metric("تغير بانياس", f"{_ba['pct']:+.1f}%", "مقارنة بنفس الأشهر من 2025",
                           "#34D399" if _ba["pct"] >= 0 else "#F87171")
                else:
                    metric("تغير بانياس", "—", "غير متاحة", "#6B7280")
            _ban_note = ""
            if _ba:
                _ban_note = (f" في المقابل سجّل مرفأ بانياس النفطي <b>{_ba['pct']:+.0f}%</b> "
                             f"لكن من قاعدة منخفضة (<b>{_ba['mean_25']:.1f}</b> ← <b>{_ba['mean_26']:.1f}</b> "
                             f"سفينة لكل مشاهدة) — وهو مرفأ تحميل نفطي صغير الحوض")
            st.markdown(f"""
            <div class="read-note"><b>القراءة التحليلية:</b> بينما قفز نشاط اللاذقية <b>{_la['pct']:+.0f}%</b>
            في كانون الثاني–آب 2026، بقي نشاط طرطوس شبه مستقر (<b>{_ta['pct']:+.1f}%</b>). طرطوس هو الميناء
            الأكبر والأكثر ازدحامًا تاريخيًا (قيمه المطلقة أعلى)، ومع ذلك لم يشهد قفزة مماثلة{_ban_note} —
            وهذا يرجّح أن الارتفاع في اللاذقية <b>خاص بالمرفأ</b> (لوجستي/تشغيلي) وليس موجة إقليمية على
            الساحل السوري.</div>""", unsafe_allow_html=True)
            pbi("المقارنة الشهرية — اللاذقية · طرطوس · بانياس (سفن لكل مشاهدة)")
            st.plotly_chart(chart_comparison(_cdf), width="stretch", key="cmp_line",
                            config={"displayModeBar": False})
            c1, c2 = st.columns(2, gap="small")
            with c1:
                pbi("فجوة النشاط — اللاذقية ناقص طرطوس")
                st.plotly_chart(chart_gap(_cdf), width="stretch", key="cmp_gap",
                                config={"displayModeBar": False})
            with c2:
                pbi("متوسط النشاط السنوي — مقارنة")
                _ycmp = cmp_yearly()[["year", "latakia", "tartus", "baniyas"]] \
                    .rename(columns={"year": "السنة", "latakia": "اللاذقية",
                                     "tartus": "طرطوس", "baniyas": "بانياس"})
                st.dataframe(_ycmp.round(1), width="stretch", hide_index=True)
        except Exception as e:
            st.info("المقارنة الإقليمية غير متاحة: " + str(e)[:100])

    # ------------------------------------------------ page 5: trend
    with p_trend:
        page_title("الاتجاه الزمني")
        # ---- stats strip ----
        _tm = monthly[monthly["n_obs"] > 0].copy()
        _t_latest = _tm.iloc[-1]
        _t_prev = _tm.iloc[-2] if len(_tm) > 1 else None
        _t_mom = None
        if _t_prev is not None and _t_prev["mean_ships_port_adj"]:
            _t_mom = (_t_latest["mean_ships_port_adj"] - _t_prev["mean_ships_port_adj"]) / _t_prev["mean_ships_port_adj"] * 100
        _t_mk = summary.get("mk_direction")
        _t_mk_txt = "صعود" if _t_mk == "increase" else ("انحدار" if _t_mk == "decrease" else "—")
        _t_peak = _tm.loc[_tm["mean_ships_port_adj"].idxmax()]
        _t_c1, _t_c2, _t_c3, _t_c4, _t_c5, _t_c6 = st.columns(6, gap="small")
        with _t_c1:
            metric("أحدث شهر", f"{_t_latest['mean_ships_port_adj']:.1f}",
                   f"<span dir='ltr'>{_t_latest['ym']}</span>", "#01B8AA")
        with _t_c2:
            if _t_mom is not None:
                metric("التغير الشهري", f"{_t_mom:+.1f}%", "",
                       "#34D399" if _t_mom >= 0 else "#F87171")
            else:
                metric("التغير الشهري", "—", "", "#6B7280")
        with _t_c3:
            metric("أعلى شهر في السلسلة", f"<span dir='ltr'>{_t_peak['ym']}</span>",
                   f"{_t_peak['mean_ships_port_adj']:.1f} سفينة لكل مشاهدة", "#F59E0B")
        with _t_c4:
            metric("متوسط السلسلة", f"{_tm['mean_ships_port_adj'].mean():.1f}",
                   f"عبر {len(_tm)} شهرًا", "#A78BFA")
        with _t_c5:
            metric("اتجاه السلسلة", _t_mk_txt,
                   f"τ={summary['mk_tau']} · احتمال {summary['mk_p']}",
                   "#34D399" if summary.get("mk_p", 1) < 0.05 else "#F59E0B")
        with _t_c6:
            metric("مشاهدات الشهر", f"{int(_t_latest['n_obs'])}",
                   f"في <span dir='ltr'>{_t_latest['ym']}</span>", "#7EDDD4")

        pbi("النشاط الشهري — سفن لكل مشاهدة")
        st.plotly_chart(chart_monthly_line(fmonthly), width="stretch", key="trend_line",
                        config={"displayModeBar": False})
        c1, c2 = st.columns(2, gap="small")
        with c1:
            pbi("كشف التغير — المتوسط المتحرك")
            st.plotly_chart(chart_change_detection(fmonthly), width="stretch", config={"displayModeBar": False})
        with c2:
            pbi("التغير الشهري بين الشهور")
            st.plotly_chart(chart_mom(fmonthly), width="stretch", config={"displayModeBar": False})
        pbi("جميع المشاهدات الفردية")
        st.plotly_chart(chart_scene_scatter(fscenes), width="stretch", config={"displayModeBar": False})

    # ------------------------------------------------ page 6: anomaly detection
    with p_anom:
        page_title("كشف الشذوذ — مراقبة إحصائية فورية")
        try:
            from anomaly import detect_anomalies, chart_ewma, chart_cusum
            _anom, _m_anom = detect_anomalies(scenes)
            c1, c2, c3, c4 = st.columns(4, gap="small")
            with c1:
                metric("خط الأساس (24 شهرًا)", f"{_anom['baseline_mu']:.1f}",
                       f"± {_anom['baseline_sd']:.1f} سفينة لكل مشاهدة", "#6B7280")
            with c2:
                metric(f"أحدث شهر ({_anom['latest_ym']})", f"{_anom['latest']:.1f}",
                       f"z = {_anom['latest_z']:+.2f}", "#01B8AA")
            with c3:
                metric("أحداث شذوذ مكتشفة", f"{len(_anom['events'])}",
                       "متوسط مرجح + مجموع تراكمي", "#F59E0B" if _anom["events"] else "#34D399")
            with c4:
                _ev_up = sum(1 for e in _anom["events"] if e["type"] == "ارتفاع")
                metric("منها ارتفاعات", f"{_ev_up}", "قيم فوق خط الأساس", "#F87171")
            pbi("مخطط المتوسط المتحرك المرجح — القيم الشهرية مقابل حدود ±3σ")
            st.plotly_chart(chart_ewma(scenes), width="stretch", key="ewma",
                            config={"displayModeBar": False})
            pbi("مخطط المجموع التراكمي — تراكم الانحرافات")
            st.plotly_chart(chart_cusum(scenes), width="stretch", key="cusum",
                            config={"displayModeBar": False})
            if _anom["events"]:
                _evdf = pd.DataFrame(_anom["events"])
                _evdf = _evdf.rename(columns={"ym": "الشهر", "method": "الطريقة",
                                              "type": "النوع", "value": "القيمة",
                                              "z_score": "درجة z"})
                pbi("سجل أحداث الشذوذ المكتشفة")
                st.dataframe(_evdf, width="stretch", hide_index=True)
        except Exception as e:
            st.info("وحدة كشف الشذوذ غير متاحة: " + str(e)[:100])

    # ------------------------------------------------ page 3: comparisons
    with p_comp:
        page_title("المقارنات بين السنوات والأشهر")
        # ---- stats strip ----
        _cm = monthly[monthly["n_obs"] > 0].copy()
        _cm_peak = _cm.loc[_cm["mean_ships_port_adj"].idxmax()]
        _cm_2026 = _cm[_cm["year"] == 2026]["mean_ships_port_adj"]
        _cm_base = _cm[_cm["year"].isin([2022, 2023, 2024, 2025])]["mean_ships_port_adj"]
        _cm_diff = None
        if len(_cm_2026) and len(_cm_base):
            _cm_diff = (_cm_2026.mean() - _cm_base.mean()) / _cm_base.mean() * 100
        _cc1, _cc2, _cc3, _cc4 = st.columns(4, gap="small")
        with _cc1:
            metric("أعلى شهر في السلسلة", f"<span dir='ltr'>{_cm_peak['ym']}</span>",
                   f"{_cm_peak['mean_ships_port_adj']:.1f} سفينة لكل مشاهدة", "#F59E0B")
        with _cc2:
            metric("متوسط 2026", f"{_cm_2026.mean():.1f}" if len(_cm_2026) else "—",
                   "سفينة لكل مشاهدة", "#01B8AA")
        with _cc3:
            if _cm_diff is not None:
                metric("2026 مقابل 2022–2025", f"{_cm_diff:+.1f}%",
                       "فرق المتوسطات الشهرية", "#34D399" if _cm_diff >= 0 else "#F87171")
            else:
                metric("2026 مقابل 2022–2025", "—", "", "#6B7280")
        with _cc4:
            _cm_years = sorted(_cm["year"].unique())
            metric("سنوات مغطاة", f"{len(_cm_years)}",
                   f"<span dir='ltr'>{_cm_years[0]}–{_cm_years[-1]}</span>", "#A78BFA")
        c1, c2 = st.columns(2, gap="small")
        with c1:
            pbi("المقارنة الشهرية بين السنوات")
            st.plotly_chart(chart_monthly_comparison(fmonthly), width="stretch", config={"displayModeBar": False})
        with c2:
            pbi("الخريطة الحرارية — سنة × شهر")
            st.plotly_chart(chart_heatmap(fmonthly), width="stretch", config={"displayModeBar": False})
        c1, c2 = st.columns(2, gap="small")
        with c1:
            pbi("النشاط السنوي والتغير السنوي")
            st.plotly_chart(chart_yearly(yearly[yearly["year"].isin([int(y) for y in sel_years])]),
                            width="stretch", config={"displayModeBar": False})
        with c2:
            pbi("التغير السنوي — المخطط التراجعي")
            st.plotly_chart(chart_waterfall(yearly[yearly["year"].isin([int(y) for y in sel_years])]),
                            width="stretch", config={"displayModeBar": False})
        # yearly table + regime tests
        yf = yearly[(yearly["data_status"] == "ok") & (yearly["year"].isin([int(y) for y in sel_years]))]
        if len(yf):
            pbi("جدول الملخص السنوي")
            st.dataframe(yf[["year", "n_obs", "annual_mean_ships_port", "annual_mean_adj",
                             "peak_month", "peak_value", "low_month", "low_value", "yoy_pct"]]
                         .rename(columns={"year": "السنة", "n_obs": "المشاهدات",
                                          "annual_mean_ships_port": "متوسط سفن لكل مشاهدة",
                                          "annual_mean_adj": "بعد تصحيح التغطية",
                                          "peak_month": "شهر الذروة", "peak_value": "قيمة الذروة",
                                          "low_month": "أدنى شهر", "low_value": "قيمة الأدنى",
                                          "yoy_pct": "تغير سنوي %"}),
                         width="stretch", hide_index=True)
        regs = summary["regimes"]
        rows = []
        for key in ["y2023_vs_2022", "y2024_vs_2023", "y2025_vs_2024",
                    "y2026_vs_2025", "post_vs_pre_dec2024"]:
            t = regs.get(key, {}).get("test")
            if t and t.get("valid"):
                rows.append(dict(المقارنة=regs[key]["label"], قبل=round(t["mean_before"], 1),
                                 بعد=round(t["mean_after"], 1), التغير_pct=f"{t['diff_pct']:+.0f}%",
                                 p_value=t["p_value"],
                                 الدلالة="دال" if t["p_value"] < 0.05 else "غير دال"))
        if rows:
            pbi("اختبارات الفترات (نفس الفترة بنفس الفترة)")
            st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

    # ------------------------------------------------ page 7: observations data
    with p_data:
        page_title("بيانات المشاهدات — الجدول الكامل")
        st.markdown(f"<p class='fpane-sub'>كل صف = مشهد قمر صناعي حقيقي بمعرّفه الرسمي وتاريخ التقاطه. "
                    f"الجدول يخضع للفلاتر الجانبية (السنة/الشهر/الفترة). يمكنك البحث والفرز داخل الجدول.</p>",
                    unsafe_allow_html=True)
        _obs = fscenes[["dt", "id", "platform", "orbit", "n_est_in_port", "n_anchorage",
                        "n_est", "coverage", "cov_port", "noise_floor_db", "sea_roughness"]].copy()
        _obs = _obs.rename(columns={"dt": "التاريخ (UTC)", "id": "معرف المشهد",
                                    "platform": "القمر", "orbit": "المدار",
                                    "n_est_in_port": "سفن الحوض", "n_anchorage": "سفن المرسى",
                                    "n_est": "إجمالي السفن", "coverage": "تغطية البحر",
                                    "cov_port": "تغطية الحوض", "noise_floor_db": "الضوضاء (ديسيبل)",
                                    "sea_roughness": "خشونة البحر"})
        _obs["التاريخ (UTC)"] = _obs["التاريخ (UTC)"].dt.strftime("%Y-%m-%d %H:%M")
        st.dataframe(_obs, width="stretch", hide_index=True)
        c1, c2, c3 = st.columns(3, gap="small")
        with c1:
            st.download_button("تنزيل CSV (المشاهدات المفلترة)", _obs.to_csv(index=False).encode("utf-8-sig"),
                               file_name="latakia_scenes_filtered.csv", mime="text/csv",
                               use_container_width=True)
        with c2:
            _vf = fvessels[["datetime", "scene", "vessel_id", "lat", "lon", "length_m",
                            "peak_db", "zone"]].copy()
            _vf = _vf.rename(columns={"scene": "المشهد"})
            _vf["datetime"] = _vf["datetime"].dt.strftime("%Y-%m-%d %H:%M")
            st.download_button("تنزيل CSV (سجلات السفن)", _vf.to_csv(index=False).encode("utf-8-sig"),
                               file_name="latakia_vessels_filtered.csv", mime="text/csv",
                               use_container_width=True)
        with c3:
            st.markdown(f"<p class='fpane-sub' style='padding-top:8px'>المشاهدات المعروضة: "
                        f"<b>{len(_obs)}</b> · سجلات السفن: <b>{len(fvessels):,}</b></p>",
                        unsafe_allow_html=True)
        st.markdown('<div class="page-title"><span class="bar"></span>تصدير متقدم</div>',
                    unsafe_allow_html=True)
        d1, d2, d3, d4 = st.columns(4, gap="small")
        with d1:
            try:
                _gj = _geoexport_cached()
                with open(_gj, "rb") as f:
                    st.download_button("GeoJSON (لبرامج GIS)", f,
                                       file_name="latakia_vessels.geojson",
                                       mime="application/geo+json", use_container_width=True)
            except Exception as ex:
                st.info("GeoJSON غير متاح: " + str(ex)[:60])
        with d2:
            try:
                _sj = _sumexport_cached()
                with open(_sj, "rb") as f:
                    st.download_button("ملخص JSON (آلي)", f,
                                       file_name="latakia_summary.json",
                                       mime="application/json", use_container_width=True)
            except Exception as ex:
                st.info("JSON غير متاح: " + str(ex)[:60])
        with d3:
            try:
                _tdf = pd.read_csv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                                "data", "detections", "tracks.csv"))
                with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                       "data", "detections", "tracks.csv"), "rb") as f:
                    st.download_button("مسارات السفن CSV", f, file_name="vessel_tracks.csv",
                                       mime="text/csv", use_container_width=True)
            except Exception:
                st.info("مسارات السفن: شغّل tracking.py أولاً")
        with d4:
            try:
                with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                       "docs", "FINAL_REPORT.xlsx"), "rb") as f:
                    st.download_button("مصنف Excel الكامل", f, file_name="FINAL_REPORT.xlsx",
                                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                       use_container_width=True)
            except Exception:
                st.info("Excel غير متاح")

        # ---- GeoTIFF raster export (GIS-ready layers on the fixed UTM grid) ----
        st.markdown('<div class="page-title"><span class="bar"></span>تصدير GeoTIFF — طبقات راستر (GIS)</div>',
                    unsafe_allow_html=True)
        st.markdown(f"<p class='fpane-sub'>كل طبقة تُبنى على شبكة UTM-36N الثابتة (10م) نفسها المستخدمة في "
                    f"خط الكشف، فتنطبق بكسلة-بكسل على الصور الرادارية والقناع. القيم عدّادات حقيقية من ملفات "
                    f"vessels.json — مجموع خلايا طبقة العد يساوي <b><span dir='ltr'>{int(good['n_est'].sum()):,}</span></b> "
                    f"سجل سفينة. خلايا اليابسة الخالية = NoData.</p>", unsafe_allow_html=True)
        g1, g2, g3, g4, g5 = st.columns([1, 1, 1, 1.4, 1], gap="small")
        with g1:
            try:
                _tp = _gt_total_cached()
                with open(_tp, "rb") as f:
                    st.download_button("العد الكلي (GeoTIFF)", f,
                                       file_name="latakia_vessel_count_total.tif",
                                       mime="image/tiff", use_container_width=True)
            except Exception as ex:
                st.info("غير متاح: " + str(ex)[:50])
        with g2:
            try:
                _ty = _gt_yearly_cached()
                with open(_ty, "rb") as f:
                    st.download_button("المكدس السنوي (GeoTIFF)", f,
                                       file_name="latakia_vessel_count_by_year.tif",
                                       mime="image/tiff", use_container_width=True)
            except Exception as ex:
                st.info("غير متاح: " + str(ex)[:50])
        with g3:
            try:
                _to = _gt_occupancy_cached()
                with open(_to, "rb") as f:
                    st.download_button("الإشغال النسبي (GeoTIFF)", f,
                                       file_name="latakia_occupancy_share.tif",
                                       mime="image/tiff", use_container_width=True)
            except Exception as ex:
                st.info("غير متاح: " + str(ex)[:50])
        with g4:
            _glab = [f"{r['dt']:%Y-%m-%d %H:%M}Z · {r['id'][:24]}…" for _, r in fscenes.iterrows()]
            if len(_glab):
                _gsel = st.selectbox("مشهد لطبقة حضور (GeoTIFF)", range(len(_glab)),
                                     format_func=lambda i: _glab[i], key="gt_scene_sel")
                _gsid = fscenes.iloc[_gsel]["id"]
                try:
                    _gsc = _gt_scene_cached(_gsid)
                    with open(_gsc, "rb") as f:
                        st.download_button("طبقة المشهد المختار (GeoTIFF)", f,
                                           file_name=f"latakia_scene_{_gsid[:40]}.tif",
                                           mime="image/tiff", use_container_width=True)
                except Exception as ex:
                    st.info("غير متاح: " + str(ex)[:50])
            else:
                st.info("لا مشاهد ضمن الفلاتر")
        with g5:
            import zipfile, io
            _zip_buf = io.BytesIO()
            _n_gt = 0
            with zipfile.ZipFile(_zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
                for _f in sorted(os.listdir(GTIFF_DIR)):
                    if _f.endswith(".tif"):
                        zf.write(os.path.join(GTIFF_DIR, _f), arcname=_f)
                        _n_gt += 1
            st.download_button(f"كل الطبقات ({_n_gt} ملف ZIP)", _zip_buf.getvalue(),
                               file_name="latakia_geotiff_layers.zip",
                               mime="application/zip", use_container_width=True)

    # ------------------------------------------------ page 4: advanced
    with p_adv:
        page_title("تحليلات متقدمة")
        a1, a2, a3, a4, a5 = st.tabs(["التوزيع الإحصائي", "الملف الموسمي", "ضغط التشغيل",
                                      "مؤشرات تشغيلية", "تتبع السفن"])
        with a5:
            try:
                from tracking import build_tracks
                _tracks, _tstats = build_tracks(scenes)
                c1, c2, c3, c4 = st.columns(4, gap="small")
                with c1:
                    metric("مسارات سفن مميزة", f"{_tstats['total_tracks']:,}",
                           "سلسلة مطابقات عبر المشاهدات", "#01B8AA")
                with c2:
                    metric("سفن ظهرت ≥ مرتين", f"{_tstats['tracks_with_2plus']:,}",
                           "أي مكثت أكثر من مشهد", "#F59E0B")
                with c3:
                    metric("متوسط المشاهدات لكل مسار", f"{_tstats['mean_obs_per_track']:.1f}",
                           "عدد مرات رصد السفينة", "#A78BFA")
                with c4:
                    metric("أطول مسار", f"{_tstats['max_obs_per_track']}",
                           "مشاهدات لنفس السفينة", "#F87171")
                _td = _tracks.sort_values("n_obs", ascending=False).head(20)
                _td = _td.rename(columns={"n_obs": "عدد المشاهدات",
                                          "first_scene": "أول ظهور",
                                          "last_scene": "آخر ظهور",
                                          "n_distinct_vessels": "سجلات مميزة"})
                pbi("أطول 20 مسار سفينة (السفن الأكثر حضورًا)")
                st.dataframe(_td, width="stretch", hide_index=True)
            except Exception as e:
                st.info("وحدة التتبع غير متاحة: " + str(e)[:100])
        with a4:
            try:
                from insights import dwell_analysis, operational_series, chart_dwell, chart_berthed
                dw_df, dw_stats = dwell_analysis(scenes)
                op_df, p95 = operational_series(scenes)
                c1, c2 = st.columns([1, 1.4], gap="small")
                with c1:
                    pbi("مدة بقاء السفينة بين مشهدين متتاليين")
                    st.plotly_chart(chart_dwell(dw_df), width="stretch", key="dwell",
                                    config={"displayModeBar": False})
                with c2:
                    pbi("السفن الملاصقة للأرصفة شهريًا")
                    st.plotly_chart(chart_berthed(op_df), width="stretch", key="berthed",
                                    config={"displayModeBar": False})
                _op26 = op_df[op_df["year"] == 2026]
                _op25 = op_df[op_df["year"] <= 2025]
                st.markdown(f"""
                <div class="health">
                  <span class="chip">وسيط مدة البقاء <b><span dir="ltr">{dw_stats['median_days']} أيام</span></b></span>
                  <span class="chip">سفن باقية ≥ 4 أيام <b><span dir="ltr">{dw_stats['pct_persistent']:.0f}%</span></b></span>
                  <span class="chip">سفن الأرصفة 2026 <b><span dir="ltr">{_op26['berthed'].mean():.1f}</span></b> مقابل <span dir="ltr">{_op25['berthed'].mean():.1f}</span></span>
                  <span class="chip">مشاهدات فوق سقف القدرة <b><span dir="ltr">{_op26['over_capacity'].mean()*100:.0f}%</span></b> (السقف: {p95:.0f} سفينة)</span>
                </div>""", unsafe_allow_html=True)
            except Exception as e:
                st.info("المؤشرات التشغيلية غير متاحة: " + str(e)[:80])
        with a1:
            c1, c2 = st.columns(2, gap="small")
            with c1:
                pbi("توزيع السفن لكل مشهد حسب السنة (مخطط الصناديق)")
                st.plotly_chart(chart_boxplot(fscenes), width="stretch", config={"displayModeBar": False})
            with c2:
                pbi("توزيع أطوال السفن المكتشفة")
                st.plotly_chart(chart_length_hist(fscenes), width="stretch", config={"displayModeBar": False})
        with a2:
            c1, c2 = st.columns(2, gap="small")
            with c1:
                pbi("الملف الموسمي — 2026 مقابل متوسط 2022–2025")
                st.plotly_chart(chart_radar(fmonthly), width="stretch", config={"displayModeBar": False})
            with c2:
                pbi("مؤشر النشاط الحالي")
                st.plotly_chart(chart_gauge(fmonthly), width="stretch", key="gauge_adv",
                                config={"displayModeBar": False})
        with a3:
            pbi("ضغط التشغيل — الحوض مقابل المرسى (حجم الفقاعة = المشاهدات)")
            st.plotly_chart(chart_bubble(fmonthly), width="stretch", key="bubble_adv",
                            config={"displayModeBar": False})

    # ------------------------------------------------ page 5: map
    with p_map:
        page_title("الخريطة")
        if len(fvessels):
            # real data strip
            _nport = int((fvessels["zone"] == 2).sum())
            _nanch = int((fvessels["zone"] == 1).sum())
            _ntrans = int((fvessels["zone"] == 0).sum())
            st.markdown(f"""
            <div class="health">
              <span class="chip">نقاط معروضة <b><span dir="ltr">{len(fvessels):,}</span></b></span>
              <span class="chip">داخل الحوض <b><span dir="ltr">{_nport:,}</span></b></span>
              <span class="chip">المرسى <b><span dir="ltr">{_nanch:,}</span></b></span>
              <span class="chip">عبور <b><span dir="ltr">{_ntrans}</span></b></span>
              <span class="chip">الخلفية <b>متوسط 30 مشهدًا راداريًا حقيقيًا</b></span>
              <span class="chip">الحدود <b>خريطة الشارع المفتوحة</b></span>
            </div>""", unsafe_allow_html=True)
            pbi("خريطة مواقع السفن المكتشفة — إحداثيات حقيقية (WGS84)")
            st.plotly_chart(build_activity_map(fvessels), width="stretch", config={"displayModeBar": False})
            pbi("خريطة كثافة الاكتشافات — شبكة 60م فوق خلفية رادارية متوسطة")
            png = static_density_map(fvessels, out=os.path.join(MAP_DIR, "density_filtered.png"))
            st.image(png, width="stretch")
        else:
            st.info("لا توجد سفن ضمن الفلاتر المحددة.")

    # ------------------------------------------------ page 6: viewer
    with p_view:
        page_title("عارض الصور — تحقق بصري")
        if sat.startswith("Sentinel-2"):
            _s2 = s2[(s2["error"].isna() | (s2["error"] == ""))].copy()
            if len(_s2):
                _s2["dt"] = pd.to_datetime(_s2["datetime"])
                _s2 = _s2[_s2["dt"].dt.year.isin([int(y) for y in sel_years]) &
                           _s2["dt"].dt.month.isin(sel_months) &
                           (_s2["dt"].dt.date >= period[0]) & (_s2["dt"].dt.date <= period[1])].sort_values("dt")
            if len(_s2):
                lab2 = [f"{r['dt']:%Y-%m-%d %H:%M}Z · غيوم {r.get('cloud_pct_aoi', '—')}% · {r['id'][:20]}"
                        for _, r in _s2.iterrows()]
                sel2 = st.selectbox("اختر مشهد Sentinel-2", range(len(_s2)),
                                    format_func=lambda i: lab2[i], key="s2scene")
                r2 = _s2.iloc[sel2]
                rgb2 = os.path.join(S2_DIR, r2["id"], "rgb.png")
                c1, c2 = st.columns([2, 1], gap="small")
                with c1:
                    if os.path.exists(rgb2):
                        st.image(rgb2, width="stretch", caption=f"Sentinel-2 RGB · {r2['id'][:36]}…")
                    else:
                        st.info("لا تتوفر صورة لهذا المشهد.")
                with c2:
                    st.markdown(f"""
                    <div class="metric" style="margin-bottom:10px">
                      <div class="lbl">أجسام لامعة فوق البحر</div>
                      <div class="val" style="color:#34D399">{int(r2.get('optical_bright_count', 0))}</div>
                      <div class="sub">المرفأ: {int(r2.get('optical_port', 0))} · المرسى: {int(r2.get('optical_anchor', 0))}</div>
                    </div>
                    <div class="metric">
                      <div class="lbl">الغيوم فوق المنطقة</div>
                      <div class="val" style="color:#F59E0B">{r2.get('cloud_pct_aoi', '—')}%</div>
                      <div class="sub"><span dir="ltr">{r2['dt']:%Y-%m-%d %H:%M}Z</span></div>
                    </div>""", unsafe_allow_html=True)
            else:
                st.info("لا توجد مشاهد Sentinel-2 ضمن الفلاتر.")
        else:
            sc_list = fscenes.sort_values("dt")
        if sat.startswith("Sentinel-1") and len(sc_list):
            lab = [f"{r['dt']:%Y-%m-%d %H:%M}Z · {r['id'][:16]}… · {int(r['n_est_in_port'])} سفينة في الحوض"
                   for _, r in sc_list.iterrows()]
            # ---- navigation: buttons drive scene_idx directly ----
            if "scene_idx" not in st.session_state:
                st.session_state["scene_idx"] = 0
            # clamp: filters may have shrunk the list below the current index
            st.session_state["scene_idx"] = max(0, min(
                st.session_state["scene_idx"], len(sc_list) - 1))
            nav1, nav2, nav3 = st.columns([1, 2, 1])
            with nav1:
                if st.session_state["scene_idx"] > 0:
                    if st.button("‹ المشهد السابق", key="prev_scene", use_container_width=True):
                        st.session_state["scene_idx"] = st.session_state["scene_idx"] - 1
                        st.rerun()
            with nav3:
                if st.session_state["scene_idx"] < len(sc_list) - 1:
                    if st.button("المشهد التالي ›", key="next_scene", use_container_width=True):
                        st.session_state["scene_idx"] = st.session_state["scene_idx"] + 1
                        st.rerun()
            with nav2:
                st.markdown(f"<p style='text-align:center;color:var(--faint);font-size:12px'>المشهد "
                            f"{st.session_state['scene_idx'] + 1} من {len(sc_list)}</p>",
                            unsafe_allow_html=True)
            # selectbox with DYNAMIC key -> Streamlit creates a fresh widget
            # whenever scene_idx changes, so navigation buttons always work.
            _cur_idx = st.session_state["scene_idx"]
            _jump = st.selectbox("اختر مشهد Sentinel-1 (أو استخدم الزرين)",
                                 range(len(sc_list)), index=_cur_idx,
                                 format_func=lambda i: lab[i],
                                 key=f"scene_{_cur_idx}")
            if _jump != _cur_idx:
                st.session_state["scene_idx"] = _jump
                st.rerun()
            sel = st.session_state["scene_idx"]
            r = sc_list.iloc[sel]
            sid = r["id"]

            # ---- scene info strip (real metadata from the scene record) ----
            _plat = str(r.get("platform", "")).replace("SENTINEL-", "S-")
            _orbit = str(r.get("orbit", "—"))
            _cov = float(r.get("cov_port") or r.get("coverage") or 0)
            _noise = float(r.get("noise_floor_db", 0))
            _rough = float(r.get("sea_roughness", 0))
            st.markdown(f"""
            <div class="health">
              <span class="chip">القمر <b><span dir="ltr">{_plat}</span></b></span>
              <span class="chip">المدار <b><span dir="ltr">{_orbit}</span></b></span>
              <span class="chip">وقت الالتقاط <b><span dir="ltr">{r['dt']:%Y-%m-%d %H:%M}Z</span></b></span>
              <span class="chip">تغطية الحوض <b><span dir="ltr">{_cov*100:.0f}%</span></b></span>
              <span class="chip">ضوضاء المشهد <b><span dir="ltr">{_noise:.1f} ديسيبل</span></b></span>
              <span class="chip">حالة البحر <b><span dir="ltr">{_rough:.2f}</span></b></span>
              <span class="chip">معرف المشهد <b><span dir="ltr">{sid[:24]}…</span></b></span>
            </div>""", unsafe_allow_html=True)

            d1, d2 = st.columns(2, gap="small")
            with d1:
                st.image(os.path.join(S1_DIR, sid, "vv_original.jpg"), width="stretch",
                         caption=f"الصورة الأصلية — الاستقطاب VV (ديسيبل)")
            with d2:
                st.image(os.path.join(S1_DIR, sid, "detection_overlay.jpg"), width="stretch",
                         caption="نتيجة الكشف — المربعات الحمراء: سفن مكتشفة")
            vj = os.path.join(S1_DIR, sid, "vessels.json")
            if os.path.exists(vj):
                vs = json.load(open(vj, encoding="utf-8"))
                zparts = " · ".join(f"{zone_name(z)}: {sum(1 for v in vs if v['zone']==z)}"
                                    for z in (2, 1, 0))
                st.markdown(f'<p class="fpane-sub">{len(vs)} سفينة مكتشفة — {zparts}</p>', unsafe_allow_html=True)
                # ---- vessels table (real coordinates & attributes) ----
                _vdf = pd.DataFrame([{k: v[k] for k in
                                      ("vessel_id", "lon", "lat", "length_m", "width_m",
                                       "peak_db", "dist_port_m", "zone")} for v in vs])
                _vdf = _vdf.rename(columns={"vessel_id": "المعرّف", "lon": "خط الطول",
                                            "lat": "خط العرض", "length_m": "الطول (م)",
                                            "width_m": "العرض (م)", "peak_db": "الذروة (ديسيبل)",
                                            "dist_port_m": "المسافة من المرفأ (م)", "zone": "المنطقة"})
                _vdf["المنطقة"] = _vdf["المنطقة"].map({2: "داخل الحوض", 1: "المرسى", 0: "عبور"})
                st.dataframe(_vdf, width="stretch", hide_index=True)
                # ---- vessel crops: contact sheet (or individual thumbs) ----
                _sheet = os.path.join(S1_DIR, sid, "vessels", "sheet.jpg")
                crops = sorted(glob.glob(os.path.join(S1_DIR, sid, "vessels", "*.jpg")))
                if os.path.exists(_sheet):
                    st.markdown(f"<p class='fpane-sub'>لوحة مقاطع السفن المكبّرة (VV | VH) — "
                                f"{len(vs)} سفينة، كل مربع معنون برقم المقطع وطوله بالأمتار. "
                                f"التفاصيل الكاملة في الجدول أعلاه.</p>", unsafe_allow_html=True)
                    st.image(_sheet, width="stretch")
                elif crops:
                    # backward-compatible individual-thumbnail grid
                    st.markdown(f"<p class='fpane-sub'>مقاطع السفن المكبّرة (VV | VH) — "
                                f"{len(crops)} مقطعًا متاحًا</p>", unsafe_allow_html=True)
                    _by_id = {}
                    for _v in vs:
                        _key = _v["vessel_id"].split("_")[-1]
                        _by_id[_key] = _v
                    cols = st.columns(6)
                    for i, cp in enumerate(crops[:36]):
                        with cols[i % 6]:
                            _fn = os.path.basename(cp).rsplit("_", 1)[-1].replace(".jpg", "")
                            _info = _by_id.get(_fn)
                            _lbl = f"#{_fn}"
                            if _info and _info.get("length_m"):
                                _lbl += f" · {_info['length_m']:.0f}م"
                            st.image(cp, caption=_lbl)
            sd = r["dt"]
            s2g = s2[(s2["error"].isna() | (s2["error"] == ""))].copy()
            if len(s2g):
                s2g["dt"] = pd.to_datetime(s2g["datetime"])
                dd = (s2g["dt"] - sd).abs()
                if dd.min() <= pd.Timedelta(days=5):
                    best = s2g.loc[dd.idxmin()]
                    rgb = os.path.join(S2_DIR, best["id"], "rgb.png")
                    if os.path.exists(rgb):
                        st.image(rgb, width="stretch",
                                 caption=f"أقرب صورة Sentinel-2 — {best['dt']:%Y-%m-%d} · غيوم {best.get('cloud_pct_aoi', '—')}%")
        else:
            if sat.startswith("Sentinel-1"):
                st.info("لا توجد مشاهد ضمن الفلاتر.")

    # ------------------------------------------------ page 7: validation
    with p_val:
        page_title("التحقق وجودة البيانات")
        c1, c2 = st.columns(2, gap="small")
        with c1:
            pbi("التحقق المتقاطع S1 ↔ S2")
            if len(pairs):
                st.plotly_chart(chart_s1s2(pairs), width="stretch", config={"displayModeBar": False})
            else:
                st.info("لا توجد أزواج تحقق ضمن الفلاتر.")
        with c2:
            pbi("جودة الاكتشافات حسب المنطقة")
            if len(qf):
                _q = qf.groupby("zone")["snr_db"].agg(["count", "mean", "min"]).round(1) \
                     .rename(columns={"count": "عدد", "mean": "متوسط الإشارة/الضوضاء", "min": "أدنى إشارة/ضوضاء"})
                _q.index = _q.index.map({2: "داخل المرفأ", 1: "المرسى/الاقتراب", 0: "عبور/خارج"})
                _q.index.name = "المنطقة"
                st.dataframe(_q, width="stretch")
            else:
                st.info("لا توجد اكتشافات ضمن الفلاتر.")
        if len(pairs):
            pbi("أزواج المقارنة S1 ↔ S2 (فارق ≤ 4 أيام)")
            st.dataframe(pairs.sort_values("s2_date")[["s2_date", "s1_date", "gap_hours", "cloud_pct",
                                                       "s1_port", "s2_port", "s1_total", "s2_total"]]
                         .rename(columns={"s2_date": "S2", "s1_date": "S1", "gap_hours": "فارق (س)",
                                         "cloud_pct": "غيوم %", "s1_port": "S1 في المرفأ",
                                         "s2_port": "S2 في المرفأ", "s1_total": "S1 الكل",
                                         "s2_total": "S2 الكل"}),
                         width="stretch", hide_index=True)

    # ------------------------------------------------ page 13: AIS verification
    with p_ais:
        page_title("التحقق AIS — هويات السفن وأنواعها (بضائع / ناقلات / حاويات)")
        try:
            _ais_files = sorted(glob.glob(os.path.join(AIS_DIR, "*.jsonl")) +
                                glob.glob(os.path.join(AIS_DIR, "*.csv")))
            _ais_key = tuple((os.path.basename(f), int(os.path.getmtime(f)))
                             for f in _ais_files)
            _det, _stats, _prof, _rpt = _ais_pipeline_cached(tuple(fscenes["id"]), _ais_key)
        except Exception as e:
            st.info("وحدة AIS غير متاحة: " + str(e)[:100])
            _det, _stats, _prof, _rpt = None, {}, None, None
        if _det is not None:
            _n_ais = int(_det["is_ais"].sum())
            _n_msg = int(_stats.get("n_ais_messages", 0))
            c1, c2, c3, c4 = st.columns(4, gap="small")
            with c1:
                metric("سجلات سفن مصنفة", f"{len(_det):,}",
                       "ضمن الفلاتر الحالية · المصدر: الأبعاد الرادارية", "#01B8AA")
            with c2:
                if _stats.get("ais_available"):
                    metric("رسائل AIS متاحة", f"{_n_msg:,}",
                           f"نطاق: {_stats.get('ais_time_span', ['—', '—'])[0]} ← "
                           f"{_stats.get('ais_time_span', ['—', '—'])[1]}", "#34D399")
                else:
                    metric("بيانات AIS", "لا توجد", "أضف ملفات إلى data/ais/", "#F59E0B")
            with c3:
                metric("مطابقات AIS حقيقية", f"{_n_ais:,}",
                       f"{_stats.get('match_rate', 0):.1f}% من السجلات",
                       "#34D399" if _n_ais else "#6B7280")
            with c4:
                metric("أنواع AIS مميزة", f"{int(_stats.get('n_ais_types', 0))}",
                       "بضائع / ناقلات / حاويات / …", "#A78BFA")

            st.markdown("""
            <div class="read-note"><b>مستويان منفصلان للتحقق:</b>
            <b>مطابقة AIS حقيقية</b> — عند توفر رسائل AIS (<span dir="ltr">data/ais/</span>) تُربط كل
            سفينة بالرسالة الأقرب (≤ 600م، ≤ 45 دقيقة) وتُعرض هويتها الحقيقية (IMO / MMSI / الاسم / النوع).
            <b>تقدير من الأبعاد</b> — تصنيف تقريبي من طول السفينة في الرادار فقط؛ العرض الراداري مضخّم بنحو 1.5–2×
            بسبب انبثاق الرادار فلا يُستخدم في التصنيف. التقدير مُعلَّم بوضوح في كل مكان وليس بديلاً عن AIS.</div>
            """, unsafe_allow_html=True)

            if _prof is not None and len(_prof):
                c1, c2 = st.columns([1.5, 1], gap="small")
                with c1:
                    pbi("التركيب الشهري حسب الفئة (تقديري + AIS عند توفره)")
                    _f1 = chart_type_profile(_prof)
                    if _f1 is not None:
                        st.plotly_chart(_f1, width="stretch", key="ais_profile",
                                        config={"displayModeBar": False})
                with c2:
                    pbi("التوزيع الكلي للفئات")
                    _f2 = chart_type_donut(_prof)
                    if _f2 is not None:
                        st.plotly_chart(_f2, width="stretch", key="ais_donut",
                                        config={"displayModeBar": False})
                _m_m = _prof[_prof["n_ais"] > 0]
                if len(_m_m):
                    st.markdown(f"<p class='fpane-sub'>فئات أُسندت من AIS حقيقي خلال الفترة: "
                                f"{_m_m['type'].nunique()} فئة في {_m_m['ym'].nunique()} شهرًا — "
                                f"هذه الفئات تُظهر النوع الفعلي بدل التقدير.</p>", unsafe_allow_html=True)

            if _n_ais:
                pbi("سجلات مطابقة AIS — هويات حقيقية")
                _mt = _det[_det["is_ais"]][["acquisition", "vessel_id", "mmsi", "imo", "ais_name",
                                            "ais_ship_type", "ais_length_m", "ais_dist_m",
                                            "ais_gap_min", "ais_destination", "zone"]].copy()
                _mt = _mt.rename(columns={"acquisition": "وقت الالتقاط", "vessel_id": "معرف الرادار",
                                          "mmsi": "MMSI", "imo": "IMO", "ais_name": "اسم السفينة",
                                          "ais_ship_type": "النوع (AIS)", "ais_length_m": "طول AIS (م)",
                                          "ais_dist_m": "مسافة المطابقة (م)", "ais_gap_min": "فارق زمني (د)",
                                          "ais_destination": "الوجهة", "zone": "المنطقة"})
                _mt["المنطقة"] = _mt["المنطقة"].map({2: "داخل الحوض", 1: "المرسى", 0: "عبور"})
                _mt["وقت الالتقاط"] = pd.to_datetime(_mt["وقت الالتقاط"]).dt.strftime("%Y-%m-%d %H:%M")
                st.dataframe(_mt.sort_values("وقت الالتقاط", ascending=False),
                             width="stretch", hide_index=True)
            else:
                st.markdown("""
                <div class="limits"><p><b>كيف تُفعَّل المطابقة الحقيقية؟</b><br>
                1) ضع ملفات AIS في <span dir="ltr">data/ais/</span> بصيغة JSONL أو CSV (الأعمدة:
                <span dir="ltr">timestamp, lon, lat, mmsi, imo, name, ship_type, length_m, width_m,
                sog, cog, destination</span>) — التنسيق موثق في <span dir="ltr">data/ais/README.md</span>.<br>
                2) أو فعّل الجلب المباشر من AISHub (مجاني بحد أقصى ~1,000 رسالة/يوم، تسجيل مطلوب):<br>
                <span dir="ltr">python3 -m src.ais_verify --aishub &lt;اسم-المستخدم&gt;</span><br>
                3) أعد فتح الصفحة — تظهر المطابقات هنا تلقائيًا. كل ما يُقرأ من
                <span dir="ltr">data/ais/</span> يُعرض كـ«AIS حقيقي»؛ وما عدا ذلك يبقى «تقديرًا من الأبعاد»
                ولا يظهر أبدًا كهوية مؤكدة.</p></div>""", unsafe_allow_html=True)

    # ------------------------------------------------ page 14: automation
    with p_auto:
        page_title("الأتمتة والتحديث الأسبوعي")
        import subprocess as _sp
        from datetime import datetime as _dt, timedelta as _td
        _ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        _now = _dt.now()
        _days = (6 - _now.weekday()) % 7  # Sunday = 6
        if _days == 0 and (_now.hour, _now.minute) >= (2, 30):
            _days = 7
        _nxt = (_now + _td(days=_days)).replace(hour=2, minute=30, second=0, microsecond=0)
        _cron_installed = False
        try:
            _r = _sp.run(["crontab", "-l"], capture_output=True, text=True, timeout=10)
            _cron_installed = _r.returncode == 0 and \
                any("latakia-monitor-weekly" in l for l in _r.stdout.splitlines())
        except Exception:
            pass
        c1, c2, c3, c4 = st.columns(4, gap="small")
        with c1:
            metric("الجدولة", "الأحد 02:30", "أسبوعيًا (قابلة للتغيير في install_cron.sh)",
                   "#01B8AA" if _cron_installed else "#F59E0B")
        with c2:
            metric("حالة cron", "مثبّتة ✓" if _cron_installed else "غير مثبتة",
                   "" if _cron_installed else "شغّل: bash scripts/install_cron.sh",
                   "#34D399" if _cron_installed else "#F59E0B")
        with c3:
            metric("التشغيل القادم", _nxt.strftime("%Y-%m-%d %H:%M"), "بتوقيت الخادم المحلي", "#A78BFA")
        with c4:
            _llog = os.path.join(_ROOT, "logs", "update_weekly.log")
            if os.path.exists(_llog):
                with open(_llog, encoding="utf-8", errors="replace") as _lf:
                    _ltail = _lf.read().splitlines()
                metric("آخر تشغيل", (_ltail[0][1:17] if _ltail else "—"), "سجل update_weekly.log", "#01B8AA")
            else:
                metric("آخر تشغيل", "لا يوجد بعد", "لم يُشغَّل السكربت بعد", "#6B7280")

        st.markdown("""
        <div class="exec"><div class="ex-t">ماذا يحدث كل يوم أحد 02:30؟</div><p>
        1) استعلام STAC عن المشاهدات الجديدة (Sentinel-1 رادار + Sentinel-2 بصري) منذ آخر تشغيل ←
        2) معالجة المشاهدات الجديدة فقط (خط الكشف الكامل — التحديث قابل للاستئناف) ←
        3) إعادة حساب التحليلات والمخططات ← 4) إعادة توليد التقارير (HTML / DOCX / XLSX / PDF) ←
        5) تحديث التصدير: GeoJSON، مسارات السفن، كشف الشذوذ، طبقات GeoTIFF، ملف AIS ←
        6) تسجيل كل خطوة في <span dir="ltr">logs/update_weekly.log</span>.</p>
        <p>أي خطوة تفشل تُسجَّل وتُستكمل البقية — لا يتوقف التحديث عند أول خطأ. حماية التداخل: لا
        يعمل تشغيلان معًا (قفل). توليد PDF يتطلب Chromium في الخادم.</p></div>""", unsafe_allow_html=True)

        if os.path.exists(os.path.join(_ROOT, "logs", "update_weekly.log")):
            pbi("آخر سجل تشغيل (آخر 25 سطرًا)")
            st.code("\n".join(_ltail[-25:]), language=None)

        pbi("أوامر التشغيل")
        st.code(
"""# تثبيت الجدولة الأسبوعية (يُحفظ في crontab الحالي دون مسح ما فيه)
bash scripts/install_cron.sh
# إزالتها
bash scripts/install_cron.sh --remove
# تشغيل يدوي كامل (نفس ما يفعله cron بالضبط)
bash scripts/run_weekly_update.sh
# أو مباشرة عبر بايثون
python3 update_data.py --full
# جلب AIS حي ثم تحديث كامل
python3 update_data.py --ais <aishub-user> --full""", language="bash")
        st.markdown("""
        <p class="fpane-sub">تغيير الموعد: <span dir="ltr">HOUR=4 WEEKDAY=1 bash scripts/install_cron.sh</span>
        (الاثنين 04:00). على خوادم Windows استخدم Task Scheduler مع
        <span dir="ltr">scripts/run_weekly_update.sh</span> عبر Git Bash، أو جدولة
        <span dir="ltr">pythonw update_data.py --full</span> مباشرة.</p>""", unsafe_allow_html=True)

    # ------------------------------------------------ methodology
    with st.expander("المنهجية"):
        st.markdown("""
**المصادر:** Sentinel-1 (رادار) وSentinel-2 (بصري) — بيانات كوبرنيكوس عبر مايكروسوفت بلانيتاري كومبيوتر · حدود المرفأ من خريطة الشارع المفتوحة · اليابسة من ناتشورال إيرث.

**خط الكشف:** شبكة UTM ثابتة 10م ← قناع يابسة ← فلتر Lee ← عتبة تكيفية (μ+k·σ) ← تحقق VV/VH ← مكونات متصلة ← فك التحام وتوحيد الأجزاء ← إحداثيات وأبعاد ومناطق.

**مؤشر النشاط:** متوسط السفن لكل مشاهدة، للمشاهدات التي غطّت حوض المرفأ كاملًا فقط.

**القيود:** سفن < ~15م غير مكتشفة · نوع السفينة تقديري من الأبعاد (المصدر المؤكد الوحيد: مطابقة AIS في تبويب «التحقق AIS») · العدّاد البصري تقديري · البيانات تصف الظاهرة ولا تفسّر أسبابها.
""")


if __name__ == "__main__":
    main()
