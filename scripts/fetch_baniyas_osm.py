#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fetch & build the Baniyas (مرفأ بانياس) port boundary from OpenStreetMap.

Baniyas does not have a closed OSM polygon tagged as a port, so the basin
polygon is DERIVED from real OSM features only:
  * port_boundary: polygon = OSM breakwater way 1340825778 + the stretch of
    OSM coastline (way 200075994) between its two nearest points.
  * breakwater: OSM ways 1340825778 / 1340825780 / 1340825775
  * jetty: OSM ways 255681448 / 255681449 / 478479855 / 478479857
  * coastline: OSM way 200075994 (clipped to the AOI)

The derivation is fully documented in the output properties so the boundary
is traceable to real OSM objects — nothing fabricated.

Usage: python3 scripts/fetch_baniyas_osm.py
"""
import os, sys, json, math
import urllib.request, urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "config", "baniyas_osm.geojson")

# Baniyas oil-terminal basin (refinery port)
CENTER = (35.2225, 35.9470)
BBOX = [35.90, 35.18, 36.00, 35.27]  # lon_min, lat_min, lon_max, lat_max
UA = {"User-Agent": "latakia-port-monitor/1.0 (research; OSM data, ODbL)"}


def overpass(query):
    url = "https://overpass-api.de/api/interpreter"
    req = urllib.request.Request(url, data=urllib.parse.urlencode({"data": query}).encode(),
                                 headers=UA)
    return json.load(urllib.request.urlopen(req, timeout=120))["elements"]


def fetch():
    # 1) breakwaters + jetties + coastline in the AOI
    q = f"""
    [out:json][timeout:120];
    (
      way(id:1340825778,1340825780,1340825775);
      way(id:255681448,255681449,478479855,478479857);
      way["natural"="coastline"]({BBOX[1]},{BBOX[0]},{BBOX[3]},{BBOX[2]});
    );
    out geom;
    """
    els = overpass(q)
    coast = [e for e in els if e.get("tags", {}).get("natural") == "coastline"]
    bw = [e for e in els if e["id"] in (1340825778, 1340825780, 1340825775)]
    jt = [e for e in els if e["id"] in (255681448, 255681449, 478479855, 478479857)]
    print("coastline ways:", len(coast), "| breakwaters:", len(bw), "| jetties:", len(jt))

    # coastline covering the basin (200075994 spans 35.18-35.26N)
    main = next((e for e in coast if e["id"] == 200075994), coast[0] if coast else None)
    if main is None:
        raise RuntimeError("no coastline found")

    def line(way):
        return [(p["lon"], p["lat"]) for p in way["geometry"]]

    coast_pts = line(main)

    def nearest(coords, p):
        best, bd = None, 1e9
        for qp in coords:
            d = (qp[0] - p[0]) ** 2 + (qp[1] - p[1]) ** 2
            if d < bd:
                bd, best = d, qp
        return best, math.sqrt(bd)

    # 2) build the basin polygon from the main breakwater + coast closure
    bw_main = next(e for e in bw if e["id"] == 1340825778)
    bw_pts = line(bw_main)
    a, b = bw_pts[0], bw_pts[-1]
    ca, da = nearest(coast_pts, a)
    cb, db = nearest(coast_pts, b)
    i_a = coast_pts.index(ca)
    i_b = coast_pts.index(cb)
    # coastline segment between the two nearest points (shortest arc)
    if i_a > i_b:
        i_a, i_b = i_b, i_a
        ca, cb = cb, ca
    seg = coast_pts[i_a:i_b + 1]
    # polygon: breakwater outward + coast segment + close
    poly = bw_pts + seg
    # close ring
    poly.append(poly[0])
    print(f"basin: breakwater ends -> coast at d={da*111:.0f}m / {db*111:.0f}m, "
          f"coast segment {len(seg)} pts")

    # 3) clip coastline to the AOI bbox for the file
    def clip(pts):
        out, cur = [], []
        for p in pts:
            if BBOX[0] <= p[0] <= BBOX[2] and BBOX[1] <= p[1] <= BBOX[3]:
                cur.append(p)
            elif cur:
                out.append(cur)
                cur = []
        if cur:
            out.append(cur)
        return max(out, key=len) if out else []

    coast_clip = clip(coast_pts)

    features = [
        {"type": "Feature", "properties": {
            "role": "port_boundary", "name": "مرفأ بانياس (مشتق)",
            "derivation": "OSM breakwater way 1340825778 closed along OSM coastline "
                          "way 200075994 (real OSM objects only)"},
         "geometry": {"type": "Polygon", "coordinates": [poly]}},
        {"type": "Feature", "properties": {"role": "breakwater",
                                           "name": "كاسر أمواج (OSM)",
                                           "osm_ids": [1340825778, 1340825780, 1340825775]},
         "geometry": {"type": "MultiLineString",
                      "coordinates": [line(e) for e in bw]}},
        {"type": "Feature", "properties": {"role": "jetty", "name": "أرصفة تحميل (OSM)",
                                           "osm_ids": [e["id"] for e in jt]},
         "geometry": {"type": "MultiLineString",
                      "coordinates": [line(e) for e in jt]}},
        {"type": "Feature", "properties": {"role": "coastline", "name": "خط الساحل (OSM)"},
         "geometry": {"type": "LineString", "coordinates": coast_clip}},
        {"type": "Feature", "properties": {"role": "aoi", "name": "صندوق الدراسة"},
         "geometry": {"type": "Polygon",
                      "coordinates": [[[BBOX[0], BBOX[1]], [BBOX[2], BBOX[1]],
                                       [BBOX[2], BBOX[3]], [BBOX[0], BBOX[3]],
                                       [BBOX[0], BBOX[1]]]]}},
    ]
    gj = {"type": "FeatureCollection", "features": features}
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(gj, f, ensure_ascii=False)
    print("written:", OUT, len(json.dumps(gj)) // 1024, "KB")


if __name__ == "__main__":
    fetch()
