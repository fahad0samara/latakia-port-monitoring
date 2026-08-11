# -*- coding: utf-8 -*-
"""
AIS verification — ties SAR detections to real AIS identities and provides
a clearly-labelled dimension-based type estimate when AIS is not available.

TWO LEVELS, NEVER MIXED:
  1. REAL AIS MATCHING — when AIS messages exist under data/ais/ (jsonl/csv,
     one message per line) every vessel detection is matched spatially
     (<= 600 m) and temporally (<= 45 min) and the real IMO/MMSI/name/ship
     type are attached. `is_ais=True` on those records only.
  2. DIMENSION ESTIMATE — ship type guessed from the SAR length/width with
     IMO-consistent thresholds. Always flagged `is_ais=False` and reported
     as "تقدير" — it is a working hypothesis, not AIS truth.

AIS file format (jsonl or csv, same column names):
  timestamp (ISO 8601 UTC), lon, lat, mmsi, imo, name, ship_type,
  length_m, width_m, sog, cog, destination
(ship_type may be an IMO numeric code or free text; codes are mapped.)

Live fetch: AISHub (free tier, registration required) —
  python3 -m src.ais_verify --aishub <username>

Outputs (data/detections/):
  ais_matches.csv  — detections matched to real AIS
  type_profile.csv — monthly type composition (estimate + AIS when present)
  ais_report.json  — machine-readable summary
"""
import os, sys, json, glob, csv, argparse
from datetime import datetime, timezone
import numpy as np
import pandas as pd
import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import DATA_DIR, DET_DIR, S1_DIR
from analysis import load_scenes

AIS_DIR = os.path.join(DATA_DIR, "ais")
AIS_README = os.path.join(AIS_DIR, "README.md")

# matching tolerances
MATCH_MAX_DIST_M = 600.0
MATCH_MAX_MIN = 45.0

# IMO AIS ship-type codes -> Arabic label (code ranges per IMO resolution)
IMO_TYPE_LABELS = {
    (30, 39): "صيد",
    (40, 49): "سرعة عالية",
    (50, 59): "إرشاد/قطر/خدمات",
    (60, 69): "ركاب",
    (70, 79): "بضائع (Cargo)",
    (80, 89): "ناقلة (Tanker)",
    (90, 99): "أخرى",
}

# Arabic classes used by the dimension estimate and by the report
EST_CLASSES = [
    "صغير/صيد", "بضائع عامة", "صبّ جاف/بضائع",
    "حاويات/ناقلة كبيرة", "كبيرة جدًا (حاويات/ناقلة)", "غير محدد",
]


def ensure_ais_dir():
    os.makedirs(AIS_DIR, exist_ok=True)
    if not os.path.exists(AIS_README):
        with open(AIS_README, "w", encoding="utf-8") as f:
            f.write("""# بيانات AIS — التحقق من هويات السفن

ضع ملفات AIS هنا بتنسيق JSON Lines أو CSV. سطر واحد لكل رسالة، بنفس أسماء الأعمدة:

| الحقل | الوصف | مثال |
|---|---|---|
| timestamp | وقت الرسالة ISO 8601 (UTC) | 2026-08-06T03:30:00Z |
| lon / lat | موقع السفينة لحظة البث | 35.7602 / 35.5264 |
| mmsi | معرّف المحطة البحرية (9 أرقام) | 371234000 |
| imo | رقم IMO (اختياري) | 9123456 |
| name | اسم السفينة | EXAMPLE |
| ship_type | نوعها (نص أو رمز IMO) | Cargo / 70 |
| length_m / width_m | أبعاد السفينة | 180 / 28 |
| sog / cog | السرعة واتجاه المسار | 0.1 / 123.0 |
| destination | وجهة الرحلة (اختياري) | LATAKIA |

- التصدير من MarineTraffic / AISHub / وحدة الاستقبال المحلية: حوّل صفوفه إلى
  هذا التنسيق (سكربت التحويل الموثق في README الرئيسي).
- الجلب المباشر من AISHub (مجاني بحد أقصى ~1,000 رسالة/يوم):
  `python3 -m src.ais_verify --aishub <اسم-المستخدم>`
- لا تضع بيانات مركّبة أو مفترضة هنا: كل ما يُقرأ من هذا المجلد يُعرض في
  الواجهة كـ«مطابقة AIS حقيقية»، وكل ما عدا ذلك يُعرض صراحةً كـ«تقدير من
  الأبعاد».
""")


