# -*- coding: utf-8 -*-
"""
Latakia Port Activity Monitoring — configuration
Real geographic + data configuration for the Port of Latakia (Syria).
All geometry originates from OpenStreetMap (© OpenStreetMap contributors)
and Natural Earth; all satellite data from Copernicus (ESA) via
Microsoft Planetary Computer STAC.
"""
import json, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_DIR = os.path.join(ROOT, "config")
DATA_DIR = os.path.join(ROOT, "data")
S1_DIR = os.path.join(DATA_DIR, "raw_s1")
S2_DIR = os.path.join(DATA_DIR, "raw_s2")
DET_DIR = os.path.join(DATA_DIR, "detections")
OUT_DIR = os.path.join(ROOT, "outputs")
CHART_DIR = os.path.join(OUT_DIR, "charts")
MAP_DIR = os.path.join(OUT_DIR, "maps")

for d in [CONFIG_DIR, DATA_DIR, S1_DIR, S2_DIR, DET_DIR, OUT_DIR, CHART_DIR, MAP_DIR]:
    os.makedirs(d, exist_ok=True)

# ---------------------------------------------------------------------------
# Study area: derived from the REAL OSM boundary of the Port of Latakia
# (OSM way 722818042 "مرفأ اللاذقية" / "Port of Latakia", industrial=port).
# AOI = port + anchorage + approach waters.
# ---------------------------------------------------------------------------
with open(os.path.join(CONFIG_DIR, "latakia_osm.geojson"), encoding="utf-8") as f:
    OSM_GEOJSON = json.load(f)

def get_feature(role):
    for ft in OSM_GEOJSON["features"]:
        if ft["properties"]["role"] == role:
            return ft
    raise KeyError(role)

AOI_BBOX_4326 = [35.70174, 35.46433, 35.79565, 35.57757]  # lon_min, lat_min, lon_max, lat_max

# Sentinel-1 RTC grid: UTM zone 36N, 10 m pixels, fixed grid so every scene
# is perfectly co-registered (pixel n of scene X == pixel n of scene Y).
RTC_EPSG = 32636
PIXEL = 10.0

# Detection parameters (tuned on real Sentinel-1 RTC data over Latakia)
DETECT = dict(
    lee_filter_size=5,          # speckle filter window
    vv_k=7.0,                   # VV threshold: mu_sea + k*sigma_sea (filtered intensity)
    vh_k=3.5,                   # VH cross-check threshold
    min_peak_db=4.0,            # absolute minimum peak backscatter (gamma0 dB) for a ship
    min_area_px=4,              # minimum component area (10 m pixels)
    max_area_px=3500,           # maximum component area (excludes land remnants)
    sea_sample_margin_m=1200,   # open-sea sample ring for clutter stats (away from coast)
)

# Zone definitions (distances from the REAL OSM port boundary)
ZONES = dict(
    in_port_m=400,          # within 400 m of the port polygon (basin + berths)
    anchorage_m=4000,       # 400 m .. 4 km: anchorage / approach
    # beyond 4 km inside the AOI: transit
)

# Copernicus / Planetary Computer
PC_API = "https://planetarycomputer.microsoft.com/api/stac/v1"
COLLECTIONS = dict(s1_rtc="sentinel-1-rtc", s1_grd="sentinel-1-grd", s2="sentinel-2-l2a")

TIME_RANGE = ("2022-01-01T00:00:00Z", "2026-08-31T23:59:59Z")

# number of S1 scenes to keep per month (evenly spread) for the time series
S1_PER_MONTH = 4
# number of S2 scenes per month (lowest cloud) for optical verification
S2_PER_MONTH = 2
S2_MAX_CLOUD = 45.0
