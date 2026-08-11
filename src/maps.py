# -*- coding: utf-8 -*-
"""
Maps for the Latakia port monitoring system.
  * interactive Folium map (real coordinates, OSM tiles)
  * static PNG density maps on a real Sentinel-1 median basemap
"""
import os, json
import numpy as np
import pandas as pd
import folium
from folium.plugins import HeatMap, MarkerCluster
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from scipy.ndimage import gaussian_filter

from config import MAP_DIR, CONFIG_DIR, DET_DIR, AOI_BBOX_4326
from analysis import load_scenes

def _port_center():
    """Centre of the OSM port boundary (computed, with a documented fallback)."""
    try:
        from shapely.geometry import shape
        from config import OSM_GEOJSON
        for ft in OSM_GEOJSON["features"]:
            if ft["properties"].get("role") == "port_boundary":
                c = shape(ft["geometry"]).centroid
                return [c.y, c.x]
    except Exception:
        pass
    return [35.5235, 35.7709]  # OSM polygon centroid (real value, fallback only)


PORT_CENTER = _port_center()


def load_vessel_points(scenes=None):
    """All vessel locations across all scenes -> DataFrame."""
    scenes = scenes if scenes is not None else load_scenes()
    good = scenes[(scenes["error"].isna() | (scenes["error"] == ""))]
    rows = []
    for _, r in good.iterrows():
        vj = os.path.join(DET_DIR, "..", "raw_s1", r["id"], "vessels.json")
        vj = os.path.normpath(vj)
        if not os.path.exists(vj):
            continue
        vs = json.load(open(vj, encoding="utf-8"))
        for v in vs:
            rows.append(dict(
                datetime=pd.to_datetime(r["datetime"]), scene=r["id"],
                lon=v["lon"], lat=v["lat"], zone=v["zone"],
                length_m=v["length_m"], peak_db=v["peak_db"],
                vessel_id=v["vessel_id"]))
    df = pd.DataFrame(rows)
    df["year"] = df["datetime"].dt.year
    df["month"] = df["datetime"].dt.month
    return df


def zone_name(z):
    return {0: "عبور/خارج", 1: "مرسى/اقتراب", 2: "داخل المرفأ"}.get(z, str(z))


def build_folium(vessels=None, title="مرفأ اللاذقية"):
    vessels = vessels if vessels is not None else load_vessel_points()
    m = folium.Map(location=PORT_CENTER, zoom_start=13,
                   tiles="CartoDB dark_matter", control_scale=True)

    # real boundaries
    osm = json.load(open(os.path.join(CONFIG_DIR, "latakia_osm.geojson"), encoding="utf-8"))
    style = {"port_boundary": {"color": "#FB7185", "weight": 2.5, "fillColor": "#FB7185", "fillOpacity": 0.10},
             "coastline": {"color": "#38BDF8", "weight": 1.8},
             "breakwater": {"color": "#CBD5E1", "weight": 2},
             "aoi": {"color": "#64748B", "weight": 1.2, "dashArray": "4 4", "fill": False}}
    for ft in osm["features"]:
        role = ft["properties"]["role"]
        if role in ("aoi", "port_boundary", "coastline", "breakwater"):
            folium.GeoJson(ft, name=ft["properties"]["name"],
                           style_function=lambda x, s=style.get(role, {}): s).add_to(m)

    zones = json.load(open(os.path.join(CONFIG_DIR, "zones.geojson"), encoding="utf-8"))
    zstyle = {"zone_port": {"color": "#F59E0B", "weight": 1.2, "dashArray": "2 3", "fill": False},
              "zone_anchor": {"color": "#A78BFA", "weight": 1.2, "dashArray": "2 5", "fill": False}}
    for ft in zones["features"]:
        role = ft["properties"]["role"]
        folium.GeoJson(ft, name=ft["properties"]["name"],
                       style_function=lambda x, s=zstyle.get(role, {}): s).add_to(m)

    # vessels
    colors = {2: "#FB7185", 1: "#A78BFA", 0: "#38BDF8"}
    for _, v in vessels.iterrows():
        folium.CircleMarker(
            location=[v["lat"], v["lon"]], radius=4,
            color=colors.get(v["zone"], "gray"), fill=True, fillOpacity=0.9,
            popup=folium.Popup(
                f"<b>{v['datetime']:%Y-%m-%d %H:%M}Z</b><br>"
                f"المنطقة: {zone_name(v['zone'])}<br>"
                f"الطول: {v['length_m']} م | ذروة: {v['peak_db']} ديسيبل<br>"
                f"<small>{v['scene'][:40]}</small>", max_width=320),
        ).add_to(m)

    # density heat layer
    if len(vessels) > 5:
        HeatMap(vessels[["lat", "lon"]].values.tolist(), radius=16, blur=14,
                min_opacity=0.25, name="كثافة السفن").add_to(m)

    folium.LayerControl(collapsed=False).add_to(m)
    return m


