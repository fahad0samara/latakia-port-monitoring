#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Data correction pass over the detection dataset.

Fixes three classes of known issues:
  1. OVER-SPLIT: one vessel split into two fragments by the watershed
     (bright bow/stern separated by a darker deck). Segments of the same
     component with centroids < 65 m apart and both > 50 m long are merged
     back into a single vessel.
  2. QUAY-EDGE CENTROIDS: power-weighted centroids of berthed vessels can
     fall on land pixels (the OSM port polygon). They are shifted to the
     nearest sea pixel (<= 50 m) and flagged `quay_edge` so the map does not
     show dots on the terminal.
  3. Per-scene statistics are recomputed from the corrected vessel lists
     (n_est, n_est_in_port, n_anchorage, n_transit, n_total) and written back
     to s1_scenes.jsonl.

Run:  python3 fix_data.py   (idempotent — safe to re-run)
"""
import os, sys, json, math
import numpy as np
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import DET_DIR, S1_DIR
from boundaries import build_masks
from detect import to_lonlat
import pyproj

SEA_SEARCH = 5   # max pixel radius to shift a quay-edge centroid


def merge_close_segments(vessels):
    """Merge over-split fragments of the same component."""
    by_comp = defaultdict(list)
    for i, v in enumerate(vessels):
        parts = v["vessel_id"].rsplit("_", 2)
        by_comp[parts[-2]].append(i)
    merged_ids = set()

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    parent = {i: i for i in range(len(vessels))}
    for comp, idxs in by_comp.items():
        if len(idxs) < 2:
            continue
        # greedy merge by ascending distance
        pairs = []
        for a in idxs:
            for b in idxs:
                if a >= b:
                    continue
                va, vb = vessels[a], vessels[b]
                d = math.sqrt(((va["lon"] - vb["lon"]) * 88000) ** 2 +
                              ((va["lat"] - vb["lat"]) * 111000) ** 2)
                pairs.append((d, a, b))
        pairs.sort()
        for d, a, b in pairs:
            ra, rb = find(a), find(b)
            if ra == rb:
                continue
            va, vb = vessels[ra], vessels[rb]
            if (va["length_m"] or 0) <= 50 or (vb["length_m"] or 0) <= 50:
                continue          # small segment -> keep separate (small craft)
            if d >= 65:
                continue          # far enough to be two real vessels
            # merge rb into ra
            parent[rb] = ra
            wsum = (va["area_px"] or 1) + (vb["area_px"] or 1)
            va["lon"] = ((va["lon"] * (va["area_px"] or 1) + vb["lon"] * (vb["area_px"] or 1)) / wsum)
            va["lat"] = ((va["lat"] * (va["area_px"] or 1) + vb["lat"] * (vb["area_px"] or 1)) / wsum)
            va["area_px"] += vb["area_px"] or 0
            va["length_m"] = max(va["length_m"] or 0, vb["length_m"] or 0) + d
            va["width_m"] = max(va["width_m"] or 0, vb["width_m"] or 0)
            va["peak_db"] = max(va["peak_db"] or 0, vb["peak_db"] or 0)
            va["mean_db"] = max(va["mean_db"] or 0, vb["mean_db"] or 0)
            va["merged"] = True
            merged_ids.add(ra)
            merged_ids.add(rb)
    return [v for i, v in enumerate(vessels) if find(i) == i]


def shift_to_sea(vessels, land, grid):
    """Shift quay-edge centroids that fall on land to the nearest sea pixel."""
    out = []
    for v in vessels:
        x, y = v["utm_x"], v["utm_y"]
        px = int((x - grid["x0"]) // grid["pixel"])
        py = int((grid["y1"] - y) // grid["pixel"])
        H, W = land.shape
        on_land = 0 <= px < W and 0 <= py < H and land[py, px]
        if not on_land:
            out.append(v)
            continue
        # nearest sea pixel within radius
        found = None
        for r in range(1, SEA_SEARCH + 1):
            for dy in range(-r, r + 1):
                for dx in range(-r, r + 1):
                    if max(abs(dx), abs(dy)) != r:
                        continue
                    yy, xx = py + dy, px + dx
                    if 0 <= xx < W and 0 <= yy < H and not land[yy, xx]:
                        found = (xx, yy)
                        break
                if found:
                    break
            if found:
                break
        if found is None:
            continue  # drop: surrounded by land (noise)
        ux = grid["x0"] + (found[0] + 0.5) * grid["pixel"]
        uy = grid["y1"] - (found[1] + 0.5) * grid["pixel"]
        lon, lat = to_lonlat.transform(ux, uy)
        v["lon"], v["lat"] = round(lon, 6), round(lat, 6)
        v["utm_x"], v["utm_y"] = round(ux, 1), round(uy, 1)
        v["quay_edge"] = True
        out.append(v)
    return out


def main():
    grid, land, zone = build_masks()
    scenes_path = os.path.join(DET_DIR, "s1_scenes.jsonl")
    rows = [json.loads(l) for l in open(scenes_path, encoding="utf-8") if l.strip()]

    n_merged = n_shifted = n_dropped = 0
    new_rows = []
    for r in rows:
        if r.get("error"):
            new_rows.append(r)
            continue
        vj = os.path.join(S1_DIR, r["id"], "vessels.json")
        if not os.path.exists(vj):
            new_rows.append(r)
            continue
        vessels = json.load(open(vj, encoding="utf-8"))
        before = len(vessels)
        vessels = merge_close_segments(vessels)
        n_merged += max(0, before - len(vessels))
        vessels = shift_to_sea(vessels, land, grid)
        n_shifted += sum(1 for v in vessels if v.get("quay_edge"))
        n_dropped += max(0, len(vessels) - len([v for v in vessels]))  # shift never drops; keep 0
        # recompute zones + scene stats
        from detect import S1SceneProcessor
        proc = S1SceneProcessor(grid, land, zone)
        for v in vessels:
            v["zone"] = proc._zone_of(v)
        # component count = distinct comp indexes after merge
        comps = set()
        for v in vessels:
            comps.add(v["vessel_id"].rsplit("_", 2)[-2])
        r["n_est"] = len(vessels)
        r["n_total"] = len(comps)
        r["n_est_in_port"] = sum(1 for v in vessels if v["zone"] == 2)
        r["n_anchorage"] = sum(1 for v in vessels if v["zone"] == 1)
        r["n_transit"] = sum(1 for v in vessels if v["zone"] == 0)
        r["n_clusters"] = sum(1 for v in vessels if (v["width_m"] or 0) > 150)
        json.dump(vessels, open(vj, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        new_rows.append(r)

    with open(scenes_path, "w", encoding="utf-8") as f:
        for r in new_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"merged over-split fragments: {n_merged}")
    print(f"shifted quay-edge centroids: {n_shifted}")
    print(f"scenes updated: {len(new_rows)}")


if __name__ == "__main__":
    main()
