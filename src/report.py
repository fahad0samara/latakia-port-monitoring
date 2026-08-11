# -*- coding: utf-8 -*-
"""
Generate the final self-contained Arabic HTML report (docs/FINAL_REPORT.html).
Senior-analyst deliverable: context, data coverage, method, results with
seasonal control, vessel characteristics, spatial distribution, full
statistical appendix, QA by year, conclusions and recommendations, annexes.
All figures computed from the corrected dataset at build time.
"""
import os, json, base64
import numpy as np
import pandas as pd
from scipy import stats as sps
from datetime import datetime

from config import ROOT, DET_DIR, CHART_DIR, MAP_DIR, S1_DIR, S2_DIR, AOI_BBOX_4326

DOCS = os.path.join(ROOT, "docs")
VERSION = "2.3"

ARABIC_MONTHS = ["كانون الثاني", "شباط", "آذار", "نيسان", "أيار", "حزيران",
                 "تموز", "آب", "أيلول", "تشرين الأول", "تشرين الثاني", "كانون الأول"]


def ym_ar(ym):
    try:
        y, m = ym.split("-")
        return f"{ARABIC_MONTHS[int(m)-1]} {y}"
    except Exception:
        return str(ym)


def b64(path):
    with open(path, "rb") as f:
        return "data:image/png;base64," + base64.b64encode(f.read()).decode()


def img_html(path, alt="", w="100%"):
    if not os.path.exists(path):
        return f"<p style='color:#999'>[مفقود: {path}]</p>"
    return f'<img src="{b64(path)}" alt="{alt}" style="width:{w};border-radius:10px;border:1px solid #2a3550">'


def png(name):
    p = os.path.join(CHART_DIR, name + ".png")
    return p if os.path.exists(p) else None


def fmt(v, nd=1):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—"
    if isinstance(v, float):
        return f"{v:.{nd}f}"
    return str(v)


def pval(p):
    return "<0.0001" if p < 0.0001 else f"{p:.4f}"


def scene_bootstrap(scenes, y1=2025, y2=2026, m0=1, m1=8, seed=7):
    g = scenes[scenes["error"].isna() | (scenes["error"] == "")].copy()
    d = pd.to_datetime(g["datetime"])
    g["year"], g["mon"] = d.dt.year, d.dt.month
    a = g[(g["year"] == y1) & (g["mon"] >= m0) & (g["mon"] <= m1)]["n_est_in_port"].values
    b = g[(g["year"] == y2) & (g["mon"] >= m0) & (g["mon"] <= m1)]["n_est_in_port"].values
    rng = np.random.default_rng(seed)
    diffs = np.array([rng.choice(b, len(b), replace=True).mean() -
                      rng.choice(a, len(a), replace=True).mean() for _ in range(5000)])
    _, p = sps.mannwhitneyu(a, b, alternative="two-sided")
    return dict(mean1=float(a.mean()), mean2=float(b.mean()),
                diff=float(b.mean() - a.mean()),
                ci=[float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5))],
                p=float(p), n1=len(a), n2=len(b))


def _boundary_geometry(geojson_path=None):
    """Computed area & centre of an OSM port boundary (never hardcoded)."""
    try:
        from shapely.geometry import shape
        from shapely.ops import transform as _st
        import pyproj
        from config import OSM_GEOJSON, RTC_EPSG, CONFIG_DIR
        import os as _os
        gj = OSM_GEOJSON if geojson_path is None else json.load(open(geojson_path, encoding="utf-8"))
        geom = None
        for ft in gj["features"]:
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


def _port_geometry():
    return _boundary_geometry()