def density_grid(vessels, grid_px=60):
    """Vessel density on the UTM grid (counts per cell), smoothed."""
    import pyproj
    from rasterio.warp import transform_bounds
    b = transform_bounds("EPSG:4326", "EPSG:32636", *AOI_BBOX_4326)
    x0, y1 = b[0], b[3]
    xr, yr = b[2] - b[0], b[3] - b[1]
    nx, ny = int(xr // grid_px), int(yr // grid_px)
    t = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:32636", always_xy=True)
    H = np.zeros((ny + 1, nx + 1))
    if len(vessels):
        xs, ys = t.transform(vessels["lon"].values, vessels["lat"].values)
        for x, y in zip(xs, ys):
            i, j = int((x - x0) // grid_px), int((y1 - y) // grid_px)
            if 0 <= i <= nx and 0 <= j <= ny:
                H[j, i] += 1
    return H, dict(x0=x0, y1=y1, dx=grid_px), (nx, ny)


def sar_basemap():
    """Median SAR basemap (real data) as RGB array + georef info."""
    z = np.load(os.path.join(CONFIG_DIR, "masks.npz"))
    med = z["med"]
    grid = json.load(open(os.path.join(CONFIG_DIR, "fixed_grid.json"), encoding="utf-8"))
    if med.size == 0:
        return None, None
    db = 10 * np.log10(np.clip(med, 1e-6, None))
    db = np.where(np.isfinite(db), db, -30)
    x = np.clip((db - (-25)) / (-2 - (-25)), 0, 1) ** 0.5
    rgb = (x[..., None] * np.array([[[0.08, 0.22, 0.5]]]) * 255)
    return np.clip(rgb, 0, 255).astype(np.uint8), grid


def static_density_map(vessels=None, out=None, title="كثافة السفن المكتشفة — مرفأ اللاذقية"):
    """PNG map: real SAR basemap + smoothed density + port boundary."""
    vessels = vessels if vessels is not None else load_vessel_points()
    base, grid = sar_basemap()
    fig, ax = plt.subplots(figsize=(11, 10), dpi=110)
    fig.patch.set_facecolor("#0B1220")
    ax.set_facecolor("#0B1220")
    if base is not None:
        ext = [grid["x0"], grid["x0"] + grid["width"] * grid["pixel"],
               grid["y1"] - grid["height"] * grid["pixel"], grid["y1"]]
        dark = base.astype(float) / 255.0 * 0.42
        ax.imshow(dark, extent=ext, origin="upper")

    H, info, (nx, ny) = density_grid(vessels)
    Hs = gaussian_filter(H.astype(float), sigma=1.2)
    cmap = LinearSegmentedColormap.from_list("den", ["#0B1220", "#155E9E", "#38BDF8", "#F59E0B", "#F87171"])
    ext2 = [info["x0"], info["x0"] + (nx + 1) * info["dx"],
            info["y1"] - (ny + 1) * info["dx"], info["y1"]]
    im = ax.imshow(Hs, extent=ext2, origin="upper", cmap=cmap, vmin=0, vmax=max(2, Hs.max()),
                   interpolation="bilinear", alpha=0.92)
    cb = fig.colorbar(im, ax=ax, fraction=0.035, pad=0.02)
    cb.set_label("عدد الاكتشافات لكل خلية (60م)", color="#8CA3C7")
    cb.ax.yaxis.set_tick_params(color="#8CA3C7")
    plt.setp(plt.getp(cb.ax.axes, "yticklabels"), color="#8CA3C7")

    osm = json.load(open(os.path.join(CONFIG_DIR, "latakia_osm.geojson"), encoding="utf-8"))
    import pyproj
    from shapely.geometry import shape
    from shapely.ops import transform as st
    t = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:32636", always_xy=True)
    for ft in osm["features"]:
        role = ft["properties"]["role"]
        if role in ("port_boundary", "breakwater"):
            g = st(t.transform, shape(ft["geometry"]))
            xs, ys = g.exterior.xy if g.geom_type == "Polygon" else g.xy
            ax.plot(xs, ys, color="#FB7185" if role == "port_boundary" else "#CBD5E1",
                    lw=2.2 if role == "port_boundary" else 1.8, zorder=5)

    ax.set_title(title, fontsize=14, color="#E6EDF7")
    ax.set_xlabel("UTM Easting (m)", color="#8CA3C7"); ax.set_ylabel("UTM Northing (m)", color="#8CA3C7")
    ax.tick_params(colors="#8CA3C7")
    for sp in ax.spines.values():
        sp.set_color("#1E2A45")
    ax.set_xticks([]); ax.set_yticks([])
    ax.set_aspect("equal")
    fig.tight_layout()
    out = out or os.path.join(MAP_DIR, "density_map.png")
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    return out


if __name__ == "__main__":
    vessels = load_vessel_points()
    print("vessel points:", len(vessels))
    m = build_folium(vessels)
    m.save(os.path.join(MAP_DIR, "latakia_map.html"))
    print("folium map saved")
    static_density_map(vessels)
    print("density map saved")
