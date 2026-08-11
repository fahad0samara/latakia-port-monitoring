# -*- coding: utf-8 -*-
"""
Process the Port of Baniyas (مرفأ بانياس — oil terminal) with the SAME
pipeline as Latakia/Tartus, then produce monthly/yearly series for the
regional comparison.

Baniyas boundary: derived from REAL OSM objects only —
  * port_boundary: OSM breakwater way 1340825778, a closed ring that
    encloses the loading basin (documented in config/baniyas_osm.geojson)
  * breakwaters / jetties / coastline: OSM ways
Same Sentinel-1 RTC scenes are reused (frames cover the whole coast).

Usage:
  python3 src/process_baniyas.py --masks       # build masks only
  python3 src/process_baniyas.py --process --since 2025-01 --to 2026-08 --per-month 3
  python3 src/process_baniyas.py --series      # rebuild csv series
"""
import os, sys, json, argparse
import numpy as np
import pandas as pd
from scipy.ndimage import binary_closing

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import ROOT, CONFIG_DIR, DET_DIR, RTC_EPSG, PIXEL, S1_DIR
from detect import process_scene
from stac import select_s1_scenes

BAN_DIR = os.path.join(ROOT, "data", "baniyas")
BAN_RAW = os.path.join(BAN_DIR, "raw")
os.makedirs(BAN_DIR, exist_ok=True)
os.makedirs(BAN_RAW, exist_ok=True)

BBOX_4326 = [35.90, 35.18, 36.00, 35.27]  # lon_min, lat_min, lon_max, lat_max
ZONES = dict(in_port_m=400, anchorage_m=4000)


def build_masks(force=False):
    cache = os.path.join(CONFIG_DIR, "baniyas_masks.npz")
    meta = os.path.join(CONFIG_DIR, "baniyas_grid.json")
    if not force and os.path.exists(cache) and os.path.exists(meta):
        grid = json.load(open(meta, encoding="utf-8"))
        z = np.load(cache)
        return grid, z["land"], z["zone"]

    from shapely.geometry import shape, box
    from shapely.ops import transform as st, unary_union
    import pyproj
    from rasterio.features import geometry_mask
    from rasterio.transform import from_origin
    from rasterio.warp import transform_bounds

    osm = json.load(open(os.path.join(CONFIG_DIR, "baniyas_osm.geojson"), encoding="utf-8"))
    feats = {ft["properties"]["role"]: shape(ft["geometry"]) for ft in osm["features"]}
    port4326 = feats["port_boundary"]

    t = pyproj.Transformer.from_crs("EPSG:4326", f"EPSG:{RTC_EPSG}", always_xy=True)
    port = st(t.transform, port4326)

    xmin, ymin, xmax, ymax = transform_bounds("EPSG:4326", f"EPSG:{RTC_EPSG}", *BBOX_4326)
    x0 = np.floor(xmin / PIXEL) * PIXEL
    y1 = np.ceil(ymax / PIXEL) * PIXEL
    w = int(np.ceil((xmax - x0) / PIXEL)) + 1
    h = int(np.ceil((y1 - ymin) / PIXEL)) + 1
    grid = dict(epsg=RTC_EPSG, pixel=PIXEL, x0=float(x0), y1=float(y1), width=w, height=h,
                transform=[x0, PIXEL, 0.0, y1, 0.0, -PIXEL])
    json.dump(grid, open(meta, "w", encoding="utf-8"))

    T = from_origin(x0, y1, PIXEL, PIXEL)
    aoi_utm = box(*[x0, y1 - h * PIXEL, x0 + w * PIXEL, y1])
    aoi_4326 = box(*BBOX_4326)

    ne_path = os.path.join(CONFIG_DIR, "ne_10m_land.geojson")
    land = []
    if os.path.exists(ne_path):
        ne = [shape(ft["geometry"]) for ft in json.load(open(ne_path, encoding="utf-8"))["features"]]
        for g in ne:
            if g.is_valid and g.intersects(aoi_4326):
                gc = g.intersection(aoi_4326)
                if gc.is_empty or not gc.is_valid:
                    continue
                gu = st(t.transform, gc)
                if gu.is_valid and gu.intersects(aoi_utm):
                    land.append(gu.intersection(aoi_utm))
    land.append(port.intersection(aoi_utm))
    for ft in osm["features"]:
        role = ft["properties"]["role"]
        if role == "breakwater":
            bw = st(t.transform, shape(ft["geometry"]))
            land.append(bw.buffer(70).intersection(aoi_utm))
        elif role == "jetty":
            jt = st(t.transform, shape(ft["geometry"]))
            land.append(jt.buffer(40).intersection(aoi_utm))
    land_geom = unary_union([g for g in land if not g.is_empty and g.area > 0])
    land_mask = ~geometry_mask([land_geom], out_shape=(h, w), transform=T)
    land_mask = binary_closing(land_mask, iterations=1)

    zone = np.zeros((h, w), dtype=np.uint8)
    zone[land_mask] = 9
    sea = ~land_mask
    in_anchor = geometry_mask([port.buffer(4000).intersection(aoi_utm)], out_shape=(h, w),
                              transform=T, invert=True)
    in_port = geometry_mask([port.buffer(400).intersection(aoi_utm)], out_shape=(h, w),
                            transform=T, invert=True)
    zone[sea & in_anchor & ~in_port] = 1
    zone[sea & in_port] = 2
    np.savez(cache, land=land_mask, zone=zone)
    return grid, land_mask, zone