def _parse_ship_type(x):
    """IMO numeric code -> Arabic label; free text kept as-is."""
    if x is None or (isinstance(x, float) and np.isnan(x)) or str(x).strip() == "":
        return None
    s = str(x).strip()
    try:
        code = int(float(s))
    except ValueError:
        return s
    for (lo, hi), lab in IMO_TYPE_LABELS.items():
        if lo <= code <= hi:
            return lab
    return s


def list_ais_files():
    return sorted(glob.glob(os.path.join(AIS_DIR, "*.jsonl")) +
                  glob.glob(os.path.join(AIS_DIR, "*.csv")))


def load_ais():
    """Read every AIS file in data/ais/ into one tidy DataFrame.
    Returns empty DataFrame when no files exist (never fails)."""
    files = list_ais_files()
    if not files:
        return pd.DataFrame()
    frames = []
    for f in files:
        try:
            if f.endswith(".jsonl"):
                df = pd.read_json(f, lines=True)
            else:
                df = pd.read_csv(f)
            frames.append(df)
        except Exception as e:
            print(f"[ais] skip {os.path.basename(f)}: {e}")
    if not frames:
        return pd.DataFrame()
    ais = pd.concat(frames, ignore_index=True)
    need = {"timestamp", "lon", "lat"}
    if not need.issubset(ais.columns):
        return pd.DataFrame()
    ais["timestamp"] = pd.to_datetime(ais["timestamp"], utc=True, errors="coerce")
    ais = ais.dropna(subset=["timestamp", "lon", "lat"])
    ais = ais[(ais["lon"].between(35.0, 36.5)) & (ais["lat"].between(34.5, 36.5))]
    if "ship_type" in ais.columns:
        ais["ship_type_ar"] = ais["ship_type"].apply(_parse_ship_type)
    else:
        ais["ship_type_ar"] = None
    return ais.reset_index(drop=True)


def _haversine_m(lon1, lat1, lon2, lat2):
    R = 6371000.0
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dp = np.radians(lat2 - lat1)
    dl = np.radians(lon2 - lon1)
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * R * np.arcsin(np.sqrt(a))


