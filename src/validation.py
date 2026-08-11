# -*- coding: utf-8 -*-
"""
Cross-validation of SAR detections against Sentinel-2 optical imagery and
against per-scene quality metrics.

Realistic validation options without a labeled reference dataset:
  1. S1 <-> S2 paired comparison: for S2 scenes within ±4 days of an S1 scene
     (cloud-free over the AOI), compare counts in the port zone.
  2. Detection quality: signal-to-clutter of every detection, land-proximity,
     size plausibility -> flags per detection.
  3. Manual visual verification: per-vessel VV/VH crops + S2 RGB crops are
     shipped with the system for the analyst to inspect (dashboard viewer).
"""
import os, json
import numpy as np
import pandas as pd

from config import DET_DIR
from analysis import load_scenes

S2_JSONL = os.path.join(DET_DIR, "s2_scenes.jsonl")


def load_s2():
    rows = []
    with open(S2_JSONL, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return pd.DataFrame(rows)


def pair_s1_s2(s1=None, s2=None, max_days=4, max_cloud=25.0):
    s1 = s1 if s1 is not None else load_scenes()
    s2 = s2 if s2 is not None else load_s2()
    g1 = s1[s1["error"].isna() | (s1["error"] == "")].copy()
    g2 = s2[(s2["error"].isna() | (s2["error"] == ""))].copy()
    g1["dt"] = pd.to_datetime(g1["datetime"])
    g2["dt"] = pd.to_datetime(g2["datetime"])
    g2 = g2[g2["cloud_pct_aoi"].fillna(100) <= max_cloud]
    pairs = []
    for _, a in g2.iterrows():
        d = (g1["dt"] - a["dt"]).abs()
        dmin = d.min()
        if dmin <= pd.Timedelta(days=max_days):
            b = g1.loc[d.idxmin()]
            pairs.append(dict(
                s2_id=a["id"], s1_id=b["id"], s2_date=a["dt"], s1_date=b["dt"],
                gap_hours=round(dmin.total_seconds() / 3600, 1),
                cloud_pct=a["cloud_pct_aoi"],
                s1_port=int(b["n_est_in_port"]), s2_port=int(a["optical_port"]),
                s1_total=int(b["n_est"]), s2_total=int(a["optical_bright_count"]),
            ))
    return pd.DataFrame(pairs)


def quality_flags(scenes=None):
    """Per-detection quality flags: SNR, size plausibility, land proximity."""
    scenes = scenes if scenes is not None else load_scenes()
    good = scenes[scenes["error"].isna() | (scenes["error"] == "")]
    rows = []
    for _, r in good.iterrows():
        vj = os.path.normpath(os.path.join(DET_DIR, "..", "raw_s1", r["id"], "vessels.json"))
        if not os.path.exists(vj):
            continue
        for v in json.load(open(vj, encoding="utf-8")):
            snr = v["peak_db"] - r["noise_floor_db"]
            flags = []
            if snr < 6:
                flags.append("low_snr")
            if v["length_m"] and (v["length_m"] > 400 or v["width_m"] and v["width_m"] > 200):
                flags.append("size_anomaly")
            if v["length_m"] and v["width_m"] and v["width_m"] > v["length_m"]:
                flags.append("shape_anomaly")
            rows.append(dict(scene=r["id"], date=r["datetime"], zone=v["zone"],
                             snr_db=round(snr, 1), length_m=v["length_m"],
                             flags=",".join(flags)))
    return pd.DataFrame(rows)


def summary(scenes=None):
    s1 = scenes if scenes is not None else load_scenes()
    good = s1[s1["error"].isna() | (s1["error"] == "")]
    qf = quality_flags(good)
    pairs = pair_s1_s2(good)
    out = dict(
        scenes_total=int(len(s1)),
        scenes_usable=int(len(good)),
        scenes_rejected=int(len(s1) - len(good)),
        detections=int(len(qf)),
        low_snr_pct=round(float((qf["snr_db"] < 6).mean() * 100), 1),
        size_anomaly_pct=round(float(qf["flags"].str.contains("size_anomaly").mean() * 100), 1),
        mean_snr_db=round(float(qf["snr_db"].mean()), 1),
        n_cluster_like=int(good.get("n_clusters", pd.Series(0)).sum()) if "n_clusters" in good.columns else 0,
    )
    if len(pairs):
        dp = pairs[pairs["s1_port"] > 0]
        out["s2_pairs"] = len(pairs)
        corr = pairs[["s1_port", "s2_port"]].corr().iloc[0, 1]
        out["s1_s2_corr_port"] = round(float(corr), 3)
        out["s1_s2_mean_gap_h"] = round(float(pairs["gap_hours"].mean()), 1)
        # agreement on busy/quiet
        med = pairs["s1_port"].median()
        busy_agree = float(((pairs["s1_port"] > med) & (pairs["s2_port"] > med)).mean())
        out["busy_agreement_pct"] = round(busy_agree * 100, 1)
    else:
        out["s2_pairs"] = 0
    return out


if __name__ == "__main__":
    print(json.dumps(summary(), ensure_ascii=False, indent=1))
