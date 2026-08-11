# -*- coding: utf-8 -*-
"""
STAC search & scene selection on Microsoft Planetary Computer.
Real Copernicus Sentinel-1 RTC / GRD and Sentinel-2 L2A items.
"""
import calendar, json, os
from datetime import datetime, timezone

import requests
from pystac import Item

from config import PC_API, AOI_BBOX_4326, COLLECTIONS, TIME_RANGE

CACHE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "stac_cache")


def search_items(collection, dt, limit=500):
    items, token = [], None
    while True:
        body = {"collections": [collection], "bbox": AOI_BBOX_4326,
                "datetime": dt, "limit": min(limit, 100)}
        if token:
            body["token"] = token
        r = requests.post(f"{PC_API}/search", json=body, timeout=120)
        r.raise_for_status()
        js = r.json()
        items += js.get("features", [])
        nxt = [l for l in js.get("links", []) if l.get("rel") == "next"]
        if not nxt:
            break
        token = requests.utils.parse_qs(requests.utils.urlparse(nxt[0]["href"]).query).get("token", [None])[0]
        if not token:
            break
    return items


def month_bounds(year, month):
    d1 = f"{year:04d}-{month:02d}-01T00:00:00Z"
    d2 = datetime(year, month, calendar.monthrange(year, month)[1], 23, 59, 59, tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return f"{d1}/{d2}"


def iter_months(y0=2022, m0=1, y1=None, m1=None):
    """Iterate months within config.TIME_RANGE (default 2022-01 .. TIME_RANGE end)."""
    if y1 is None:
        y1 = int(TIME_RANGE[1][:4])
        m1 = int(TIME_RANGE[1][5:7])
    y, m = y0, m0
    while (y, m) <= (y1, m1):
        yield y, m
        m += 1
        if m > 12:
            y, m = y + 1, 1


def select_s1_scenes(per_month=4, force=False):
    """Pick up to `per_month` RTC scenes per month (mixed orbit passes, spread dates)."""
    path = os.path.join(CACHE, "s1_selected.json")
    os.makedirs(CACHE, exist_ok=True)
    if not force and os.path.exists(path):
        return json.load(open(path, encoding="utf-8"))

    selected = []
    for y, m in iter_months():
        items = search_items(COLLECTIONS["s1_rtc"], month_bounds(y, m))
        if not items:
            continue
        # prefer IW VV+VH, keep both orbit states
        good = [it for it in items
                if it["properties"].get("sar:instrument_mode") == "IW"
                and "VV" in it["properties"].get("sar:polarizations", [])
                and "VH" in it["properties"].get("sar:polarizations", [])]
        if not good:
            good = items
        good.sort(key=lambda it: it["properties"]["datetime"])
        # group by orbit pass, then spread picks across the month
        asc = sorted([it for it in good if it["properties"].get("sat:orbit_state") == "ascending"],
                     key=lambda it: it["properties"]["datetime"])
        desc = sorted([it for it in good if it["properties"].get("sat:orbit_state") == "descending"],
                      key=lambda it: it["properties"]["datetime"])
        pools = [asc, desc]
        taken, n = [], 0
        for pool in pools:
            if not pool:
                continue
            step = max(1, len(pool) // max(1, per_month))
            for j in range(0, len(pool), step):
                if n >= per_month:
                    break
                taken.append(pool[j])
                n += 1
        # ensure minimum spread if duplicated orbit times
        seen = set()
        uniq = []
        for it in taken:
            if it["id"] not in seen:
                seen.add(it["id"])
                uniq.append(it)
        for it in uniq[:per_month]:
            selected.append({
                "id": it["id"], "datetime": it["properties"]["datetime"],
                "sat": it["properties"]["platform"], "orbit": it["properties"].get("sat:orbit_state"),
                "year": y, "month": m,
                "bbox": it["bbox"], "collection": COLLECTIONS["s1_rtc"],
            })
    json.dump(selected, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return selected


def select_s2_scenes(per_month=2, max_cloud=45.0, force=False):
    """Lowest-cloud S2 L2A scenes per month (for optical verification)."""
    path = os.path.join(CACHE, "s2_selected.json")
    if not force and os.path.exists(path):
        return json.load(open(path, encoding="utf-8"))
    selected = []
    for y, m in iter_months():
        items = search_items(COLLECTIONS["s2"], month_bounds(y, m))
        items = [it for it in items if it["properties"].get("eo:cloud_cover", 100) <= max_cloud]
        items.sort(key=lambda it: it["properties"].get("eo:cloud_cover", 100))
        for it in items[:per_month]:
            selected.append({
                "id": it["id"], "datetime": it["properties"]["datetime"],
                "cloud": it["properties"].get("eo:cloud_cover"), "year": y, "month": m,
                "sat": it["properties"].get("platform", "S2"),
                "bbox": it["bbox"], "collection": COLLECTIONS["s2"],
            })
    json.dump(selected, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return selected


def load_item(rec):
    """Re-fetch the STAC item by id (to get fresh signed asset hrefs)."""
    body = {"collections": [rec["collection"]], "ids": [rec["id"]], "limit": 5}
    r = requests.post(f"{PC_API}/search", json=body, timeout=120)
    r.raise_for_status()
    feats = r.json().get("features", [])
    return Item.from_dict(feats[0]) if feats else None


if __name__ == "__main__":
    s1 = select_s1_scenes()
    s2 = select_s2_scenes()
    print("S1 selected:", len(s1), "| months:", sorted({f"{r['year']}-{r['month']:02d}" for r in s1})[:3], "...")
    print("S2 selected:", len(s2))
    from collections import Counter
    print("S1 per month:", Counter(f"{r['year']}-{r['month']:02d}" for r in s1))