def match_detections(scenes=None, ais=None, max_dist_m=MATCH_MAX_DIST_M,
                     max_min=MATCH_MAX_MIN):
    """Match every SAR detection to the closest real AIS message.
    Returns (df, stats): df has one row per detection with ais_* columns
    (empty when no AIS data), stats summarises the matching."""
    ais = ais if ais is not None else load_ais()
    scenes = scenes if scenes is not None else load_scenes()
    good = scenes[scenes["error"].isna() | (scenes["error"] == "")].copy()
    good["dt"] = pd.to_datetime(good["datetime"])

    rows = []
    for _, r in good.iterrows():
        vj = os.path.normpath(os.path.join(S1_DIR, r["id"], "vessels.json"))
        if not os.path.exists(vj):
            continue
        for v in json.load(open(vj, encoding="utf-8")):
            rows.append(dict(
                scene_id=r["id"], acquisition=r["dt"],
                vessel_id=v["vessel_id"], lon=v["lon"], lat=v["lat"],
                length_m=v.get("length_m"), width_m=v.get("width_m"),
                peak_db=v.get("peak_db"), zone=v.get("zone")))
    det = pd.DataFrame(rows)

    if len(ais) == 0 or len(det) == 0:
        for c in ["mmsi", "imo", "ais_name", "ais_ship_type", "ais_length_m",
                  "ais_width_m", "ais_dist_m", "ais_gap_min", "ais_sog",
                  "ais_destination"]:
            det[c] = np.nan
        det["is_ais"] = False
        return det, dict(ais_available=False, n_ais_messages=0,
                         n_detections=len(det), n_matched=0, match_rate=0.0,
                         n_ais_types=0)

    # index AIS by time buckets for a cheap pre-filter
    ais = ais.sort_values("timestamp").reset_index(drop=True)
    hits = []
    for i, d in det.iterrows():
        t0, t1 = d["acquisition"] - pd.Timedelta(minutes=max_min), \
                 d["acquisition"] + pd.Timedelta(minutes=max_min)
        cand = ais[(ais["timestamp"] >= t0) & (ais["timestamp"] <= t1)]
        if len(cand) == 0:
            continue
        dists = _haversine_m(d["lon"], d["lat"], cand["lon"].values, cand["lat"].values)
        j = int(np.argmin(dists))
        if dists[j] <= max_dist_m:
            a = cand.iloc[j]
            hits.append((i, a, float(dists[j]),
                         float(abs((a["timestamp"] - d["acquisition"]).total_seconds()) / 60.0)))
    match_map = {}
    for i, a, dist, gap in hits:
        if i not in match_map or gap < match_map[i][0]:
            match_map[i] = (gap, i, a, dist)

    n_matched = 0
    for i, (_, _, a, dist) in match_map.items():
        n_matched += 1
        det.loc[i, "mmsi"] = a.get("mmsi")
        det.loc[i, "imo"] = a.get("imo")
        det.loc[i, "ais_name"] = a.get("name")
        det.loc[i, "ais_ship_type"] = a.get("ship_type_ar") or _parse_ship_type(a.get("ship_type"))
        det.loc[i, "ais_length_m"] = a.get("length_m")
        det.loc[i, "ais_width_m"] = a.get("width_m")
        det.loc[i, "ais_dist_m"] = dist
        det.loc[i, "ais_gap_min"] = gap
        det.loc[i, "ais_sog"] = a.get("sog")
        det.loc[i, "ais_destination"] = a.get("destination")
    det["is_ais"] = det["mmsi"].notna()

    stats = dict(
        ais_available=True,
        n_ais_messages=int(len(ais)),
        ais_time_span=[ais["timestamp"].min().strftime("%Y-%m-%d"),
                       ais["timestamp"].max().strftime("%Y-%m-%d")],
        n_detections=int(len(det)),
        n_matched=int(n_matched),
        match_rate=round(float(n_matched / max(len(det), 1) * 100), 1),
        n_ais_types=int(det["ais_ship_type"].notna().sum()),
    )
    return det, stats


def estimate_type(length_m, width_m=None):
    """Dimension-based type estimate (SAR-only, clearly approximate).

    Length-only classification: Sentinel-1's point-spread function inflates
    the cross-range width by ~1.5-2x (median W/L here is 1.6 — ships appear
    nearly square), so the beam ratio cannot separate tankers from container
    ships at 10 m. The classes below are therefore coarse length bands with
    honest labels; REAL AIS matches (when present) supersede them entirely.
    Returns (type_ar, confidence)."""
    if length_m is None or (isinstance(length_m, float) and np.isnan(length_m)):
        return "غير محدد", "منخفضة"
    L = float(length_m)
    if L < 90:
        return "صغير/صيد", "متوسطة"
    if L < 160:
        return "بضائع عامة", "متوسطة"
    if L < 240:
        # bulk/general; container feeders of this size are indistinguishable
        return "صبّ جاف/بضائع", "منخفضة"
    if L < 310:
        return "حاويات/ناقلة كبيرة", "منخفضة"
    return "كبيرة جدًا (حاويات/ناقلة)", "متوسطة"