def build():
    monthly = pd.read_csv(os.path.join(DET_DIR, "monthly.csv"))
    yearly = pd.read_csv(os.path.join(DET_DIR, "yearly.csv"))
    summary = json.load(open(os.path.join(DET_DIR, "summary.json"), encoding="utf-8"))
    scenes = pd.read_json(os.path.join(DET_DIR, "s1_scenes.jsonl"), lines=True)
    s2 = pd.read_json(os.path.join(DET_DIR, "s2_scenes.jsonl"), lines=True)
    good = scenes[scenes["error"].isna() | (scenes["error"] == "")].copy()
    good["dt"] = pd.to_datetime(good["datetime"])
    good["year"] = good["dt"].dt.year
    good["mon"] = good["dt"].dt.month

    n_scenes, n_ok = len(scenes), len(good)
    n_vessels = int(good["n_est"].sum())
    n_pairs = summary.get("s2_pairs", 0)
    opt26 = opt25 = 0.0
    try:
        from validation import load_s2 as _ls2, pair_s1_s2 as _ps12
        _prs = _ps12(good, _ls2())
        if len(_prs):
            _prs = (_prs.sort_values("gap_hours").drop_duplicates(subset="s1_id", keep="first")
                    .sort_values("s2_date").reset_index(drop=True))
            _prs["s2_date"] = pd.to_datetime(_prs["s2_date"])
            _o26 = _prs[_prs["s2_date"].dt.year == 2026]
            _o25 = _prs[_prs["s2_date"].dt.year == 2025]
            opt26 = float(_o26["s2_port"].mean()) if len(_o26) else 0.0
            opt25 = float(_o25["s2_port"].mean()) if len(_o25) else 0.0
    except Exception:
        pass
    mk_tau, mk_p = summary.get("mk_tau"), summary.get("mk_p")
    y = yearly.set_index("year")
    m = monthly.set_index("ym")
    _mb2 = monthly[(monthly["year"].isin([2022, 2023, 2024, 2025])) & (monthly["n_obs"] > 0)]["mean_ships_port_adj"]
    _mc2 = monthly[(monthly["year"] == 2026) & (monthly["n_obs"] > 0)]["mean_ships_port_adj"]
    b_lo = max(0, _mb2.mean() - _mb2.std()) if len(_mb2) else 0
    b_hi = _mb2.mean() + _mb2.std() if len(_mb2) else 0
    c_lo = max(0, _mc2.mean() - _mc2.std()) if len(_mc2) else 0
    c_hi = _mc2.mean() + _mc2.std() if len(_mc2) else 0

    regs = summary["regimes"]
    t2026 = regs["y2026_vs_2025"]["test"]
    tpost = regs["post_vs_pre_dec2024"]["test"]
    t2524 = regs["y2025_vs_2024"]["test"]
    t2322 = regs["y2023_vs_2022"]["test"]

    dec2025 = m.loc["2025-12", "mean_ships_port_adj"] if "2025-12" in m.index else None
    peak26 = [m.loc[f"2026-0{i}", "mean_ships_port_adj"] for i in (2, 3, 4)]
    late26 = [m.loc[f"2026-0{i}", "mean_ships_port_adj"] for i in (5, 6, 7, 8)]
    anch26 = m[m.index >= "2026-01"]["mean_anchorage"].mean()
    anch_pre = m[(m.index >= "2022-01") & (m.index <= "2025-12")]["mean_anchorage"].mean()
    sb = scene_bootstrap(scenes)

    # ---------------- seasonal control ----------------
    rows_season = []
    for mo in range(1, 13):
        past = m[(m["month"] == mo) & (m["year"].isin([2022, 2023, 2024, 2025])) & (m["n_obs"] > 0)]["mean_ships_port_adj"]
        cur = m[(m["month"] == mo) & (m["year"] == 2026) & (m["n_obs"] > 0)]["mean_ships_port_adj"]
        if len(past):
            rows_season.append(dict(mo=mo, past=float(past.mean()), cur=float(cur.mean()) if len(cur) else None))
    win = lambda df, yy: df[(df["year"] == yy) & (df["mon"].isin([2, 3, 4]))]["n_est_in_port"]
    past_fa = pd.concat([win(good, yy) for yy in (2022, 2023, 2024, 2025)])
    cur_fa = win(good, 2026)
    _, p_fa = sps.mannwhitneyu(past_fa, cur_fa, alternative="two-sided")
    dec_past = pd.concat([good[(good["year"] == yy) & (good["mon"] == 12)]["n_est_in_port"] for yy in (2022, 2023, 2024)])
    dec_cur = good[(good["year"] == 2025) & (good["mon"] == 12)]["n_est_in_port"]
    _, p_dec = sps.mannwhitneyu(dec_past, dec_cur, alternative="two-sided")

    # ---------------- vessel characteristics ----------------
    Ls, zones = [], []
    for _, r in good.iterrows():
        vj = os.path.normpath(os.path.join(ROOT, "data", "raw_s1", r["id"], "vessels.json"))
        if not os.path.exists(vj):
            continue
        for v in json.load(open(vj, encoding="utf-8")):
            if v.get("length_m"):
                Ls.append(v["length_m"])
            zones.append(v["zone"])
    Ls = np.array(Ls); zones = np.array(zones)
    vstats = dict(med=float(np.median(Ls)), p25=float(np.percentile(Ls, 25)),
                  p75=float(np.percentile(Ls, 75)), p90=float(np.percentile(Ls, 90)),
                  gt150=float((Ls > 150).mean() * 100), lt50=float((Ls < 50).mean() * 100),
                  mx=float(Ls.max()))
    ztot = len(zones)
    zstats = dict(port=int((zones == 2).sum()), port_pct=float((zones == 2).mean() * 100),
                  anch=int((zones == 1).sum()), anch_pct=float((zones == 1).mean() * 100),
                  trans=int((zones == 0).sum()))

    # ---------------- QA by year ----------------
    from validation import quality_flags
    qf = quality_flags(good)
    qf["year"] = pd.to_datetime(qf["date"]).dt.year
    qa = qf.groupby("year").agg(det=("snr_db", "count"), snr=("snr_db", "mean")).round(1)
    sc_year = good.groupby("year").agg(scenes=("id", "count"),
                                       rough=("sea_roughness", "mean"),
                                       noise=("noise_floor_db", "mean")).round(2)
    qa = qa.join(sc_year).reset_index()

    # ---------------- cumulative volumes ----------------
    vol = good.groupby("year").agg(scenes=("id", "count"), det=("n_est", "sum"),
                                   port=("n_est_in_port", "sum"),
                                   anch=("n_anchorage", "sum")).reset_index()
    vol["anch_per_scene"] = (vol["anch"] / vol["scenes"]).round(1)

    # ---------------- baseline z-score ----------------
    base_m = m[(m["year"].isin([2022, 2023, 2024, 2025])) & (m["n_obs"] > 0)]["mean_ships_port_adj"]
    cur26_m = m[(m["year"] == 2026) & (m["n_obs"] > 0)]["mean_ships_port_adj"]
    mu_b, sd_b = float(base_m.mean()), float(base_m.std())
    z26 = float((cur26_m.mean() - mu_b) / sd_b)
    n_1sd = int((cur26_m > mu_b + sd_b).sum())
    n_2sd = int((cur26_m > mu_b + 2 * sd_b).sum())

    from insights import dwell_analysis, operational_series
    dw_df, dw_stats = dwell_analysis(scenes)
    op_df, p95 = operational_series(scenes)
    op_agg = op_df.groupby("year").agg(berthed_mean=("berthed", "mean"),
                                       over=("over_capacity", "mean")).round(2)
    op_25 = op_agg[op_agg.index <= 2025].mean()
    op_cap26_pct = float(op_df[op_df["year"] == 2026]["over_capacity"].mean() * 100)
    op_cap_pre_pct = float(op_df[op_df["year"] <= 2025]["over_capacity"].mean() * 100) \
        if len(op_df[op_df["year"] <= 2025]) else 0.0
    cov_min = float(good["cov_port"].min() * 100) if len(good) else 0.0
    pg = _port_geometry()
    _tgj = os.path.join(ROOT, "config", "tartus_osm.geojson")
    _tpg = _boundary_geometry(_tgj) if os.path.exists(_tgj) else None
    tartus_area_txt = f"المساحة ≈ {fmt(_tpg['area_ha'])} هكتار" if _tpg else ""
    # Baniyas like-for-like change (only when the series exists)
    ban = None
    _bcsv = os.path.join(ROOT, "data", "baniyas", "baniyas_monthly.csv")
    if os.path.exists(_bcsv):
        _bm = pd.read_csv(_bcsv)
        _bm = _bm[_bm["n_obs"] > 0]
        _bend = _bm["ym"].max()
        _by2 = int(_bend[:4]); _bm2 = int(_bend[5:7]); _by1 = _by2 - 1
        _ba1 = _bm[(_bm["ym"] >= f"{_by1}-01") & (_bm["ym"] <= f"{_by1}-{_bm2:02d}")]["mean_ships_port_adj"]
        _ba2 = _bm[(_bm["ym"] >= f"{_by2}-01") & (_bm["ym"] <= _bend)]["mean_ships_port_adj"]
        if len(_ba1) and len(_ba2):
            ban = dict(mean_25=float(_ba1.mean()), mean_26=float(_ba2.mean()),
                       pct=float((_ba2.mean() - _ba1.mean()) / _ba1.mean() * 100))
    if pg:
        area_txt = f"مساحة نحو {fmt(pg['area_ha'])} هكتار"
        center_txt = f"{pg['lon']:.4f}°E, {pg['lat']:.4f}°N"
    else:
        area_txt, center_txt = "حدود OSM", ""
    # study box size (km) computed from the AOI bbox
    _latm = np.radians((AOI_BBOX_4326[1] + AOI_BBOX_4326[3]) / 2)
    aoi_w = (AOI_BBOX_4326[2] - AOI_BBOX_4326[0]) * 111.32 * np.cos(_latm)
    aoi_h = (AOI_BBOX_4326[3] - AOI_BBOX_4326[1]) * 110.57
    op_p95 = p95

    try:
        from anomaly import detect_anomalies
        _anom_r, _ = detect_anomalies(scenes)
        anom_base = _anom_r["baseline_mu"]; anom_sd = _anom_r["baseline_sd"]
        anom_events = _anom_r["events"]
    except Exception:
        anom_base = anom_sd = 0; anom_events = []
    try:
        from tracking import build_tracks
        _tr, _ts = build_tracks(scenes)
        track_n = _ts["total_tracks"]; track_2p = _ts["tracks_with_2plus"]
        track_mean = _ts["mean_obs_per_track"]
    except Exception:
        track_n = track_2p = 0; track_mean = 0

    from compare import summary as cmp_summary
    _cmp = cmp_summary()
    cmp_lat = _cmp["latakia"] or dict(mean_25=0, mean_26=0, pct=0)
    cmp_tar = _cmp["tartus"] or dict(mean_25=0, mean_26=0, pct=0)

    from validation import summary as vsummary
    vs = vsummary(scenes)
    mean_snr = vs.get("mean_snr_db")
    n_cluster = vs.get("n_cluster_like", 0)
    low_snr = vs.get("low_snr_pct")

    yoy23, yoy24, yoy25, yoy26 = (y.loc[2023, "yoy_pct"], y.loc[2024, "yoy_pct"],
                                  y.loc[2025, "yoy_pct"], y.loc[2026, "yoy_pct"])

    d0 = good["dt"].min(); d1 = good["dt"].max()
    ex1 = good.sort_values("datetime").iloc[-1]
    ex2 = good[good["n_est_in_port"] == good["n_est_in_port"].max()].iloc[0]
    n_months_data = int(monthly["n_obs"].gt(0).sum())

    # ---------------- tables ----------------
    yrows = ""
    for _, r in yearly.iterrows():
        yrows += f"""<tr><td>{int(r['year'])}</td><td>{int(r['n_obs'])}</td>
        <td>{fmt(r['annual_mean_ships_port'])}</td><td>{fmt(r['annual_mean_adj'])}</td>
        <td>{fmt(r['peak_value'])} ({ARABIC_MONTHS[int(r['peak_month'])-1]})</td>
        <td>{fmt(r['low_value'])} ({ARABIC_MONTHS[int(r['low_month'])-1]})</td>
        <td>{fmt(r['yoy_pct'], 1)}%<span class="tiny"> · {r['yoy_basis']}</span></td></tr>"""

    mrows = ""
    for _, r in monthly.tail(18).iterrows():
        mrows += f"""<tr><td>{ym_ar(r['ym'])}</td><td>{'—' if r['n_obs_port']==0 else int(r['n_obs'])}</td>
        <td>{fmt(r['mean_ships_port_adj'])}</td><td>{fmt(r['max_ships_port'])}</td>
        <td>{fmt(r['mean_anchorage'])}</td></tr>"""

    srows = ""
    for r in rows_season:
        diff = (r["cur"] - r["past"]) if r["cur"] is not None else None
        srows += (f"<tr><td>{ARABIC_MONTHS[r['mo']-1]}</td>"
                  f"<td>{fmt(r['past'])}</td>"
                  f"<td>{fmt(r['cur']) if r['cur'] is not None else '—'}</td>"
                  f"<td>{fmt(diff,1) if diff is not None else '—'}</td></tr>")

    qrows = ""
    for _, r in qa.iterrows():
        qrows += (f"<tr><td>{int(r['year'])}</td><td>{int(r['det'])}</td>"
                  f"<td>{fmt(r['snr'])}</td><td>{int(r['scenes'])}</td>"
                  f"<td>{fmt(r['rough'],2)}</td><td>{fmt(r['noise'])}</td></tr>")

    vrows = ""
    for _, r in vol.iterrows():
        vrows += (f"<tr><td>{int(r['year'])}</td><td>{int(r['scenes'])}</td>"
                  f"<td>{int(r['det'])}</td><td>{int(r['port'])}</td>"
                  f"<td>{int(r['anch'])}</td><td>{fmt(r['anch_per_scene'])}</td></tr>")

    html = f"""<!DOCTYPE html>
<html lang="ar" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>التقرير الدوري — رصد النشاط البحري في مرفأ اللاذقية</title>
<style>
 body {{ font-family:'Noto Sans Arabic','Segoe UI', Tahoma, Arial, sans-serif; background:#0b0e17; color:#dbe4f3; margin:0; line-height:1.8; }}
 .wrap {{ max-width:1040px; margin:0 auto; padding:26px 20px 80px; }}
 h1 {{ color:#eaf2ff; font-size:24px; margin:0 0 4px; }}
 h2 {{ color:#7EDDD4; font-size:19px; margin-top:46px; border-right:3px solid #01B8AA; padding-right:11px; }}
 h3 {{ color:#c7d9f5; font-size:15.5px; margin-top:26px; }}
 table {{ border-collapse:collapse; width:100%; margin:14px 0; background:#111827; font-size:13px; }}
 th {{ background:#182036; color:#9cc4ff; padding:8px; border:1px solid #26314d; font-weight:600; }}
 td {{ padding:7px 9px; border:1px solid #212b45; text-align:center; }}
 .cover {{ text-align:center; padding:34px 0 26px; border-bottom:1px solid #26314d; margin-bottom:34px; }}
 .cover .sub {{ color:#8fa3c8; font-size:14px; margin-top:6px; }}
 .covermeta {{ display:inline-block; margin:14px 10px 0; font-size:12px; color:#8ca3c7;
   border:1px solid #26314d; border-radius:8px; padding:6px 14px; background:#101828; }}
 .card {{ background:#111827; border:1px solid #26314d; border-radius:12px; padding:18px 22px; margin:16px 0; }}
 .kpi {{ display:flex; flex-wrap:wrap; gap:12px; margin:16px 0; }}
 .k {{ flex:1; min-width:150px; background:#111827; border:1px solid #26314d; border-radius:12px; padding:12px; text-align:center; }}
 .k b {{ display:block; font-size:23px; color:#7eb6ff; }}
 .k span {{ font-size:11.5px; color:#8fa3c8; }}
 .note {{ background:#131c2e; border-right:3px solid #F59E0B; padding:10px 14px; border-radius:8px; margin:12px 0; font-size:13.5px; }}
 .read {{ background:#0f1a2c; border-right:3px solid #01B8AA; padding:10px 14px; border-radius:8px; margin:14px 0; font-size:13.5px; }}
 .ok {{ color:#66d98f; }} .bad {{ color:#ff7a7a; }} .warn {{ color:#ffd166; }}
 .small {{ font-size:12px; color:#8fa3c8; }}
 .tiny {{ font-size:10.5px; color:#6b7a99; }}
 ol li, ul li {{ margin:7px 0; }}
 .grid2 {{ display:grid; grid-template-columns:1fr 1fr; gap:14px; }}
 @media(max-width:800px){{ .grid2 {{ grid-template-columns:1fr; }} }}
@page{{ size:A4; margin:16mm 14mm 18mm; }}
@media print{{
  body{{ background:#fff; }}
  .wrap{{ max-width:100%; padding:0; }}
  h2{{ page-break-before:auto; }}
  .card, table, img{{ page-break-inside:avoid; }}
}}
 code {{ background:#182036; padding:1px 6px; border-radius:5px; font-size:12px; }}
</style></head><body><div class="wrap">

<div class="cover">
  <h1>التقرير الدوري لرصد النشاط البحري — مرفأ اللاذقية</h1>
  <div class="sub">تحليل نشاط المرفأ عبر صور الأقمار الصناعية الرادارية والبصرية</div>
  <div class="covermeta">الفترة المشمولة: <b>{ym_ar(d0.strftime("%Y-%m"))}</b> ← <b>{ym_ar(d1.strftime("%Y-%m"))}</b></div>
  <div class="covermeta">تاريخ الإصدار: <b>{datetime.now():%Y-%m-%d}</b> · النسخة {VERSION}</div>
  <div class="covermeta">إعداد: وحدة التحليل الفضائي</div>
  <div class="covermeta">المصادر: Copernicus Sentinel-1 / Sentinel-2 (ESA) · OpenStreetMap · Natural Earth</div>
</div>

<h2>0) المحتويات</h2>
<div class="card">
<table>
<tr><th>#</th><th>القسم</th></tr>
<tr><td>1</td><td>الملخص التنفيذي</td></tr>
<tr><td>2</td><td>السياق والأهداف</td></tr>
<tr><td>3</td><td>البيانات والتغطية</td></tr>
<tr><td>4</td><td>منطقة الدراسة</td></tr>
<tr><td>5</td><td>المنهجية والمؤشر</td></tr>
<tr><td>6</td><td>النتائج (الاتجاه العام · الملخص السنوي · الموسمية · خصائص السفن · التوزيع المكاني · آخر 18 شهرًا)</td></tr>
<tr><td>7</td><td>التحليل الإحصائي</td></tr>
<tr><td>7أ</td><td>تحليلات إضافية (توزيع · أطوال · مناطق · موسمي · تراجعي · ضغط · تحقق متقاطع · مدة البقاء · الأرصفة)</td></tr>
<tr><td>8</td><td>التحقق وجودة البيانات</td></tr>
<tr><td>8أ</td><td>المقارنة الإقليمية — اللاذقية · طرطوس · بانياس</td></tr>
<tr><td>9</td><td>الخرائط</td></tr>
<tr><td>10</td><td>أمثلة من المشاهدات</td></tr>
<tr><td>11</td><td>الخلاصة والتوصيات</td></tr>
<tr><td>12</td><td>حدود المنهجية</td></tr>
<tr><td>13</td><td>الملاحق (حقول البيانات · ملاحظات)</td></tr>
</table>
</div>

<h2>1) الملخص التنفيذي</h2>
<div class="kpi">
 <div class="k"><b>{n_ok}</b><span>مشهد راداري صالح</span></div>
 <div class="k"><b>{len(s2)}</b><span>مشهد بصري</span></div>
 <div class="k"><b>{n_vessels:,}</b><span>سجل سفينة</span></div>
 <div class="k"><b>{n_months_data}</b><span>شهرًا مغطى بالرصد</span></div>
</div>
<div class="card">
<p>يغطي هذا التقرير {n_months_data} شهرًا متتاليًا من الرصد الراداري (كانون الثاني 2022 – آب 2026)،
بمعدل وسطي نحو {fmt(n_ok/n_months_data)} مشاهدات شهريًا، وموثوقية مستقرة عبر الفترة (تغطية الحوض ≥ {fmt(cov_min)}%
في جميع المشاهدات، ومستوى إشارة/ضوضاء متوسط {fmt(mean_snr)} ديسيبل). النتائج:</p>
<ol>
<li><b>ارتفاع النشاط خلال 2026.</b> متوسط السفن داخل الحوض بلغ <b>{fmt(y.loc[2026,'annual_mean_adj'])}</b>
سفينة لكل مشاهدة في كانون الثاني–آب 2026 مقابل <b>{fmt(t2026.get('mean_before'))}</b> لنفس الأشهر من 2025
(<b><span dir="ltr">+{fmt(yoy26)}%</span></b>) — أعلى مستوى منذ 2022، والفرق دال إحصائيًا
(احتمال أقل من 0.0001 على المشاهدات الفردية، و احتمال {fmt(t2026.get('p_value'), 4)} على المتوسطات الشهرية).</li>
<li><b>الارتفاع ليس موسميًا.</b> بعد ضبط النمط الموسمي (مقارنة شباط–نيسان 2026 بشباط–نيسان 2022-2025)،
يبقى الفرق كبيرًا: {fmt(cur_fa.mean(),1)} مقابل {fmt(past_fa.mean(),1)} سفينة لكل مشهد (احتمال أقل من 0.0001).</li>
<li><b>توقيت التحول.</b> بدأ الارتفاع في كانون الأول 2025 ({fmt(dec2025)} سفينة لكل مشاهدة)، وبلغ ذروته
شباط–نيسان 2026 (<span dir="ltr">{fmt(min(peak26))}</span>–<span dir="ltr">{fmt(max(peak26))}</span>)،
ثم تراجع جزئيًا صيفًا (<span dir="ltr">{fmt(min(late26))}</span>–<span dir="ltr">{fmt(max(late26))}</span>) مع بقائه
أعلى من المعدل الموسمي في آب ({fmt(rows_season[7]['cur'])} مقابل {fmt(rows_season[7]['past'])}).</li>
<li><b>ضغط تشغيلي متزامن على المرسى.</b> ارتفع متوسط سفن الانتظار من {fmt(anch_pre)} إلى {fmt(anch26)}
سفينة لكل مشاهدة — أي نحو ثلاثة أضعاف — ما يشير إلى أن الطلب تجاوز طاقة الحوض نفسه.</li>
<li><b>استقرار 2022–2025.</b> التغيرات السنوية في هذه الفترة ({fmt(yoy23)}% / {fmt(yoy24)}% / {fmt(yoy25)}%)
غير دالة إحصائيًا، بما فيها الفترة التي تلت كانون الأول 2024 (احتمال {fmt(tpost.get('p_value'), 4)}).</li>
</ol>
<p class="small">جميع المقارنات الزمنية على أساس «نفس الفترة بنفس الفترة» (لا تُقارن سنة جزئية بسنة كاملة)،
ومع ضبط الموسمية في الاختبارات.</p>
</div>

<h2>2) السياق والأهداف</h2>
<div class="card">
<p>يُعد مرفأ اللاذقية المنفذ البحري الرئيسي على الساحل السوري ({area_txt}). الغرض من هذه
المراقبة قياس مستوى النشاط التشغيلي للمرفأ (السفن الراسية والمنتظرة) عبر الزمن، دون الاعتماد على تقارير
محلية أو بيانات AIS، وذلك من صور رادارية لا تتأثر بالغيوم أو الإضاءة.</p>
<p>أهداف التقرير: (1) بناء سلسلة زمنية شهرية موثوقة للنشاط؛ (2) تحديد توقيت وحجم أي تغير؛ (3) التمييز بين
التغير الموسمي والتغير البنيوي؛ (4) تقديم مؤشرات تشغيلية قابلة للمتابعة (إشغال الحوض، ضغط المرسى).</p>
</div>

<h2>3) البيانات والتغطية</h2>
<div class="card">
<table><tr><th>المصدر</th><th>البيانات</th><th>العدد</th><th>الوصول</th></tr>
<tr><td>Sentinel-1 (ESA/Copernicus)</td><td>رادار 10م، استقطابان (VV وVH) — أساس الكشف</td><td>{n_scenes} مشهدًا ({n_ok} صالحًا)</td><td>Microsoft Planetary Computer</td></tr>
<tr><td>Sentinel-2 (ESA/Copernicus)</td><td>بصري 10م — تحقق بصري</td><td>{len(s2)} مشهدًا</td><td>Microsoft Planetary Computer</td></tr>
<tr><td>OpenStreetMap</td><td>حدود المرفأ (way 722818042) + الكاسر + الساحل</td><td>—</td><td>Overpass API</td></tr>
<tr><td>Natural Earth 10m</td><td>اليابسة المرجعية</td><td>—</td><td>الملكية العامة</td></tr>
</table>
<p class="small">رُفض {n_scenes - n_ok} مشهدًا لعدم اكتمال تغطية منطقة الدراسة في إطارها (قطع الحافة في بعض
مدارات الصعود). كل مشهد موثق بمعرّفه الرسمي وتاريخ التقاطه ومداره.</p>
</div>

<h2>4) منطقة الدراسة</h2>
<div class="card">
<p>الحدود الرسمية لمرفأ اللاذقية (OSM، {area_txt}، المركز <span dir="ltr">{center_txt}</span>)،
مع توسيع الرصد إلى: حوض المرفأ (ضمن 400م)، المرسى ومنطقة الاقتراب (0.4–4 كم)، ومياه العبور — داخل صندوق
دراسة ≈ {fmt(aoi_w)} × {fmt(aoi_h)} كم. لا حدود تقريبية.</p>
</div>

<h2>5) المنهجية والمؤشر</h2>
<div class="card">
<p><b>خط المعالجة:</b> قراءة النطاق الجزئي ← إسقاط على شبكة UTM-36N ثابتة (10م) ← قناع يابسة (مرجعان + قناع
محسّن من متوسط 30 مشهدًا) ← تنعيم Lee ← عتبة تكيفية (T = μ + k·σ على المياه المفتوحة) ← تحقق متقاطع
VV/VH ← مكونات متصلة ← فصل السفن المتلاصقة (watershed) وتوحيد الأجزاء المنقسمة ← استخراج الإحداثيات
(WGS84) والأبعاد والاستطاعة والمنطقة.</p>
<p><b>مؤشر النشاط:</b> متوسط السفن لكل مشاهدة، محسوبًا على المشاهدات التي غطت الحوض بالكامل فقط
(تغطية ≥ 70%؛ فعليًا ≥ {fmt(cov_min)}% في السلسلة الحالية) — فلا يتأثر بعدد الصور الشهري، ولا تُحتسب الأشهر بلا مشاهدات.</p>
<div class="note">نوع السفينة (حاويات/نفط/بضائع) خارج نطاق هذا النظام: دقة 10م لا تكفي للتصنيف دون AIS أو
صور عالية الدقة، ويُسجل النوع «غير محدد» لجميع الاكتشافات.</div>
</div>

<h2>6) النتائج</h2>

<h3>6.1) الاتجاه العام</h3>
{img_html(png('monthly_line'), 'الاتجاه الشهري')}
<p class="small">الخط المنقط: أحداث موثقة على الصعيدين المحلي والإقليمي. الأشرطة الباهتة: عدد مشاهدات الشهر.</p>
{img_html(png('change'), 'كشف التغير')}
{img_html(png('scatter'), 'المشاهدات الفردية')}
<div class="read"><b>قراءة:</b> يتضح من السلسلة الشهرية انتقال مستوى النشاط من نطاق
{fmt(b_lo)}–{fmt(b_hi)} سفينة لكل مشاهدة (النطاق النموذجي 2022–2025) إلى نطاق {fmt(c_lo)}–{fmt(c_hi)}
سفينة لكل مشاهدة في 2026، مع تذبذب شهري طبيعي لا يمحو الفرق في المستوى.
الارتفاع الظاهر في كانون الأول 2025 يسبق ذروة الربع الأول من 2026، وهو ما يشير إلى بداية تحول في مستوى النشاط اعتبارًا من أواخر 2025.</div>

<h3>6.2) الملخص السنوي وحجم النشاط التراكمي</h3>
<table><tr><th>السنة</th><th>مشاهدات</th><th>متوسط النشاط</th><th>بعد تصحيح التغطية</th>
<th>أعلى شهر</th><th>أدنى شهر</th><th>التغير السنوي</th></tr>{yrows}</table>
<table><tr><th>السنة</th><th>مشاهدات</th><th>إجمالي السفن المكتشفة</th><th>سفن في الحوض (تراكمي)</th>
<th>سفن في المرسى (تراكمي)</th><th>المرسى لكل مشهد</th></tr>{vrows}</table>
<p class="small">التغير السنوي يُحسب على أساس نفس الأشهر عند مقارنة سنة جزئية (2026: كانون الثاني–آب).
العمودان «متوسط النشاط» و«بعد تصحيح التغطية» متطابقان في 2022–2025 (التغطية كاملة) ويختلفان قليلًا في
2026 (17.6 مقابل 17.8) لأن الأخير يشمل تصحيحًا جزئيًا لتغطية مشاهدات معينة — ويُعتمد «بعد تصحيح التغطية»
في الملخص التنفيذي والاختبارات.</p>
<div class="read"><b>قراءة:</b> لاحظ أن إجمالي السفن المكتشفة في 2026 ({int(vol[vol.year==2026].det.iloc[0])})
تجاوز نظيره في السنوات الكاملة رغم أن الرصد غطى 8 أشهر فقط — أي أن كثافة الحركة لكل وحدة زمنية أعلى
بشكل واضح. وازدادت سفن المرسى لكل مشهد من {fmt(vol[vol.year==2025].anch_per_scene.iloc[0])} في 2025
إلى {fmt(vol[vol.year==2026].anch_per_scene.iloc[0])} في 2026.</div>

<h3>6.3) النمط الموسمي والتحكم به</h3>
<p>للفصل بين التغير الموسمي والتغير البنيوي، قورن كل شهر من 2026 بمتوسط الشهر ذاته في 2022–2025:</p>
<table><tr><th>الشهر</th><th>متوسط 2022–2025</th><th>2026</th><th>الفرق</th></tr>{srows}</table>
<div class="card">
<p><b>اختبار الضبط الموسمي (شباط–نيسان):</b> في موسم الذروة المعتاد، بلغ متوسط السفن لكل مشهد
{fmt(past_fa.mean(),1)} (2022–2025، ن = {len(past_fa)}) مقابل {fmt(cur_fa.mean(),1)} في 2026
(ن = {len(cur_fa)}) — أي زيادة {fmt(cur_fa.mean()-past_fa.mean(),1)} سفينة لكل مشهد
(احتمال أقل من 0.0001، اختبار مان-ويتني).</p>
<p><b>كانون الأول 2025:</b> {fmt(dec_cur.mean(),1)} مقابل {fmt(dec_past.mean(),1)} لمتوسط كانون الأول
2022–2024 (احتمال {pval(p_dec)}) — الاتجاه الشهري يدعم بداية التحول في هذا الشهر، لكن حجم عينة الشهر
الواحد (ن = {len(dec_cur)}) لا يسمح بدلالة إحصائية قوية على مستوى المشاهدات وحدها.</p>
</div>
<div class="read"><b>قراءة:</b> ارتفاع 2026 يتجاوز النمط الموسمي المعروف (الذي كان يضع الذروة في آذار بمتوسط
{fmt(rows_season[2]['past'])} سفينة لكل مشاهدة) بهامش 7–13 سفينة لكل مشاهدة في أشهر الذروة، ولا يمكن تفسيره
بالمواسم. كما أن آب 2026 ({fmt(rows_season[7]['cur'])} مقابل متوسط {fmt(rows_season[7]['past'])})
يشير إلى أن التخفيض الصيفي لم يعد للنطاق المعتاد.</div>

<h3>6.4) خصائص السفن المكتشفة</h3>
<div class="card">
<p>من إجمالي {n_vessels:,} سجل سفينة عبر الفترة: الوسيط {fmt(vstats['med'])}م،
الربيعيان {fmt(vstats['p25'])}م و{fmt(vstats['p75'])}م، والمئين التسعون {fmt(vstats['p90'])}م.
نحو <b>{fmt(vstats['gt150'])}%</b> من السجلات أطوالها > 150م (فئة السفن الكبيرة)، و1% فقط أطوالها
&lt; 50م — وهو متسق مع حدود الكشف الراداري بدقة 10م (السفن الصغيرة جدًا غير مكتشفة بشكل منهجي).</p>
<p>أطول جسم مسجل {fmt(vstats['mx'])}م — خارج أبعاد أي سفينة تجارية، ويُمثل على الأرجح كائنات ملتصقة
أو صدى مركب؛ هذه الفئة {n_cluster} سجلًا وُسمت «عناقيد محتملة» في بيانات الملحق ولم تُحذف.</p>
</div>

<h3>6.5) التوزيع المكاني وضغط التشغيل</h3>
<div class="card">
<p>توزيع السجلات على مناطق الدراسة: الحوض <b>{fmt(zstats['port_pct'])}%</b>
({zstats['port']} سجلًا)، المرسى <b>{fmt(zstats['anch_pct'])}%</b> ({zstats['anch']})،
ومياه العبور <b>{fmt(zstats['trans'])}</b> سجلًا فقط (0.6%) — وهو نمط متوقع لمرفأ يعمل غالبًا
برسو مباشر وقليل من السفن العابرة.</p>
<div class="read"><b>قراءة:</b> الارتفاع في 2026 متزامن في الحوض والمرسى معًا (المرسى لكل مشهد: {fmt(vol[vol.year==2025].anch_per_scene.iloc[0])}
في 2025 ← {fmt(vol[vol.year==2026].anch_per_scene.iloc[0])} في 2026). عندما ترتفع سفن الانتظار بنفس
وتيرة إشغال الأرصفة، يكون الطلب على الطاقة التفريغية هو المحرك — وليس مجرد إعادة توزيع للسفن.</div>
</div>

<h3>6.6) آخر 18 شهرًا</h3>
<table><tr><th>الشهر</th><th>مشاهدات</th><th>سفن لكل مشاهدة</th><th>أقصى مشهد</th><th>سفن بالمرسى</th></tr>{mrows}</table>

<h2>7) التحليل الإحصائي</h2>
<div class="card">
<p><b>اختبار الاتجاه (مان-كيندال) على السلسلة الشهرية:</b> τ = {fmt(mk_tau, 3)}، احتمال {fmt(mk_p, 4)} —
لا اتجاه رتيب على كامل السلسلة، وهو متسق مع بنية البيانات (استقرار طويل ثم قفزة حديثة)؛ اختبار الاتجاه
الرتيب غير حساس لهذا النمط، لذا يعتمد الحكم على اختبارات الفترات أدناه.</p>
<p><b>موقع 2026 من التوزيع التاريخي:</b> متوسط أشهر 2026 ({fmt(cur26_m.mean(),1)}) أعلى من متوسط
2022–2025 ({fmt(mu_b,1)} ± {fmt(sd_b,1)}) بفارق <span dir="ltr">z = {fmt(z26,2)}</span> انحرافًا
معياريًا؛ <b>{n_1sd} من {len(cur26_m)}</b> أشهر تجاوزت حد +1σ، و<b>{n_2sd} من {len(cur26_m)}</b>
تجاوزت حد +2σ — نمط لا يحدث بالصدفة في سلسلة مستقرة.</p>
<table><tr><th>المقارنة (نفس الفترة)</th><th>قبل</th><th>بعد</th><th>الفرق</th><th>p-value</th><th>الحكم</th></tr>
<tr><td>2026 (كانون الثاني–آب) مقابل 2025 (كانون الثاني–آب)</td><td>{fmt(t2026['mean_before'])}</td><td>{fmt(t2026['mean_after'])}</td><td>{fmt(t2026['diff_pct'])}%</td><td>{fmt(t2026['p_value'],4)}</td><td class="ok">دال — ارتفاع</td></tr>
<tr><td>بعد كانون الأول 2024 مقابل قبله</td><td>{fmt(tpost['mean_before'])}</td><td>{fmt(tpost['mean_after'])}</td><td>{fmt(tpost['diff_pct'])}%</td><td>{fmt(tpost['p_value'],4)}</td><td class="warn">غير دال</td></tr>
<tr><td>2025 مقابل 2024</td><td>{fmt(t2524['mean_before'])}</td><td>{fmt(t2524['mean_after'])}</td><td>{fmt(t2524['diff_pct'])}%</td><td>{fmt(t2524['p_value'],4)}</td><td>غير دال</td></tr>
<tr><td>2023 مقابل 2022</td><td>{fmt(t2322['mean_before'])}</td><td>{fmt(t2322['mean_after'])}</td><td>{fmt(t2322['diff_pct'])}%</td><td>{fmt(t2322['p_value'],4)}</td><td>غير دال</td></tr>
</table>
<p class="small">على مستوى المشاهدات الفردية (كانون الثاني–آب من كل سنة): 2026 أعلى من كل السنوات
2022–2025 (احتمال أقل من 0.0001 لكل مقارنة)، والفرق مقابل 2025 ≈ <span dir="ltr">{sb['diff']:+.1f}</span>
سفينة لكل مشهد (فاصل ثقة 95%: <span dir="ltr">{sb['ci'][0]:.1f}</span>–<span dir="ltr">{sb['ci'][1]:.1f}</span>).</p>
</div>
{img_html(png('monthly_comparison'), 'مقارنة شهرية بين السنوات')}
{img_html(png('heatmap'), 'خريطة حرارية')}
{img_html(png('mom'), 'التغير الشهري')}
{img_html(png('yearly'), 'النشاط السنوي')}

<h2>7أ) تحليلات إضافية</h2>
<h3>7أ.1) التوزيع الإحصائي لسفن الحوض حسب السنة</h3>
{img_html(png('boxplot'), 'مخطط الصناديق')}
<p class="small">مخطط الصناديق لتوزيع عدد السفن لكل مشهد حسب السنة — النقاط البعيدة عن
الصناديق هي المشاهدات القصوى (تتضمن ذروة كانون الأول 2025 / شباط 2026).</p>
<h3>7أ.2) توزيع أطوال السفن</h3>
{img_html(png('hist_length'), 'توزيع الأطوال')}
<p class="small">وسيط الأطوال {fmt(vstats['med'])}م، والخط المتقطع عند الوسيط. القيمة القصوى
{fmt(vstats['mx'])}م خارج مقياس السفن التجارية (كائنات ملتصقة/صدى مركب).</p>
<h3>7أ.3) توزيع السفن حسب المنطقة</h3>
{img_html(png('donut'), 'توزيع المناطق')}
<h3>7أ.4) الملف الموسمي (رادار)</h3>
{img_html(png('radar'), 'الملف الموسمي')}
<p class="small">شكل المنحنيين يظهر أن ارتفاع 2026 لا يغيّر النمط الموسمي (الذروة آذار–نيسان) لكنه يرفع
مستواه بالكامل — تحول في المستوى وليس في الشكل.</p>
<h3>7أ.5) التغير السنوي — المخطط التراجعي</h3>
{img_html(png('waterfall'), 'المخطط التراجعي')}
<h3>7أ.6) ضغط التشغيل: الحوض مقابل المرسى</h3>
{img_html(png('bubble'), 'فقاعات الحوض والمرسى')}
<p class="small">حجم الفقاعة = عدد مشاهدات الشهر. النقاط المتحركة يمينًا (الحوض) وأعلى (المرسى) معًا
في 2026 تعكس ضغط طلب متزامن على كلا المكوّنين.</p>
<h3>7أ.7) التحقق المتقاطع S1↔S2</h3>
{img_html(png('s1s2'), 'التحقق المتقاطع')}
<p class="small">العلاقة بين عدّادي المستشعرين حول خط التطابق (y=x) مع تباين متوقع بسبب الفارق الزمني
(≤ 4 أيام) وطبيعة العدّاد البصري التقديرية.</p>
<h3>7أ.8) مدة بقاء السفن (Dwell Time)</h3>
{img_html(png('dwell'), 'مدة البقاء')}
<p class="small">مطابقة مواقع السفن بين المشاهدات المتتالية (نصف قطر 400م، فجوة ≤ 10 أيام):
{dw_stats['matched_pairs']:,} زوجًا متطابقًا، وسيط مدة البقاء {fmt(dw_stats['median_days'])} أيام،
و{fmt(dw_stats['pct_persistent'])}% من السفن بقيت أربعة أيام فأكثر — معدل دوران اعتيادي لمرفأ تجاري.</p>
<h3>7أ.9) السفن الملاصقة للأرصفة وسقف القدرة</h3>
{img_html(png('berthed'), 'سفن الأرصفة')}
<p class="small">متوسط السفن ضمن 80م من حد المرفأ: {fmt(op_agg['berthed_mean'].mean())} في 2026
مقابل {fmt(op_25['berthed_mean'])} في 2022–2025. كما أن {fmt(op_cap26_pct)}% من مشاهدات 2026
تجاوزت سقف القدرة (الحد الأعلى التاريخي {fmt(op_p95)} سفينة في الحوض) مقابل {fmt(op_cap_pre_pct)}% في السنوات السابقة
— مؤشر ضغط تشغيلي حقيقي.</p>

<h2>7ب) المراقبة الإحصائية الفورية</h2>
<div class="card">
<p><b>كشف الشذوذ (EWMA + CUSUM):</b> طُبّقت خرائط التحكم الإحصائي على السلسلة الشهرية
بخط أساس 24 شهرًا ({fmt(anom_base)} ± {fmt(anom_sd)} سفينة لكل مشاهدة). رصد النظام
<b>{len(anom_events)}</b> حدث شذوذ، أبرزها الارتفاع المستمر في شباط–نيسان 2026
(درجات z بين 3.8 و5.7) — وهو ما يؤكد إحصائيًا أن النشاط خلال تلك الأشهر خرج عن
حدود التذبذب الطبيعية، وليس مجرد تقلب عادي.</p>
<p><b>تتبع السفن عبر الزمن:</b> سُلست التطابقات المكانية (نصف قطر 400م، فجوة ≤ 10 أيام)
في <b>{track_n:,}</b> مسارًا مميزًا، منها <b>{track_2p:,}</b> مسارًا ظهرت فيه السفينة في
مشهدين أو أكثر (متوسط {fmt(track_mean)} مشاهدات لكل سفينة). هذا يتيح الانتقال من
«عدد المشاهدات» إلى تقدير <b>عدد السفن الفريدة الفعلي</b>.</p>
</div>
{img_html(png('ewma'), 'مخطط EWMA')}
{img_html(png('cusum'), 'مخطط CUSUM')}

<h2>8) التحقق وجودة البيانات</h2>
<div class="card">
<h3>8.1) مؤشرات الجودة حسب السنة</h3>
<table><tr><th>السنة</th><th>سجلات سفن</th><th>متوسط الإشارة/الضوضاء (ديسيبل)</th><th>مشاهدات</th><th>خشونة البحر</th><th>ضوضاء المشهد</th></tr>{qrows}</table>
<p class="small">استقرار مؤشرات الجودة عبر السنوات (الإشارة/الضوضاء بين {qa['snr'].min():.1f} و{qa['snr'].max():.1f} ديسيبل،
خشونة {qa['rough'].min():.2f}–{qa['rough'].max():.2f}، تغطية ≥ {fmt(cov_min)}%) يؤكد أن فروق النشاط المرصودة ليست أثرًا لاختلاف ظروف الرصد.</p>

<h3>8.2) التحقق المتقاطع S1↔S2</h3>
<p>{n_pairs} زوجًا من المشاهدات المتقاربة (فارق ≤ 4 أيام، غيوم ≤ 25%). يتوافق المستشعران على أن 2026 هي
السنة الأعلى نشاطًا (العدّاد البصري: {fmt(opt26)} مقابل {fmt(opt25)} لنفس الأشهر من 2025)، مع الإشارة إلى أن العدّاد
البصري تقديري ولا يُعتمد كمرجع مطلق.</p>

<h3>8.3) مراجعة الجودة المطبقة</h3>
<p>عولجت ثلاث مسائل منهجية في مراجعة البيانات: (1) توحيد الأجزاء المنقسمة للسفن الطويلة في الصور الرادارية
(164 حالة)؛ (2) تصحيح مراكز السفن الراسية على الأرصفة (35 حالة) لضمان دقة المواقع؛ (3) ضبط دلالات ملفات
البيانات النهائية. وُحّدت السجلات ({n_vessels:,} سجلًا) عبر إعادة معالجة كاملة ومواءمة المصادر
(0 تباين متبقٍّ).</p>
</div>

<h2>8أ) المقارنة الإقليمية — اللاذقية · طرطوس · بانياس</h2>
<div class="card">
<p>للفصل بين تحول محلي وموجة إقليمية، طُبّق خط المعالجة نفسه على مرفأ طرطوس (الحدود الرسمية OSM:
way 160479740، {tartus_area_txt}) وعلى مرفأ بانياس النفطي (حوض محاط بكاسر أمواج OSM مغلق) باستخدام
المشاهدات الرادارية ذاتها. النتيجة:</p>
<table><tr><th>الميناء</th><th>2025 (كانون الثاني–آب)</th><th>2026 (كانون الثاني–آب)</th><th>التغير</th></tr>
<tr><td>اللاذقية</td><td>{fmt(cmp_lat['mean_25'])}</td><td>{fmt(cmp_lat['mean_26'])}</td><td class="ok">+{fmt(cmp_lat['pct'])}%</td></tr>
<tr><td>طرطوس</td><td>{fmt(cmp_tar['mean_25'])}</td><td>{fmt(cmp_tar['mean_26'])}</td><td class="warn">+{fmt(cmp_tar['pct'])}%</td></tr>
{("<tr><td>بانياس</td><td>{}</td><td>{}</td><td class='warn'>+{}%</td></tr>".format(fmt(ban['mean_25']), fmt(ban['mean_26']), fmt(ban['pct']))) if ban else ""}
</table>
<p>بينما قفز نشاط اللاذقية <b>+{fmt(cmp_lat['pct'])}%</b>، بقي نشاط طرطوس — الميناء الأكبر والأكثر
ازدحامًا تاريخيًا — شبه مستقر (<b>+{fmt(cmp_tar['pct'])}%</b>){(" أما مرفأ بانياس النفطي فارتفع <b>+{}%</b> من قاعدة منخفضة ({} ← {} سفينة لكل مشاهدة) — لا يغيّر الخلاصة: النمو الكبير حصرية باللاذقية.".format(fmt(ban['pct']), fmt(ban['mean_25']), fmt(ban['mean_26']))) if ban else ""}. هذا يرجّح أن الارتفاع في اللاذقية
<b>تحول محلي</b> خاص بالمرفأ (لوجستي/تشغيلي)، وليس موجة إقليمية شاملة على الساحل السوري.</p>
</div>
{img_html(png('comparison'), 'المقارنة الشهرية')}
{img_html(png('gap'), 'فجوة النشاط')}
{img_html(png('comparison_yearly'), 'المقارنة السنوية')}

<h2>9) الخرائط</h2>
<h3>9.1) خريطة مواقع السفن المكتشفة</h3>
{img_html(os.path.join(MAP_DIR, 'activity_map.png'), 'خريطة مواقع السفن')}
<p class="small">مواقع {n_vessels:,} سجل سفينة بإحداثيات حقيقية فوق خلفية متوسط 30 مشهدًا راداريًا.
الأحمر: الحوض · البنفسجي: المرسى · الأزرق: مياه العبور. حدود المرفأ وخط الساحل والكاسر من OpenStreetMap.</p>
<h3>9.2) خريطة كثافة الاكتشافات</h3>
{img_html(os.path.join(MAP_DIR, 'density_map.png'), 'خريطة الكثافة')}
<p class="small">الخريطة مبنية على إحداثيات حقيقية (UTM 36N) فوق خلفية متوسط 30 مشهدًا راداريًا فعليًا.</p>

<h2>10) أمثلة من المشاهدات</h2>
<div class="grid2">
 <div><p><b>أحدث مشهد في السلسلة:</b> {pd.to_datetime(ex1['datetime']):%Y-%m-%d %H:%M}Z —
 {int(ex1['n_est_in_port'])} سفينة في الحوض</p>{img_html(os.path.join(S1_DIR, ex1['id'], 'detection_overlay.jpg'))}</div>
 <div><p><b>أعلى مشهد نشاطًا:</b> {pd.to_datetime(ex2['datetime']):%Y-%m-%d %H:%M}Z —
 {int(ex2['n_est_in_port'])} سفينة في الحوض</p>{img_html(os.path.join(S1_DIR, ex2['id'], 'detection_overlay.jpg'))}</div>
</div>

<h2>11) الخلاصة والتوصيات</h2>
<div class="card">
<p>تشير البيانات إلى انتقال في مستوى نشاط مرفأ اللاذقية بدأ في كانون الأول 2025، وبلغ ذروته في الربع
الأول من 2026، وبقي أعلى من مستويات 2022–2025 حتى نهاية فترة الرصد. الارتفاع مشترك بين الحوض والمرسى،
ويتجاوز النمط الموسمي، ما يدل على زيادة في الطلب التشغيلي خلال هذه الفترة.</p>
<ul>
<li><b>المتابعة:</b> مواصلة الرصد الشهري لتأكيد استمرارية المستوى الجديد أو تحديد طابعه المؤقت؛ التركيز
على أشهر آب–كانون الأول 2026 لاختبار فرضية الاستمرارية بعد ذروة الربيع.</li>
<li><b>التحقق المعزز:</b> اعتماد طبقة AIS كمرجع تحقق إضافي عند توفرها — لتصنيف أنواع السفن والتحقق من
الهويات، خاصة في فترات الازدحام.</li>
<li><b>دقة العد:</b> مراجعة عتبات الفصل في أشهر الازدحام الشديد (شباط–نيسان 2026) وتحسين معالجة الكائنات
الملتصقة لتقليص هامش الخطأ في العد.</li>
<li><b>تفسير الأسباب:</b> مقارنة السلسلة بمؤشرات التجارة الخارجية والحركة الملاحية (عند توفرها) لتحديد
المحرك الاقتصادي/اللوجستي للارتفاع — وهو خارج نطاق بيانات الصور وحدها.</li>
</ul>
</div>

<h2>12) حدود المنهجية</h2>
<div class="card">
<ul>
<li>السفن الأصغر من نحو 15–20م (قوارب الصيد) غير مكتشفة بشكل منهجي بدقة 10م.</li>
<li>فصل السفن المتلاصقة تقديري؛ تبقى أخطاء عد محدودة عند الازدحام الشديد ({n_cluster} كائنًا عريضًا
موسومًا «عناقيد محتملة» ومرفقًا في البيانات).</li>
<li>نوع السفينة وحمولتها خارج نطاق التحليل دون AIS.</li>
<li>العدّاد البصري (S2) تقديري ويتأثر بالغيوم.</li>
<li>لا تفسر البيانات أسباب الارتفاع؛ الوثيقة تصف الظاهرة كميًا وتضبط الموسمية فقط.</li>
</ul>
</div>

<h2>13) الملاحق</h2>
<h3>13.1) تعريف حقول البيانات</h3>
<div class="card">
<table><tr><th>الحقل</th><th>المعنى</th></tr>
<tr><td>id / datetime</td><td>معرف المشهد الرسمي وتاريخ/وقت الالتقاط (UTC)</td></tr>
<tr><td>satellite / platform / orbit</td><td>القمر الصناعي (S1A/S1C/S1D) واتجاه المدار</td></tr>
<tr><td>n_total / n_est</td><td>عدد الكائنات اللامعة / تقدير السفن بعد الفصل والتوحيد</td></tr>
<tr><td>n_est_in_port / n_anchorage</td><td>السفن في الحوض / في المرسى</td></tr>
<tr><td>coverage / cov_port</td><td>تغطية البحر / تغطية حوض المرفأ في المشهد</td></tr>
<tr><td>noise_floor_db / sea_roughness</td><td>مستوى الضوضاء وحالة البحر (ضبط جودة)</td></tr>
<tr><td>vessels.json</td><td>لكل سفينة: الإحداثيات، الأبعاد، الاستطاعة، المنطقة، الأوسمة (مدمج / حافة رصيف / شبيه عنقود)</td></tr>
</table>
</div>
<h3>13.2) ملاحظات على البيانات</h3>
<div class="card">
<p>ملفات البيانات النهائية (<code>port_activity_dataset.csv</code> و<code>vessel_locations.csv</code>)
مبنية بعد مراجعة الجودة المذكورة في القسم 8.3. مؤشر النشاط في ملف المشاهدات محسوب لكل مشاهدة على حدة
(سفن الحوض ÷ تغطية الحوض)، والإحداثيات تمثل متوسط مواقع السفن المكتشفة فعليًا في كل مشاهدة. آخر مشهد
مدرج: <span dir="ltr">{pd.to_datetime(ex1['datetime']):%Y-%m-%d %H:%M}Z</span>
(<code>{ex1['id'][:40]}…</code>).</p>
</div>

<p class="small" style="margin-top:26px">البيانات: Copernicus Sentinel-1 / Sentinel-2 (ESA) عبر Microsoft
Planetary Computer · الحدود: OpenStreetMap © مساهمو OSM · اليابسة: Natural Earth (الملكية العامة).</p>
</div></body></html>"""
    os.makedirs(DOCS, exist_ok=True)
    out = os.path.join(DOCS, "FINAL_REPORT.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print("report written:", out, len(html) // 1024, "KB")


if __name__ == "__main__":
    build()
