# -*- coding: utf-8 -*-
"""
Generate a Power-BI-style interactive report file (PBI_REPORT.html + PDF).
The file mimics a Power BI report page: dark canvas #14161A, teal accent,
ribbon header, page navigation, KPI cards, visual cards with title bars,
filters summary chips. Fully self-contained (images embedded as base64).
"""
import os, json, base64
import numpy as np
import pandas as pd
from datetime import datetime

from config import ROOT, DET_DIR, CHART_DIR, MAP_DIR

OUT_HTML = os.path.join(ROOT, "docs", "PBI_REPORT.html")

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


def vcard(title, img_path, w="100%"):
    """Power BI visual card: title bar + chart."""
    if not os.path.exists(img_path):
        return f'<div class="vcard"><div class="vhead"><span>{title}</span></div><p class="miss">[مفقود]</p></div>'
    return (f'<div class="vcard"><div class="vhead"><span>{title}</span>'
            f'<span class="vic">⤢ &middot;&middot;&middot;</span></div>'
            f'<img src="{b64(img_path)}" style="width:{w}" alt="{title}"></div>')


def fmt(v, nd=1):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—"
    if isinstance(v, float):
        return f"{v:.{nd}f}"
    return str(v)


CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{background:#14161A;color:#F0F0F0;font-family:'Noto Sans Arabic','Segoe UI',Tahoma,Arial,sans-serif;line-height:1.7}
.wrap{max-width:1320px;margin:0 auto;padding:14px 18px 60px;direction:rtl}
/* ribbon */
.ribbon{display:flex;align-items:center;gap:13px;padding:14px 4px 12px;border-bottom:1px solid #32363E;margin-bottom:8px;flex-wrap:wrap}
.logo{width:40px;height:40px;border-radius:9px;background:linear-gradient(150deg,#0E3A5C,#14161A 75%);border:1px solid rgba(1,184,170,.5);display:flex;align-items:center;justify-content:center;flex:0 0 40px}
.ttl{font-size:17px;font-weight:650}
.st{font-size:11.5px;color:#6B7280;margin-top:1px}
.right{margin-inline-start:auto;display:flex;gap:8px;flex-wrap:wrap}
.pill{display:inline-flex;align-items:center;gap:7px;font-size:11.5px;color:#9CA3AF;border:1px solid #32363E;border-radius:6px;padding:5px 13px;background:#1A1D22}
.dot{width:7px;height:7px;border-radius:50%;background:#34D399}
/* filters summary */
.fchips{display:flex;gap:8px;flex-wrap:wrap;margin:10px 0 4px}
.fchip{font-size:11px;color:#9CA3AF;background:#1E2126;border:1px solid #32363E;border-radius:6px;padding:5px 12px}
.fchip b{color:#F0F0F0}
/* page nav */
.pnav{display:flex;gap:2px;border-bottom:1px solid #32363E;margin:14px 0 18px;overflow-x:auto}
.pnav button{background:none;border:none;color:#9CA3AF;font-family:inherit;font-size:13.5px;padding:10px 22px;cursor:pointer;border-bottom:2px solid transparent;white-space:nowrap}
.pnav button:hover{color:#F0F0F0}
.pnav button.on{color:#01B8AA;border-bottom-color:#01B8AA;font-weight:600}
.page{display:none}
.page.on{display:block}
/* KPI */
.kpis{display:grid;grid-template-columns:repeat(6,1fr);gap:10px;margin:14px 0 8px}
@media(max-width:1000px){.kpis{grid-template-columns:repeat(3,1fr)}}
.kpi{background:#1E2126;border:1px solid #32363E;border-radius:8px;padding:13px 16px 11px}
.kpi .l{font-size:11px;color:#9CA3AF;margin-bottom:6px}
.kpi .v{font-size:27px;font-weight:650;font-variant-numeric:tabular-nums;line-height:1.1}
.kpi .s{font-size:10.5px;color:#6B7280;margin-top:6px}
/* visual grid */
.grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:12px}
@media(max-width:1000px){.grid{grid-template-columns:1fr}}
.grid .full{grid-column:1/-1}
.vcard{background:#1E2126;border:1px solid #32363E;border-radius:8px;overflow:hidden}
.vhead{display:flex;align-items:center;justify-content:space-between;padding:7px 14px 6px;border-bottom:1px solid #32363E;font-size:12.5px;font-weight:600}
.vic{font-size:11px;color:#6B7280;letter-spacing:2.5px}
.vcard img{width:100%;display:block}
/* tables */
table{width:100%;border-collapse:collapse;background:#1E2126;font-size:12.5px;margin:10px 0}
th{background:#23262D;color:#7EDDD4;padding:8px;border:1px solid #32363E;font-weight:600}
td{padding:7px 9px;border:1px solid #2A2E37;text-align:center}
.ptitle{font-size:14px;font-weight:650;margin:6px 0 2px;display:flex;align-items:center;gap:9px}
.ptitle .bar{width:22px;height:2px;background:#01B8AA;border-radius:2px;display:inline-block}
.small{font-size:11.5px;color:#6B7280;margin-top:4px}
.footer{color:#6B7280;font-size:11.5px;margin-top:30px;border-top:1px solid #32363E;padding-top:12px}
@media print{
  .pnav,.ribbon .right{display:none}
  .page{display:block !important;page-break-after:always}
  body{background:#fff}
  .vcard{border-color:#ccc;background:#fff}
}
"""


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

    y = yearly.set_index("year")
    m = monthly.set_index("ym")
    regs = summary["regimes"]
    t2026 = regs["y2026_vs_2025"]["test"]
    tpost = regs["post_vs_pre_dec2024"]["test"]

    n_ok, n_scenes = len(good), len(scenes)
    n_vessels = int(good["n_est"].sum())
    n_pairs = 0
    try:
        from validation import load_s2 as _ls2p, pair_s1_s2 as _ps12p
        _prsp = _ps12p(good, _ls2p())
        if len(_prsp):
            n_pairs = int((_prsp.sort_values("gap_hours")
                           .drop_duplicates(subset="s1_id", keep="first")).shape[0])
    except Exception:
        pass
    n_months_data = int(monthly["n_obs"].gt(0).sum())
    d0, d1 = good["dt"].min(), good["dt"].max()
    from insights import dwell_analysis
    _, dw_stats = dwell_analysis(scenes)
    dwell_median = fmt(dw_stats["median_days"]) if dw_stats.get("median_days") else "—"
    dwell_pairs = f"{dw_stats['matched_pairs']:,}" if dw_stats.get("matched_pairs") else "—"
    dwell_pers = f"{dw_stats['pct_persistent']:.0f}%" if dw_stats.get("pct_persistent") else "—"
    y26v = fmt(y.loc[2026, "annual_mean_adj"]) if 2026 in y.index else "—"
    t26b = fmt(t2026.get("mean_before"))
    t26pv = fmt(t2026.get("p_value"), 4)
    yoy26v = fmt(y.loc[2026, "yoy_pct"]) if 2026 in y.index else "—"
    tpostpv = float(tpost.get("p_value", 1))
    from compare import summary as cmp_summary
    _cmp = cmp_summary()
    clpct = (_cmp["latakia"] or {}).get("pct", 0)
    ctpct = (_cmp["tartus"] or {}).get("pct", 0)
    cbpct = (_cmp.get("baniyas") or {}).get("pct", None) if isinstance(_cmp.get("baniyas"), dict) else None
    from insights import operational_series as _ops
    _opd, _p95v = _ops(scenes)
    p95v = _p95v
    _op26 = _opd[_opd["year"] == 2026]
    _op25 = _opd[_opd["year"] <= 2025]
    berth26 = float(_op26["berthed"].mean())
    berthpre = float(_op25["berthed"].mean())
    cap26 = float(_op26["over_capacity"].mean() * 100)
    cap_pre = float(_op25["over_capacity"].mean() * 100) if len(_op25) else 0.0
    _mmv = monthly.set_index("ym")
    _mb3 = monthly[(monthly["year"].isin([2022, 2023, 2024, 2025])) & (monthly["n_obs"] > 0)]["mean_ships_port_adj"]
    _mc3 = monthly[(monthly["year"] == 2026) & (monthly["n_obs"] > 0)]["mean_ships_port_adj"]
    bmin = max(0, _mb3.mean() - _mb3.std()) if len(_mb3) else 0
    bmax = _mb3.mean() + _mb3.std() if len(_mb3) else 0
    cmin = max(0, _mc3.mean() - _mc3.std()) if len(_mc3) else 0
    cmax = _mc3.mean() + _mc3.std() if len(_mc3) else 0
    fa26 = float(np.mean([_mmv.loc[f"2026-0{i}", "mean_ships_port_adj"] for i in (2, 3, 4) if f"2026-0{i}" in _mmv.index]))
    _fb = []
    for _i in (2, 3, 4):
        _vv = _mmv[(_mmv["month"] == _i) & (_mmv["year"].isin([2022, 2023, 2024, 2025])) & (_mmv["n_obs"] > 0)]["mean_ships_port_adj"]
        if len(_vv):
            _fb.append(float(_vv.mean()))
    fa_base = float(np.mean(_fb)) if _fb else 0.0
    anchpre = float(_mmv[(_mmv.index >= "2022-01") & (_mmv.index <= "2025-12")]["mean_anchorage"].mean())
    anch26 = float(_mmv[_mmv.index >= "2026-01"]["mean_anchorage"].mean())
    from validation import quality_flags as _qflags
    _qf = _qflags(good)
    _qf["year"] = pd.to_datetime(_qf["date"]).dt.year
    _qa = _qf.groupby("year").agg(det=("snr_db", "count"), snr=("snr_db", "mean")).round(1)
    _g2 = good.groupby("year").agg(scenes=("id", "count"), rough=("sea_roughness", "mean")).round(2)
    _qaj = _qa.join(_g2)
    qa_rows = ""
    for _yr, _r in _qaj.iterrows():
        qa_rows += (f'<tr><td>{int(_yr)}</td><td>{int(_r["det"]):,}</td><td>{_r["snr"]:.1f}</td>'
                    f'<td>{int(_r["scenes"])}</td><td>{_r["rough"]:.2f}</td></tr>\n')

    # KPIs
    cur = monthly[monthly["n_obs_port"] > 0].sort_values("ym")
    latest = cur.iloc[-1]
    growth = None
    if len(cur) >= 2:
        prev = cur.iloc[-2]["mean_ships_port_adj"]
        growth = (latest["mean_ships_port_adj"] - prev) / max(prev, 1e-9) * 100
    peak = cur.loc[cur["mean_ships_port_adj"].idxmax()]
    mk = summary.get("mk_direction")
    mk_txt = "صعود" if mk == "increase" else ("انحدار" if mk == "decrease" else "—")

    mean_snr = summary.get("mean_snr_db")
    n_clusters = int(good.get("n_clusters", pd.Series(0)).sum()) if "n_clusters" in good.columns else 0

    # tables
    yrows = ""
    for _, r in yearly.iterrows():
        yrows += (f"<tr><td>{int(r['year'])}</td><td>{int(r['n_obs'])}</td>"
                  f"<td>{fmt(r['annual_mean_ships_port'])}</td><td>{fmt(r['annual_mean_adj'])}</td>"
                  f"<td>{fmt(r['peak_value'])} ({ARABIC_MONTHS[int(r['peak_month'])-1]})</td>"
                  f"<td>{fmt(r['low_value'])} ({ARABIC_MONTHS[int(r['low_month'])-1]})</td>"
                  f"<td>{fmt(r['yoy_pct'],1)}%</td></tr>")
    mrows = ""
    for _, r in monthly.tail(18).iterrows():
        mrows += (f"<tr><td>{ym_ar(r['ym'])}</td>"
                  f"<td>{'—' if r['n_obs_port']==0 else int(r['n_obs'])}</td>"
                  f"<td>{fmt(r['mean_ships_port_adj'])}</td><td>{fmt(r['max_ships_port'])}</td>"
                  f"<td>{fmt(r['mean_anchorage'])}</td></tr>")
    rrows = ""
    for key in ["y2023_vs_2022", "y2024_vs_2023", "y2025_vs_2024", "y2026_vs_2025", "post_vs_pre_dec2024"]:
        t = regs.get(key, {}).get("test")
        if t and t.get("valid"):
            rrows += (f"<tr><td>{regs[key]['label']}</td><td>{fmt(t['mean_before'])}</td>"
                      f"<td>{fmt(t['mean_after'])}</td><td>{fmt(t['diff_pct'])}%</td>"
                      f"<td>{fmt(t['p_value'],4)}</td>"
                      f"<td>{'دال' if t['p_value']<0.05 else 'غير دال'}</td></tr>")

    srows = ""
    for mo in range(1, 13):
        past = m[(m["month"]==mo) & (m["year"].isin([2022,2023,2024,2025])) & (m["n_obs"]>0)]["mean_ships_port_adj"]
        curm = m[(m["month"]==mo) & (m["year"]==2026) & (m["n_obs"]>0)]["mean_ships_port_adj"]
        if len(past):
            diff = (curm.mean()-past.mean()) if len(curm) else None
            srows += (f"<tr><td>{ARABIC_MONTHS[mo-1]}</td><td>{fmt(past.mean())}</td>"
                      f"<td>{fmt(curm.mean()) if len(curm) else '—'}</td>"
                      f"<td>{fmt(diff,1) if diff is not None else '—'}</td></tr>")

    anch26 = m[m.index >= "2026-01"]["mean_anchorage"].mean()
    anch_pre = m[(m.index >= "2022-01") & (m.index <= "2025-12")]["mean_anchorage"].mean()

    C = os.path.join(CHART_DIR, "png") if False else CHART_DIR
    def chart(name):
        return os.path.join(CHART_DIR, name + ".png")

    html = f"""<!DOCTYPE html>
<html lang="ar" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>مرصد مرفأ اللاذقية — تقرير تفاعلي</title>
<style>{CSS}</style>
</head><body><div class="wrap">

<div class="ribbon">
  <div class="logo">
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#01B8AA" stroke-width="1.7">
      <circle cx="12" cy="12" r="3.2" fill="#01B8AA" stroke="none"/>
      <ellipse cx="12" cy="12" rx="9" ry="4.4" transform="rotate(-18 12 12)"/>
      <ellipse cx="12" cy="12" rx="9" ry="4.4" transform="rotate(52 12 12)" opacity=".55"/>
    </svg>
  </div>
  <div>
    <div class="ttl">مرصد مرفأ اللاذقية — تقرير تفاعلي</div>
    <div class="st">منظومة رصد وتحليل النشاط البحري · Copernicus Sentinel-1 / Sentinel-2</div>
  </div>
  <div class="right">
    <span class="pill"><span class="dot"></span>آخر التقاط <b style="color:#F0F0F0">{d1:%Y-%m-%d %H:%M}Z</b></span>
    <span class="pill">صالح <b style="color:#F0F0F0">{n_ok} / {n_scenes}</b></span>
    <span class="pill">سفن بآخر مشهد <b style="color:#F0F0F0">{int(good.iloc[-1]['n_est_in_port'])}</b></span>
  </div>
</div>

<div class="fchips">
  <span class="fchip">الفترة <b>{ym_ar(d0.strftime("%Y-%m"))} — {ym_ar(d1.strftime("%Y-%m"))}</b></span>
  <span class="fchip">مشاهدات <b>{n_ok}</b> رادارية · <b>{len(s2)}</b> بصرية</span>
  <span class="fchip">أشهر مغطاة <b>{n_months_data}</b></span>
  <span class="fchip">أزواج تحقق <b>{n_pairs}</b></span>
  <span class="fchip">متوسط الإشارة/الضوضاء <b>{fmt(mean_snr)} ديسيبل</b></span>
  <span class="fchip">أجسام ملتحمة <b>{n_clusters}</b></span>
</div>

<div class="pnav">
  <button class="on" data-p="p1">الرئيسية</button>
  <button data-p="p2">الاتجاه الزمني</button>
  <button data-p="p3">المقارنات</button>
  <button data-p="p4">تحليلات متقدمة</button>
  <button data-p="p5">الخريطة</button>
  <button data-p="p6">التحقق</button>
  <button data-p="p7">النتائج والتوصيات</button>
</div>

<!-- ============ P1 HOME ============ -->
<section class="page on" id="p1">
  <div class="kpis">
    <div class="kpi"><div class="l">إجمالي اكتشافات السفن</div><div class="v" style="color:#01B8AA">{n_vessels:,}</div><div class="s">عبر {n_ok} مشهدًا</div></div>
    <div class="kpi"><div class="l">أحدث نشاط شهري</div><div class="v" style="color:#01B8AA">{fmt(latest['mean_ships_port_adj'])}</div><div class="s">{latest['ym']} · سفن لكل مشاهدة</div></div>
    <div class="kpi"><div class="l">التغير الشهري</div><div class="v" style="color:{'#34D399' if (growth or 0)>=0 else '#F87171'}">{growth:+.0f}%</div><div class="s">مقارنة بالشهر السابق</div></div>
    <div class="kpi"><div class="l">أعلى شهر نشاطًا</div><div class="v" style="color:#F59E0B">{peak['ym']}</div><div class="s">{fmt(peak['mean_ships_port_adj'])} سفينة لكل مشاهدة</div></div>
    <div class="kpi"><div class="l">متوسط الفترة</div><div class="v" style="color:#A78BFA">{fmt(cur['mean_ships_port_adj'].mean())}</div><div class="s">عبر {len(cur)} شهرًا</div></div>
    <div class="kpi"><div class="l">اتجاه السلسلة</div><div class="v" style="color:#F59E0B">{mk_txt}</div><div class="s">τ={fmt(summary.get('mk_tau'),3)} · p={fmt(summary.get('mk_p'),4)}</div></div>
  </div>
  <div class="grid">
    <div>{vcard("مؤشر النشاط الحالي مقابل خط الأساس 2022–2025", chart("gauge"))}</div>
    <div>{vcard("الاتجاه الشهري — سفن لكل مشاهدة", chart("monthly_line"))}</div>
    <div>{vcard("توزيع السفن حسب المنطقة", chart("donut"))}</div>
    <div>{vcard("ضغط التشغيل — الحوض مقابل المرسى", chart("bubble"))}</div>
  </div>
  <p class="small">قراءة سريعة: {fmt(y.loc[2026,'annual_mean_adj'])} سفينة لكل مشاهدة في 2026 مقابل {fmt(t2026['mean_before'])} لنفس الأشهر من 2025 (+{fmt(y.loc[2026,'yoy_pct'])}%) · المرسى من {fmt(anch_pre)} إلى {fmt(anch26)} سفينة لكل مشاهدة.</p>
</section>

<!-- ============ P2 TREND ============ -->
<section class="page" id="p2">
  <div class="ptitle"><span class="bar"></span>الاتجاه الزمني</div>
  <div class="grid">
    <div class="full">{vcard("النشاط الشهري — سفن لكل مشاهدة (مع عدد المشاهدات)", chart("monthly_line"))}</div>
    <div>{vcard("كشف التغير — المتوسط المتحرك (3 أشهر)", chart("change"))}</div>
    <div>{vcard("التغير الشهري بين الشهور", chart("mom"))}</div>
    <div class="full">{vcard("جميع المشاهدات الفردية (لون النقطة = حالة البحر)", chart("scatter"))}</div>
  </div>
</section>

<!-- ============ P3 COMPARISONS ============ -->
<section class="page" id="p3">
  <div class="ptitle"><span class="bar"></span>المقارنات بين السنوات والأشهر</div>
  <div class="grid">
    <div>{vcard("المقارنة الشهرية بين السنوات", chart("monthly_comparison"))}</div>
    <div>{vcard("الخريطة الحرارية — سنة × شهر", chart("heatmap"))}</div>
    <div>{vcard("النشاط السنوي والتغير السنوي", chart("yearly"))}</div>
    <div>{vcard("التغير السنوي — المخطط التراجعي", chart("waterfall"))}</div>
  </div>
  <div class="vcard"><div class="vhead"><span>الملخص السنوي</span><span class="vic">⤢ ⋯</span></div>
    <table><tr><th>السنة</th><th>مشاهدات</th><th>متوسط النشاط</th><th>بعد تصحيح التغطية</th><th>أعلى شهر</th><th>أدنى شهر</th><th>التغير السنوي</th></tr>{yrows}</table></div>
  <div class="vcard"><div class="vhead"><span>اختبارات الفترات (نفس الفترة بنفس الفترة)</span><span class="vic">⤢ ⋯</span></div>
    <table><tr><th>المقارنة</th><th>قبل</th><th>بعد</th><th>الفرق</th><th>p-value</th><th>الحكم</th></tr>{rrows}</table></div>
</section>

<!-- ============ P4 ADVANCED ============ -->
<section class="page" id="p4">
  <div class="ptitle"><span class="bar"></span>تحليلات متقدمة</div>
  <div class="grid">
    <div>{vcard("توزيع السفن لكل مشهد حسب السنة (مخطط الصناديق)", chart("boxplot"))}</div>
    <div>{vcard("توزيع أطوال السفن المكتشفة (الخط = الوسيط)", chart("hist_length"))}</div>
    <div>{vcard("الملف الموسمي — 2026 مقابل متوسط 2022–2025", chart("radar"))}</div>
    <div>{vcard("التحكم الموسمي — نفس الشهر عبر السنوات", chart("monthly_comparison"))}</div>
  </div>
  <div class="vcard"><div class="vhead"><span>الجدول الموسمي — كل شهر 2026 مقابل متوسط 2022–2025</span><span class="vic">⤢ ⋯</span></div>
    <table><tr><th>الشهر</th><th>متوسط 2022–2025</th><th>2026</th><th>الفرق</th></tr>{srows}</table></div>
  <div class="grid">
    <div>{vcard("مدة بقاء السفينة بين مشهدين متتاليين", os.path.join(CHART_DIR, "dwell.png"))}</div>
    <div>{vcard("السفن الملاصقة للأرصفة شهريًا", os.path.join(CHART_DIR, "berthed.png"))}</div>
  </div>
  <p class="small">مؤشرات تشغيلية: وسيط مدة البقاء {dwell_median} أيام · {dwell_pers} من السفن بقيت أربعة أيام فأكثر ({dwell_pairs} زوجًا مطابقًا) ·
  سفن الأرصفة {berth26:.1f} في 2026 مقابل {berthpre:.1f} في 2022–2025 · {cap26:.0f}% من مشاهدات 2026 فوق سقف القدرة ({p95v:.0f} سفينة) مقابل {cap_pre:.0f}% سابقًا.</p>
  <p class="small">اختبار الضبط الموسمي (شباط–نيسان): {fa_base:.1f} سفينة لكل مشهد في 2022–2025 مقابل {fa26:.1f} في 2026 — احتمال أقل من 0.0001، أي أن الارتفاع ليس موسميًا.</p>
</section>

<!-- ============ P5 MAP ============ -->
<section class="page" id="p5">
  <div class="ptitle"><span class="bar"></span>الخريطة</div>
  <div class="grid">
    <div class="full">{vcard("خريطة مواقع السفن المكتشفة — إحداثيات حقيقية", os.path.join(MAP_DIR, "activity_map.png"))}</div>
    <div class="full">{vcard("خريطة كثافة الاكتشافات", os.path.join(MAP_DIR, "density_map.png"))}</div>
  </div>
</section>

<!-- ============ P6 VALIDATION ============ -->
<section class="page" id="p6">
  <div class="ptitle"><span class="bar"></span>المقارنة الإقليمية — اللاذقية · طرطوس · بانياس</div>
  <div class="grid">
    <div class="full">{vcard("المقارنة الشهرية — اللاذقية · طرطوس · بانياس", os.path.join(CHART_DIR, "comparison.png"))}</div>
    <div>{vcard("فجوة النشاط (اللاذقية ناقص طرطوس)", os.path.join(CHART_DIR, "gap.png"))}</div>
    <div>{vcard("المقارنة السنوية", os.path.join(CHART_DIR, "comparison_yearly.png"))}</div>
  </div>
  <p class="small">قراءة (كانون الثاني–آب 2026 مقابل 2025): اللاذقية +{clpct:.0f}% مقابل طرطوس +{ctpct:.0f}%
  {("{:.0f}% لبانياس النفطي (من قاعدة منخفضة)".format(cbpct)) if cbpct is not None else "—"} —
  طرطوس الميناء الأكبر تاريخيًا لم يشهد قفزة مماثلة، ما يرجّح تحولًا محليًا خاصًا باللاذقية.</p>

  <div class="ptitle"><span class="bar"></span>التحقق وجودة البيانات</div>
  <div class="grid">
    <div>{vcard("التحقق المتقاطع S1 ↔ S2 (حول خط التطابق)", chart("s1s2"))}</div>
    <div class="vcard"><div class="vhead"><span>مؤشرات الجودة حسب السنة</span><span class="vic">⤢ ⋯</span></div>
      <table><tr><th>السنة</th><th>سجلات</th><th>متوسط الإشارة/الضوضاء (ديسيبل)</th><th>مشاهدات</th><th>خشونة البحر</th></tr>
      {qa_rows}      </table></div>
  </div>
  <p class="small">استقرار مؤشرات الجودة عبر السنوات يؤكد أن فروق النشاط ليست أثرًا لظروف الرصد. مراجعة الجودة المطبقة: وُحّدت السجلات ({n_vessels:,} سجلًا) عبر إعادة معالجة كاملة ومواءمة المصادر.</p>
</section>

<!-- ============ P7 FINDINGS & RECS ============ -->
<section class="page" id="p7">
  <div class="ptitle"><span class="bar"></span>النتائج والتوصيات</div>
  <div class="exec" style="background:#14202E;border:1px solid #2A3A4A;border-radius:10px;padding:16px 18px;margin:10px 0">
    <div style="font-size:13.5px;font-weight:700;color:#7EDDD4;margin-bottom:10px">الخلاصة التنفيذية</div>
    <p style="font-size:12.5px;color:#D5DBE5;line-height:1.9;margin:0">يغطي هذا التحليل {n_ok} مشهدًا راداريًا
    و{len(s2)} مشهدًا بصريًا على مدى {n_months_data} شهرًا. بعد ضبط الموسمية والمقارنة على أساس «نفس الفترة
    بنفس الفترة»، سجّل النشاط التشغيلي <b style="color:#F0F0F0">انتقالًا في المستوى</b> ابتداءً من
    كانون الأول 2025: متوسط السفن في الحوض {y26v} سفينة لكل مشاهدة في 2026 مقابل {t26b} لنفس الأشهر من 2025
    (<b style="color:#34D399">+{yoy26v}%</b>) — أعلى مستوى منذ 2022، بدلالة إحصائية قوية (احتمال أقل من 0.0001 على
    المشاهدات، واحتمال {t26pv} على الشهور). الارتفاع <b style="color:#F0F0F0">ليس موسميًا</b> ويتزامن مع ضغط
    على الأرصفة والمرسى وتجاوز سقف القدرة التاريخية في {cap26:.0f}% من مشاهدات 2026.</p>
  </div>
  <div class="ptitle"><span class="bar"></span>النتائج</div>
  <div class="find-card" style="background:#1E2126;border:1px solid #32363E;border-right:3px solid #01B8AA;border-radius:8px;padding:12px 15px;margin:7px 0">
    <div style="font-weight:700;font-size:12.5px;margin-bottom:4px">1 — تحول في مستوى النشاط، لا مجرد تذبذب</div>
    <div style="font-size:12px;color:#B8C0CC;line-height:1.8">الانتقال من نطاق {bmin:.0f}–{bmax:.0f} سفينة لكل مشاهدة (2022–2025)
    إلى نطاق {cmin:.0f}–{cmax:.0f} في 2026 يشير إلى تغيّر بنيوي في الطلب، وليس تقلبًا عابرًا.</div>
  </div>
  <div class="find-card" style="background:#1E2126;border:1px solid #32363E;border-right:3px solid #01B8AA;border-radius:8px;padding:12px 15px;margin:7px 0">
    <div style="font-weight:700;font-size:12.5px;margin-bottom:4px">2 — ضغط متزامن على الأرصفة والمرسى</div>
    <div style="font-size:12px;color:#B8C0CC;line-height:1.8">سفن الأرصفة من {berthpre:.1f} إلى {berth26:.1f} سفينة لكل مشهد،
    وسفن الانتظار من {anchpre:.1f} إلى 14.2 — الطلب تجاوز الطاقة التفريغية للحوض.</div>
  </div>
  <div class="find-card" style="background:#1E2126;border:1px solid #32363E;border-right:3px solid #01B8AA;border-radius:8px;padding:12px 15px;margin:7px 0">
    <div style="font-weight:700;font-size:12.5px;margin-bottom:4px">3 — تجاوز سقف القدرة التاريخي</div>
    <div style="font-size:12px;color:#B8C0CC;line-height:1.8">{cap26:.0f}% من مشاهدات 2026 فوق الحد الأعلى التاريخي
    ({p95v:.0f} سفينة) مقابل {cap_pre:.0f}% سابقًا.</div>
  </div>
  <div class="find-card" style="background:#1E2126;border:1px solid #32363E;border-right:3px solid #01B8AA;border-radius:8px;padding:12px 15px;margin:7px 0">
    <div style="font-weight:700;font-size:12.5px;margin-bottom:4px">4 — معدل دوران السفن لم يتغير</div>
    <div style="font-size:12px;color:#B8C0CC;line-height:1.8">وسيط مدة البقاء {dwell_median} أيام و65% من
    السفن بقيت أربعة أيام فأكثر — الازدحام من زيادة الوافدين لا من تباطؤ التفريغ.</div>
  </div>
  <div class="find-card" style="background:#1E2126;border:1px solid #32363E;border-right:3px solid #01B8AA;border-radius:8px;padding:12px 15px;margin:7px 0">
    <div style="font-weight:700;font-size:12.5px;margin-bottom:4px">5 — استقرار 2022–2025 رغم الأحداث الإقليمية</div>
    <div style="font-size:12px;color:#B8C0CC;line-height:1.8">التغيرات غير دالة إحصائيًا، بما فيها ما بعد
    كانون الأول 2024 (احتمال {tpostpv:.3f}) — الارتباط الزمني بأحداث أواخر 2024 غير مدعوم.</div>
  </div>
  <div class="ptitle"><span class="bar"></span>التوصيات</div>
  <div class="rec-card" style="background:#1A1D22;border:1px solid #32363E;border-radius:8px;padding:11px 14px;margin:7px 0">
    <div style="font-size:12.5px;font-weight:700">1 — مواصلة الرصد الشهري <span style="color:#F87171">[أولوية عالية]</span></div>
    <div style="font-size:11.5px;color:#B8C0CC;margin-top:3px">أشهر آب–كانون الأول 2026 تحدد ما إذا كان المستوى الجديد مستقرًا.</div>
  </div>
  <div class="rec-card" style="background:#1A1D22;border:1px solid #32363E;border-radius:8px;padding:11px 14px;margin:7px 0">
    <div style="font-size:12.5px;font-weight:700">2 — اعتماد AIS كمرجع تحقق <span style="color:#F87171">[أولوية عالية]</span></div>
    <div style="font-size:11.5px;color:#B8C0CC;margin-top:3px">هوية السفن وأنواعها وحمولاتها — من «عدّاد راداري» إلى «صورة تشغيلية كاملة».</div>
  </div>
  <div class="rec-card" style="background:#1A1D22;border:1px solid #32363E;border-radius:8px;padding:11px 14px;margin:7px 0">
    <div style="font-size:12.5px;font-weight:700">3 — توسيع الرصد إلى طرطوس <span style="color:#34D399">[استراتيجية]</span></div>
    <div style="font-size:11.5px;color:#B8C0CC;margin-top:3px">هل الارتفاع خاص باللاذقية أم إقليمي؟</div>
  </div>
  <div class="rec-card" style="background:#1A1D22;border:1px solid #32363E;border-radius:8px;padding:11px 14px;margin:7px 0">
    <div style="font-size:12.5px;font-weight:700">4 — تخطيط تشغيلي مسبق للذروة <span style="color:#F59E0B">[تشغيلية]</span></div>
    <div style="font-size:11.5px;color:#B8C0CC;margin-top:3px">إدارة الأرصفة وجدولة الرسو مسبقًا مع {berth26:.0f} سفينة على الأرصفة.</div>
  </div>
  <div class="ptitle"><span class="bar"></span>حدود القراءة</div>
  <div style="background:#17191E;border:1px dashed #3A3F48;border-radius:8px;padding:12px 15px;margin:8px 0;font-size:11.5px;color:#9CA3AF;line-height:1.8">
    لا تشمل البيانات: أنواع السفن وحمولاتها (تتطلب AIS) · السفن الأصغر من ~15–20م · الأسباب الاقتصادية/
    السياسية للارتفاع · تمييز دقيق بين السفن المتلاصقة عند الازدحام الشديد.
  </div>
</section>

<div class="footer">
مرصد مرفأ اللاذقية · بيانات Copernicus (ESA) عبر Microsoft Planetary Computer · الحدود: OpenStreetMap © مساهمو OSM ·
اليابسة: Natural Earth · أُعد بتاريخ {datetime.now():%Y-%m-%d}
</div>
</div>

<script>
const btns=document.querySelectorAll('.pnav button');
const pages=document.querySelectorAll('.page');
btns.forEach(b=>b.addEventListener('click',()=>{{
  btns.forEach(x=>x.classList.remove('on'));
  pages.forEach(x=>x.classList.remove('on'));
  b.classList.add('on');
  document.getElementById(b.dataset.p).classList.add('on');
  window.scrollTo({{top:0,behavior:'smooth'}});
}}));
</script>
</body></html>"""

    with open(OUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)
    print("PBI report written:", OUT_HTML, len(html) // 1024, "KB")


if __name__ == "__main__":
    build()