def type_profile(scenes=None, det=None):
    """Monthly composition by estimated type (and real AIS type when matched).
    Returns a tidy DataFrame with one row per (month, class)."""
    det = det if det is not None else match_detections(scenes)[0]
    if len(det) == 0:
        return pd.DataFrame()
    d = det.copy()
    d["est_type"], d["est_conf"] = zip(*d.apply(
        lambda r: estimate_type(r.get("length_m"), r.get("width_m")), axis=1))
    d["ym"] = d["acquisition"].dt.strftime("%Y-%m")
    # effective type: real AIS type wins when a match exists
    d["eff_type"] = d["ais_ship_type"].where(d["is_ais"], d["est_type"])
    d["type_source"] = np.where(d["is_ais"], "AIS حقيقي", "تقدير أبعاد")
    rows = []
    for (ym, cls), g in d.groupby(["ym", "eff_type"]):
        rows.append(dict(ym=ym, type=cls, n=len(g),
                         n_ais=int(g["is_ais"].sum()),
                         n_est=int((~g["is_ais"]).sum())))
    out = pd.DataFrame(rows).sort_values(["ym", "type"]).reset_index(drop=True)
    out.to_csv(os.path.join(DET_DIR, "type_profile.csv"), index=False)
    return out


def ais_report(scenes=None, det=None, stats=None):
    """Machine-readable summary -> data/detections/ais_report.json."""
    det = det if det is not None else match_detections(scenes)[0]
    stats = stats or {}
    report = dict(
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        ais_available=bool(stats.get("ais_available", False)),
        ais_files=[os.path.basename(f) for f in list_ais_files()],
        ais_messages=int(stats.get("n_ais_messages", 0)),
        ais_time_span=stats.get("ais_time_span", []),
        matching=dict(max_dist_m=MATCH_MAX_DIST_M, max_time_min=MATCH_MAX_MIN,
                      n_detections=int(stats.get("n_detections", len(det))),
                      n_matched=int(stats.get("n_matched", 0)),
                      match_rate=float(stats.get("match_rate", 0.0))),
    )
    if len(det):
        det = det.copy()
        det["est_type"], det["est_conf"] = zip(*det.apply(
            lambda r: estimate_type(r.get("length_m"), r.get("width_m")), axis=1))
        report["dimension_estimate"] = dict(
            total_classified=int(det["est_type"].notna().sum()),
            by_type={k: int(v) for k, v in det["est_type"].value_counts().items()},
            by_confidence={k: int(v) for k, v in det["est_conf"].value_counts().items()},
            note="تقدير من أبعاد SAR فقط — ليس بديلاً عن AIS",
        )
        if stats.get("ais_available"):
            m = det[det["is_ais"]]
            report["real_ais"] = dict(
                matched=int(len(m)),
                by_type={k: int(v) for k, v in m["ais_ship_type"].value_counts().items()},
                median_dist_m=round(float(m["ais_dist_m"].median()), 1) if len(m) else None,
                median_gap_min=round(float(m["ais_gap_min"].median()), 1) if len(m) else None,
            )
    with open(os.path.join(DET_DIR, "ais_report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    return report


def fetch_aishub(username, out_dir=None):
    """Fetch live AIS messages from AISHub (free tier). Needs a registered
    username; fails gracefully with a clear message otherwise."""
    url = ("http://data.aishub.net/ws.php?username=%s&format=1&output=csv&compressed=0"
           % requests.utils.quote(username))
    try:
        r = requests.get(url, timeout=60)
        r.raise_for_status()
    except Exception as e:
        raise RuntimeError(f"AISHub fetch failed: {e}")
    text = r.text
    if "Error" in text[:200] or text.strip().startswith("<?xml"):
        raise RuntimeError(f"AISHub rejected the request: {text[:200]}")
    out_dir = out_dir or AIS_DIR
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, f"aishub_{datetime.now():%Y%m%d}.csv")
    with open(out, "w", encoding="utf-8") as f:
        f.write(text)
    # quick sanity parse
    n = sum(1 for _ in csv.reader(text.splitlines())) - 1
    print(f"AISHub: {n} messages -> {out}")
    return out


# ---------------------------------------------------------------------------
# charts (plotly, same dark palette as the rest of the dashboard)
# ---------------------------------------------------------------------------
def chart_type_profile(profile):
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    if len(profile) == 0:
        return None
    piv = profile.pivot(index="ym", columns="type", values="n").fillna(0)
    piv = piv.reindex(sorted(piv.index))
    cols = EST_CLASSES
    cols = [c for c in cols if c in piv.columns] + [c for c in piv.columns if c not in cols]
    palette = {"صغير/صيد": "#94A3B8", "بضائع عامة": "#38BDF8",
               "صبّ جاف/بضائع": "#A78BFA", "حاويات/ناقلة كبيرة": "#F59E0B",
               "كبيرة جدًا (حاويات/ناقلة)": "#F87171", "غير محدد": "#6B7280"}
    fig = make_subplots(specs=[[{"secondary_y": False}]])
    for c in cols:
        fig.add_bar(x=piv.index, y=piv[c], name=c, marker_color=palette.get(c, "#64748B"))
    fig.update_layout(barmode="stack", template="plotly_dark",
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      font=dict(family="IBM Plex Sans Arabic", size=12, color="#F0F0F0"),
                      height=380, margin=dict(l=10, r=10, t=30, b=10),
                      legend=dict(orientation="h", y=-0.18),
                      xaxis=dict(title="", showgrid=False),
                      yaxis=dict(title="عدد السفن", gridcolor="#32363E"))
    return fig


def chart_type_donut(profile):
    import plotly.graph_objects as go
    if len(profile) == 0:
        return None
    tot = profile.groupby("type")["n"].sum().sort_values(ascending=False)
    palette = {"صغير/صيد": "#94A3B8", "بضائع عامة": "#38BDF8",
               "صبّ جاف/بضائع": "#A78BFA", "حاويات/ناقلة كبيرة": "#F59E0B",
               "كبيرة جدًا (حاويات/ناقلة)": "#F87171", "غير محدد": "#6B7280"}
    fig = go.Figure(go.Pie(labels=tot.index, values=tot.values, hole=0.62,
                           marker=dict(colors=[palette.get(c, "#64748B") for c in tot.index],
                                       line=dict(color="#14161A", width=2)),
                           textinfo="label+percent", textposition="outside",
                           hovertemplate="%{label}: %{value:,} سفينة (%{percent})<extra></extra>"))
    fig.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)",
                      font=dict(family="IBM Plex Sans Arabic", size=12, color="#F0F0F0"),
                      height=380, margin=dict(l=10, r=10, t=30, b=10),
                      showlegend=False)
    return fig


def run(scenes=None):
    """Regenerate all AIS outputs from current data."""
    det, stats = match_detections(scenes)
    profile = type_profile(scenes, det)
    report = ais_report(scenes, det, stats)
    if stats.get("ais_available") and len(det[det["is_ais"]]):
        m = det[det["is_ais"]]
        m.to_csv(os.path.join(DET_DIR, "ais_matches.csv"), index=False,
                 encoding="utf-8-sig")
        print(f"ais_matches.csv: {len(m)} matched records")
    print("ais report:", report["ais_available"],
          "| detections:", len(det), "| matched:", stats.get("n_matched", 0),
          "| profile months:", profile["ym"].nunique() if len(profile) else 0)
    return det, stats, profile, report


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--aishub", type=str, default=None,
                    help="AISHub username to fetch live AIS into data/ais/")
    args = ap.parse_args()
    if args.aishub:
        fetch_aishub(args.aishub)
    run()
