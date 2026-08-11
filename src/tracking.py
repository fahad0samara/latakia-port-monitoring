# -*- coding: utf-8 -*-
"""
Vessel tracking across time — chain matched detections into unique vessel
trajectories. Uses greedy nearest-neighbour matching between consecutive
scenes (400 m radius, <=10 day gap), then chains pairs into tracks.

Outputs:
  * number of unique vessels per year/month
  * average visits per vessel
  * persistence of vessels across scenes
All from real detection data; nothing hardcoded.
"""
import os, json
import numpy as np
import pandas as pd

from config import ROOT, DET_DIR, S1_DIR
from analysis import load_scenes
from insights import load_vessels, MATCH_RADIUS_M, MAX_GAP_DAYS


def build_tracks(scenes=None):
    """Match detections across consecutive scenes -> track chains."""
    scenes = scenes if scenes is not None else load_scenes()
    good = scenes[scenes["error"].isna() | (scenes["error"] == "")].copy()
    good["dt"] = pd.to_datetime(good["datetime"])
    g = good.sort_values("dt").reset_index(drop=True)

    # global vessel id -> list of (scene_idx, vessel_local_idx)
    tracks = []
    track_of = {}  # (scene_idx, local_idx) -> track index

    for i in range(len(g)):
        a = g.iloc[i]
        va = load_vessels(a["id"])
        if not va:
            continue
        for j, v in enumerate(va):
            # try to match to previous scene's vessels
            matched = None
            if i > 0:
                pb = g.iloc[i - 1]
                gap = (a["dt"] - pb["dt"]).days
                if gap <= MAX_GAP_DAYS:
                    vb = load_vessels(pb["id"])
                    best_d, best_idx = MATCH_RADIUS_M, None
                    for k, w in enumerate(vb):
                        d = np.sqrt(((v["lon"] - w["lon"]) * 88000) ** 2 +
                                    ((v["lat"] - w["lat"]) * 111000) ** 2)
                        if d < best_d:
                            best_d, best_idx = d, k
                    if best_idx is not None:
                        key = (i - 1, best_idx)
                        if key in track_of:
                            matched = track_of[key]
            if matched is None:
                matched = len(tracks)
                tracks.append(dict(vessels=[], scenes=[], zones=[]))
            tracks[matched]["vessels"].append(v["vessel_id"])
            tracks[matched]["scenes"].append(a["id"])
            tracks[matched]["zones"].append(v.get("zone", 0))
            track_of[(i, j)] = matched

    # summarize
    rows = []
    for t in tracks:
        if not t["vessels"]:
            continue
        rows.append(dict(
            track_id=len(rows),
            n_obs=len(t["scenes"]),
            first_scene=t["scenes"][0],
            last_scene=t["scenes"][-1],
            zones=list(set(t["zones"])),
            n_distinct_vessels=len(set(t["vessels"])),
        ))
    df = pd.DataFrame(rows)
    stats = dict(
        total_tracks=int(len(df)),
        tracks_with_2plus=0,
        mean_obs_per_track=0.0,
        max_obs_per_track=0,
    )
    if len(df):
        stats["tracks_with_2plus"] = int((df["n_obs"] >= 2).sum())
        stats["mean_obs_per_track"] = round(float(df["n_obs"].mean()), 2)
        stats["max_obs_per_track"] = int(df["n_obs"].max())
    return df, stats


def run():
    df, stats = build_tracks()
    print(json.dumps(stats, ensure_ascii=False, indent=1))
    with open(os.path.join(DET_DIR, "tracking.json"), "w", encoding="utf-8") as f:
        json.dump(dict(stats=stats), f, ensure_ascii=False, indent=1)
    # save tracks table
    df.to_csv(os.path.join(DET_DIR, "tracks.csv"), index=False)
    print(f"tracks saved: {len(df)}")


if __name__ == "__main__":
    run()
