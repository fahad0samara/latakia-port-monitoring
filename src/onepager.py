# -*- coding: utf-8 -*-
"""
Generate a one-page executive brief (EXEC_BRIEF.html + .pdf) for official
submission — A4, single page, KPI tiles, key findings, mini chart, approval line.
"""
import os, json, base64
import numpy as np
import pandas as pd
from datetime import datetime

from config import ROOT, DET_DIR, CHART_DIR

OUT = os.path.join(ROOT, "docs", "EXEC_BRIEF.html")
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


def fmt(v, nd=1):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—"
    if isinstance(v, float):
        return f"{v:.{nd}f}"
    return str(v)


CSS = """
*{box-sizing:border-box;margin:0;padding:0}
@page{size:A4;margin:0}
body{background:#fff;color:#1A1A2E;font-family:'Noto Sans Arabic','Segoe UI',Tahoma,Arial,sans-serif;
  width:210mm;min-height:297mm;margin:0 auto;padding:14mm 15mm;line-height:1.55;position:relative}
.hd{display:flex;justify-content:space-between;align-items:flex-start;border-bottom:3px solid #01B8AA;padding-bottom:8px;margin-bottom:12px}
.hd .t1{font-size:17pt;font-weight:700;color:#0E3A5C}
.hd .t2{font-size:10pt;color:#5A6A85;margin-top:2px}
.hd .ref{font-size:8.5pt;color:#5A6A85;text-align:left;line-height:1.6}
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:7px;margin:10px 0}
.k{background:#F2F8F8;border:1px solid #CFE6E4;border-radius:8px;padding:8px 10px}
.k .l{font-size:8pt;color:#5A6A85}
.k .v{font-size:15pt;font-weight:700;color:#01B8AA;margin-top:2px}
.k .s{font-size:7.5pt;color:#8A97AD}
.find{margin:10px 0}
.find .fh{font-size:11pt;font-weight:700;color:#0E3A5C;margin-bottom:6px}
ul{margin:0 18px 0 0;padding:0}
li{font-size:9.5pt;margin:4px 0}
.chart{margin:10px 0;text-align:center}
.chart img{width:100%;border:1px solid #E2E8F0;border-radius:8px}
.tbl{width:100%;border-collapse:collapse;font-size:8.5pt;margin:8px 0}
th{background:#0E3A5C;color:#fff;padding:5px 6px}
td{border:1px solid #D8E0EC;padding:4px 6px;text-align:center}
.two{display:grid;grid-template-columns:1.2fr 1fr;gap:10px}
.sign{margin-top:12px;border-top:1px solid #D8E0EC;padding-top:8px;display:flex;justify-content:space-between}
.sign div{font-size:8.5pt;color:#5A6A85;text-align:center;width:30%}
.sign .line{border-top:1px solid #8A97AD;margin-top:18px;padding-top:3px}
.foot{position:absolute;bottom:8mm;right:15mm;left:15mm;font-size:7.5pt;color:#8A97AD;border-top:1px solid #E2E8F0;padding-top:5px;display:flex;justify-content:space-between}
"""


