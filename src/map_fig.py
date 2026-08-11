# -*- coding: utf-8 -*-
"""
Self-contained interactive map (Plotly) for the Latakia port dashboard.

No external dependencies: the real Sentinel-1 median basemap is embedded as a
base64 image, boundaries come from the real OSM GeoJSON, and vessel points are
plotted from the corrected detection data. Works offline.
"""
import os, json, base64, io
import numpy as np
import pandas as pd
import plotly.graph_objects as go

from config import CONFIG_DIR, AOI_BBOX_4326, DET_DIR
from charts import C, FONT

ZONE_COLORS = {2: "#FB7185", 1: "#A78BFA", 0: "#38BDF8"}
ZONE_NAMES = {2: "داخل المرفأ", 1: "المرسى / الاقتراب", 0: "عبور / خارج"}


def _sar_basemap():
    """Median SAR VV as base64 PNG + lon/lat extent."""
    z = np.load(os.path.join(CONFIG_DIR, "masks.npz"))
    med = z["med"]
    if med.size == 0:
        return None, None
    grid = json.load(open(os.path.join(CONFIG_DIR, "fixed_grid.json"), encoding="utf-8"))
    db = 10 * np.log10(np.clip(med, 1e-6, None))
    db = np.where(np.isfinite(db), db, -30)
    x = np.clip((db - (-25)) / (-2 - (-25)), 0, 1) ** 0.5
    rgb = (x[..., None] * np.array([[[0.08, 0.22, 0.5]]]) * 255)
    rgb = np.clip(rgb, 0, 255).astype(np.uint8)
    from PIL import Image
    buf = io.BytesIO()
    Image.fromarray(rgb).save(buf, "PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()
    # UTM extent -> WGS84
    from pyproj import Transformer
    t = Transformer.from_crs(f"EPSG:{grid['epsg']}", "EPSG:4326", always_xy=True)
    x0, y1 = grid["x0"], grid["y1"]
    x1 = x0 + grid["width"] * grid["pixel"]
    y0 = y1 - grid["height"] * grid["pixel"]
    lon0, lat1 = t.transform(x0, y1)
    lon1, lat0 = t.transform(x1, y0)
    return f"data:image/png;base64,{b64}", (lon0, lon1, lat0, lat1)


def _osm_layers():
    """Port boundary, coastline, breakwater as (lon, lat) line lists."""
    osm = json.load(open(os.path.join(CONFIG_DIR, "latakia_osm.geojson"), encoding="utf-8"))
    out = {}
    for ft in osm["features"]:
        role = ft["properties"]["role"]
        if role not in ("port_boundary", "coastline", "breakwater", "aoi"):
            continue
        g = ft["geometry"]
        if g["type"] == "Polygon":
            ring = g["coordinates"][0]
            out.setdefault(role, []).append(([p[0] for p in ring], [p[1] for p in ring]))
        elif g["type"] == "LineString":
            out.setdefault(role, []).append(([p[0] for p in g["coordinates"]],
                                             [p[1] for p in g["coordinates"]]))
    return out


def build_activity_map(vessels, height=640):
    """Interactive plotly map: SAR basemap + real boundaries + vessel points."""
    fig = go.Figure()
    b64, ext = _sar_basemap()
    if b64:
        lon0, lon1, lat0, lat1 = ext
        fig.add_layout_image(dict(
            source=b64, x=lon0, y=lat1, sizex=lon1 - lon0, sizey=lat1 - lat0,
            xref="x", yref="y", layer="below", sizing="stretch", opacity=1.0))

    layers = _osm_layers()
    style = {"port_boundary": dict(color="#FB7185", width=2.5, dash="solid", name="حدود المرفأ (OSM)"),
             "coastline": dict(color="#7DD3FC", width=1.6, dash="solid", name="خط الساحل"),
             "breakwater": dict(color="#E2E8F0", width=2.0, dash="solid", name="كاسر الأمواج"),
             "aoi": dict(color="#64748B", width=1.2, dash="dot", name="منطقة الدراسة")}
    for role, lines in layers.items():
        for lon, lat in lines:
            fig.add_trace(go.Scattergeo if False else go.Scatter(
                x=lon, y=lat, mode="lines",
                line=dict(color=style[role]["color"], width=style[role]["width"],
                          dash=style[role]["dash"]),
                name=style[role]["name"], hoverinfo="skip",
                showlegend=(role != "coastline")))

    if len(vessels):
        for z in (2, 1, 0):
            sub = vessels[vessels["zone"] == z]
            if not len(sub):
                continue
            fig.add_trace(go.Scattergl(
                x=sub["lon"], y=sub["lat"], mode="markers",
                name=f"{ZONE_NAMES[z]} ({len(sub)})",
                marker=dict(size=4.5, color=ZONE_COLORS[z], opacity=0.85,
                            line=dict(width=0.3, color="rgba(255,255,255,0.5)")),
                customdata=np.stack([sub["datetime"].dt.strftime("%Y-%m-%d %H:%M"),
                                     sub["vessel_id"], sub["length_m"].fillna(0).astype(int),
                                     sub["peak_db"]], axis=-1),
                hovertemplate=("<b>%{customdata[0]}Z</b><br>"
                               + ZONE_NAMES[z]
                               + "<br>الطول: %{customdata[2]} م · ذروة: %{customdata[3]} ديسيبل"
                               + "<br><span style='font-size:10px'>%{customdata[1]}</span><extra></extra>")))

    fig.update_layout(
        title=dict(text="خريطة النشاط — مواقع السفن المكتشفة (إحداثيات حقيقية)",
                   x=0.5, xanchor="center",
                   font=dict(size=15, family=FONT, color=C["ink"])),
        paper_bgcolor=C["bg"], plot_bgcolor=C["bg"],
        font=dict(family=FONT, color=C["ink"]),
        xaxis=dict(range=[AOI_BBOX_4326[0], AOI_BBOX_4326[2]], showgrid=False,
                   zeroline=False, visible=False),
        yaxis=dict(range=[AOI_BBOX_4326[1], AOI_BBOX_4326[3]], showgrid=False,
                   zeroline=False, visible=False, scaleanchor="x", scaleratio=1.0),
        legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="center", x=0.5,
                    font=dict(size=11.5, color=C["ink_dim"]),
                    bgcolor="rgba(0,0,0,0)"),
        margin=dict(l=10, r=10, t=56, b=10),
        height=height,
        hoverlabel=dict(bgcolor=C["panel"], bordercolor="rgba(140,163,199,0.35)",
                        font=dict(family=FONT, color=C["ink"], size=12)),
    )
    return fig


if __name__ == "__main__":
    from maps import load_vessel_points
    vessels = load_vessel_points()
    fig = build_activity_map(vessels)
    fig.write_html("/tmp/test_map.html", include_plotlyjs="cdn")
    print("test map written")