def process(since=None, to=None, per_month=None, workers=6, limit=None):
    grid, land, zone = build_masks()
    print("grid:", grid["width"], "x", grid["height"], "| land px:", int(land.sum()))
    recs = select_s1_scenes(8)
    print("candidates:", len(recs))

    if since or to:
        import datetime as dt
        def d(s): return dt.date.fromisoformat(s)
        recs = [r for r in recs
                if (not since or d(r["datetime"][:10]) >= d(since))
                and (not to or d(r["datetime"][:10]) <= d(to))]
        print("after date filter:", len(recs))
    if per_month:
        from collections import defaultdict
        bym = defaultdict(list)
        for r in recs:
            bym[r["datetime"][:7]].append(r)
        recs = []
        for ym in sorted(bym):
            recs.extend(bym[ym][:per_month])
        print("after monthly sampling:", len(recs))
    if limit:
        recs = recs[:limit]

    out_path = os.path.join(BAN_DIR, "baniyas_scenes.jsonl")
    done = set()
    if os.path.exists(out_path):
        done = {json.loads(l)["id"] for l in open(out_path, encoding="utf-8") if l.strip()}
    todo = [r for r in recs if r["id"] not in done]
    print("to process:", len(todo))

    from shapely.geometry import shape as _shape
    osm = json.load(open(os.path.join(CONFIG_DIR, "baniyas_osm.geojson"), encoding="utf-8"))
    tgeoms = {ft["properties"]["role"]: _shape(ft["geometry"]) for ft in osm["features"]}

    from concurrent.futures import ThreadPoolExecutor, as_completed
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(process_scene, r, grid, land, zone, False, BBOX_4326, tgeoms, BAN_RAW): r for r in todo}
        for i, fut in enumerate(as_completed(futs), 1):
            r = futs[fut]
            try:
                out = fut.result()
            except Exception as e:
                out = dict(id=r["id"], datetime=r["datetime"], error=f"exc: {e}")
            with open(out_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(out, ensure_ascii=False) + "\n")
            tag = "ERR" if out.get("error") else "OK "
            print(f"[{i}/{len(todo)}] {tag} {r['id'][:34]} port={out.get('n_est_in_port','-')} "
                  f"anch={out.get('n_anchorage','-')}", flush=True)
    print("Baniyas processing done")


def build_series():
    rows = []
    with open(os.path.join(BAN_DIR, "baniyas_scenes.jsonl"), encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    df = pd.DataFrame(rows)
    df["dt"] = pd.to_datetime(df["datetime"])
    good = df[df["error"].isna() | (df["error"] == "")].copy()
    good["ym"] = good["dt"].dt.strftime("%Y-%m")
    good["year"] = good["dt"].dt.year
    good["month"] = good["dt"].dt.month

    monthly = good.groupby("ym").agg(
        n_obs=("id", "count"),
        mean_ships_port=("n_est_in_port", "mean"),
        mean_anchorage=("n_anchorage", "mean"),
        max_ships_port=("n_est_in_port", "max"),
        mean_coverage=("coverage", "mean"),
    ).reset_index()
    monthly["year"] = monthly["ym"].str[:4].astype(int)
    monthly["month"] = monthly["ym"].str[5:7].astype(int)
    monthly["mean_ships_port_adj"] = monthly["mean_ships_port"]
    monthly.to_csv(os.path.join(BAN_DIR, "baniyas_monthly.csv"), index=False)

    yearly = monthly.groupby("year").agg(
        n_months=("ym", "count"), n_obs=("n_obs", "sum"),
        annual_mean=("mean_ships_port_adj", "mean"),
        peak_value=("mean_ships_port_adj", "max"),
    ).reset_index()
    # peak month = actual calendar month of the max (not the row index)
    _peak = []
    for y, g in monthly.groupby("year"):
        _peak.append((y, int(g.loc[g["mean_ships_port_adj"].idxmax(), "month"])))
    yearly["peak_month"] = [p for _, p in sorted(_peak)]
    # like-for-like YoY: same calendar months when the later year is partial
    yearly["yoy_pct"] = np.nan
    yearly["yoy_basis"] = ""
    for i in range(1, len(yearly)):
        cur, prev = yearly.iloc[i], yearly.iloc[i - 1]
        cur_months = sorted(monthly[monthly["year"] == cur["year"]]["month"])
        if len(cur_months) == 12:
            a, b = cur["annual_mean"], prev["annual_mean"]
            yearly.loc[yearly.index[i], "yoy_basis"] = "12 شهرًا"
        else:
            cm = monthly[(monthly["year"] == cur["year"]) & (monthly["month"].isin(cur_months))]
            pm = monthly[(monthly["year"] == prev["year"]) & (monthly["month"].isin(cur_months))]
            a = float(cm["mean_ships_port_adj"].mean()) if len(cm) else np.nan
            b = float(pm["mean_ships_port_adj"].mean()) if len(pm) else np.nan
            yearly.loc[yearly.index[i], "yoy_basis"] = f"نفس الأشهر ({cur_months[0]}-{cur_months[-1]})"
        if b and not np.isnan(b):
            yearly.loc[yearly.index[i], "yoy_pct"] = round((a - b) / b * 100, 1)
    yearly.to_csv(os.path.join(BAN_DIR, "baniyas_yearly.csv"), index=False)
    print("Baniyas series saved")
    print(yearly.to_string(index=False))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--masks", action="store_true")
    ap.add_argument("--process", action="store_true")
    ap.add_argument("--series", action="store_true")
    ap.add_argument("--since", type=str, default=None)
    ap.add_argument("--to", type=str, default=None)
    ap.add_argument("--per-month", type=int, default=None)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()
    if args.masks:
        g, l, z = build_masks(force=True)
        print("masks:", g["width"], "x", g["height"], "| land:", int(l.sum()))
    if args.process:
        process(args.since, args.to, args.per_month, args.workers, args.limit)
    if args.series:
        build_series()