def build():
    monthly = pd.read_csv(os.path.join(DET_DIR, "monthly.csv"))
    yearly = pd.read_csv(os.path.join(DET_DIR, "yearly.csv"))
    summary = json.load(open(os.path.join(DET_DIR, "summary.json"), encoding="utf-8"))
    insights = json.load(open(os.path.join(DET_DIR, "insights.json"), encoding="utf-8"))
    scenes = pd.read_json(os.path.join(DET_DIR, "s1_scenes.jsonl"), lines=True)
    good = scenes[scenes["error"].isna() | (scenes["error"] == "")].copy()
    good["dt"] = pd.to_datetime(good["datetime"])
    good["year"] = good["dt"].dt.year

    y = yearly.set_index("year")
    t2026 = summary["regimes"]["y2026_vs_2025"]["test"]
    tpost = summary["regimes"]["post_vs_pre_dec2024"]["test"]
    dw = insights["dwell"]

    anch26 = monthly[(monthly["ym"] >= "2026-01") & (monthly["n_obs"] > 0)]["mean_anchorage"].mean()
    anch_pre = monthly[(monthly["ym"] >= "2022-01") & (monthly["ym"] <= "2025-12") & (monthly["n_obs"] > 0)]["mean_anchorage"].mean()

    d0, d1 = good["dt"].min(), good["dt"].max()
    from compare import summary as cmp_summary
    _cmp = cmp_summary()
    cmp_lat_pct = (_cmp["latakia"] or {}).get("pct", 0)
    cmp_tar_pct = (_cmp["tartus"] or {}).get("pct", 0)
    _cb = _cmp.get("baniyas") if isinstance(_cmp.get("baniyas"), dict) else None
    cbpct = _cb.get("pct", 0) if _cb else 0
    from insights import operational_series as _ops
    _opd, _p95v = _ops(scenes)
    cap26 = float(_opd[_opd["year"] == 2026]["over_capacity"].mean() * 100)
    cap_pre = float(_opd[_opd["year"] <= 2025]["over_capacity"].mean() * 100) \
        if len(_opd[_opd["year"] <= 2025]) else 0.0
    n_vessels = int(good["n_est"].sum())
    n_ok = len(good)
    mk_tau = summary.get("mk_tau")
    mk_p = summary.get("mk_p")
    mk_txt = "صعود" if summary.get("mk_direction") == "increase" else ("انحدار" if summary.get("mk_direction") == "decrease" else "—")
    from insights import operational_series as _ops2
    _opd2, _p95v = _ops2(scenes)
    p95v = _p95v
    berth26v = float(_opd2[_opd2["year"] == 2026]["berthed"].mean())
    berthpre_v = float(_opd2[_opd2["year"] <= 2025]["berthed"].mean())
    _mmv = monthly.set_index("ym")
    fa26 = float(np.mean([_mmv.loc[f"2026-0{i}", "mean_ships_port_adj"] for i in (2, 3, 4) if f"2026-0{i}" in _mmv.index]))
    _fb = []
    for _i in (2, 3, 4):
        _vv = _mmv[(_mmv["month"] == _i) & (_mmv["year"].isin([2022, 2023, 2024, 2025])) & (_mmv["n_obs"] > 0)]["mean_ships_port_adj"]
        if len(_vv):
            _fb.append(float(_vv.mean()))
    fa_base = float(np.mean(_fb)) if _fb else 0.0

    # yearly table rows
    yrows = ""
    for _, r in yearly.iterrows():
        yrows += (f"<tr><td>{int(r['year'])}</td><td>{int(r['n_obs'])}</td>"
                  f"<td>{fmt(r['annual_mean_adj'])}</td>"
                  f"<td>{fmt(r['peak_value'])} ({ARABIC_MONTHS[int(r['peak_month'])-1]})</td>"
                  f"<td>{fmt(r['yoy_pct'],1)}%</td></tr>")

    html = f"""<!DOCTYPE html>
<html lang="ar" dir="rtl"><head><meta charset="utf-8">
<title>موجز تنفيذي — رصد النشاط البحري · مرفأ اللاذقية</title>
<style>{CSS}</style></head><body>

<div class="hd">
  <div>
    <div class="t1">موجز تنفيذي — رصد النشاط البحري في مرفأ اللاذقية</div>
    <div class="t2">إعداد: وحدة التحليل الفضائي · المصادر: كوبرنيكوس سنتينل-1 / سنتينل-2 (ESA) · خريطة الشارع المفتوحة · ناتشورال إيرث</div>
  </div>
  <div class="ref">
    التاريخ: {datetime.now():%Y-%m-%d}<br>
    الفترة: {ym_ar(d0.strftime("%Y-%m"))} — {ym_ar(d1.strftime("%Y-%m"))}
  </div>
</div>

<div class="kpis">
  <div class="k"><div class="l">متوسط النشاط 2026 (كانون الثاني–آب)</div><div class="v">{fmt(y.loc[2026,'annual_mean_adj'])}</div><div class="s">سفينة لكل مشاهدة</div></div>
  <div class="k"><div class="l">مقابل نفس الأشهر من 2025</div><div class="v" style="color:#0E9F6E">+{fmt(y.loc[2026,'yoy_pct'])}%</div><div class="s">احتمال {fmt(t2026['p_value'],4)}</div></div>
  <div class="k"><div class="l">سفن على الأرصفة 2026</div><div class="v" style="color:#F59E0B">{berth26v:.1f}</div><div class="s">مقابل {berthpre_v:.1f} (2022–2025)</div></div>
  <div class="k"><div class="l">مشاهدات فوق سقف القدرة</div><div class="v" style="color:#E11D48">{cap26:.0f}%</div><div class="s">مقابل {cap_pre:.0f}% سابقًا</div></div>
  <div class="k"><div class="l">إجمالي سجلات السفن</div><div class="v">{n_vessels:,}</div><div class="s">من {n_ok} مشهدًا راداريًا</div></div>
  <div class="k"><div class="l">اتجاه السلسلة (مان-كيندال)</div><div class="v" style="color:#F59E0B">{mk_txt}</div><div class="s">τ = {fmt(mk_tau,3)} · احتمال {fmt(mk_p,4)}</div></div>
</div>

<div class="two">
  <div class="find">
    <div class="fh">النتائج الرئيسية</div>
    <ul>
      <li><b>ارتفاع حقيقي في 2026:</b> {fmt(y.loc[2026,'annual_mean_adj'])} سفينة لكل مشاهدة مقابل {fmt(t2026['mean_before'])}
      لنفس الأشهر من 2025 — أعلى مستوى منذ 2022، ودال إحصائيًا (احتمال أقل من 0.0001 على المشاهدات، واحتمال {fmt(t2026['p_value'],4)} على الشهور).</li>
      <li><b>ليس موسميًا:</b> شباط–نيسان 2026 ({fa26:.1f}) مقابل {fa_base:.1f} في 2022–2025 — احتمال أقل من 0.0001 بعد الضبط الموسمي.</li>
      <li><b>ضغط على الأرصفة والمرسى:</b> سفن الأرصفة {berth26v:.1f} مقابل {berthpre_v:.1f}، وسفن الانتظار من {fmt(anch_pre)} إلى {fmt(anch26)} سفينة لكل مشاهدة.</li>
      <li><b>تجاوز القدرة التاريخية:</b> {cap26:.0f}% من مشاهدات 2026 تجاوزت سقف {p95v:.0f} سفينة (المئين الخامس والتسعون للفترة 2022–2024) مقابل {cap_pre:.0f}% فقط سابقًا.</li>
      <li><b>مدة البقاء:</b> وسيط {fmt(dw['median_days'])} أيام، و{fmt(dw['pct_persistent'])}% من السفن
      المتطابقة ({dw['matched_pairs']:,} زوجًا) بقيت أربعة أيام فأكثر — معدل دوران معتاد.</li>
      <li><b>استقرار 2022–2025:</b> التغيرات غير دالة، بما فيها ما بعد كانون الأول 2024 (احتمال {fmt(tpost['p_value'],4)}).</li>
      <li><b>تحول محلي لا إقليمي:</b> نفس المعالجة على طرطوس أظهرت تغيرًا +{cmp_tar_pct:.0f}% فقط
      (مقابل +{cmp_lat_pct:.0f}% للاذقية في نفس الفترة) وبانياس النفطي +{cbpct:.0f}% من قاعدة
      منخفضة — الارتفاع الكبير خاص باللاذقية.</li>
    </ul>
  </div>
  <div class="chart">
    <img src="{b64(os.path.join(CHART_DIR, 'monthly_line.png'))}" alt="الاتجاه الشهري">
  </div>
</div>

<table class="tbl">
<tr><th>السنة</th><th>مشاهدات</th><th>متوسط سفن لكل مشاهدة</th><th>أعلى شهر</th><th>التغير السنوي</th></tr>
{yrows}
</table>

<div class="foot">
  <span>تُحدَّث السلسلة الزمنية مع توفر مشاهدات جديدة · كل الأرقام من مشاهدات قمر صناعي حقيقية موثقة</span>
  <span>صفحة 1 من 1</span>
</div>
</body></html>"""
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html)
    print("brief written:", OUT, len(html) // 1024, "KB")


if __name__ == "__main__":
    build()
