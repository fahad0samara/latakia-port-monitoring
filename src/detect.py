# -*- coding: utf-8 -*-
"""
Vessel detection on real Sentinel-1 RTC (gamma0) imagery over the Port of
Latakia study area.

Pipeline (per scene):
  1. load signed COG from Planetary Computer, read VV+VH subset
  2. reproject onto the fixed 10 m UTM-36N AOI grid (perfect co-registration)
  3. land masking (Natural Earth + OSM port + OSM breakwater)
  4. Lee speckle filter (5x5)
  5. adaptive sea-clutter thresholding on VV + VH cross-check
  6. connected components -> vessel candidates -> geometry & radiometry stats
  7. visual products: dB image, detection overlay, per-vessel VV/VH crops
"""
import os, json, math
import numpy as np
import rasterio
from rasterio.windows import from_bounds
from rasterio.warp import reproject, Resampling, transform_bounds
from rasterio.transform import from_origin
from scipy.ndimage import (uniform_filter, label as ndlabel, find_objects, binary_opening,
                           binary_closing, maximum_filter, watershed_ift, distance_transform_edt)
import cv2
from PIL import Image
from shapely.geometry import Point
import pyproj

from config import RTC_EPSG, PIXEL, DETECT, S1_DIR, AOI_BBOX_4326
from boundaries import load_geoms

WGS = pyproj.CRS("EPSG:4326")
UTM = pyproj.CRS(f"EPSG:{RTC_EPSG}")
to_lonlat = pyproj.Transformer.from_crs(UTM, WGS, always_xy=True)


def lee_filter(img, size=5):
    """Lee speckle filter; preserves point targets while smoothing speckle."""
    mu = uniform_filter(img, size=size)
    mu2 = uniform_filter(img * img, size=size)
    var_img = np.clip(mu2 - mu * mu, 0, None)
    with np.errstate(divide="ignore", invalid="ignore"):
        enl = (mu * mu) / np.where(var_img > 1e-12, var_img, np.nan)
        w = np.nan_to_num(var_img / (var_img + mu * mu / np.nan_to_num(enl, nan=1.0)), nan=0.0)
    return mu + w * (img - mu)


def robust_stats(x):
    med = np.median(x)
    sig = 1.4826 * np.median(np.abs(x - med))
    return med, sig


def _split_component(sl, comp, intensity, t_vv, min_area=4):
    """Split a bright component at intensity valleys (marker-controlled watershed).
    Returns a list of sub-masks (one per ship when several are berthed together)."""
    from skimage.feature import peak_local_max
    from skimage.segmentation import watershed as sk_watershed

    y0, y1, x0, x1 = sl[0].start, sl[0].stop, sl[1].start, sl[1].stop
    win_int = intensity[y0:y1, x0:x1]
    data = np.where(comp, win_int, 0.0)
    peaks = peak_local_max(data, min_distance=4, exclude_border=False, labels=comp.astype(np.uint8))
    nm = len(peaks)
    if nm <= 1:
        return [comp]
    markers = np.zeros_like(comp, dtype=np.int32)
    for idx, (py, px) in enumerate(peaks, 1):
        markers[py, px] = idx
    basin = sk_watershed(-data, markers, mask=comp)
    segs = []
    for i in range(1, nm + 1):
        seg = (basin == i) & comp
        if seg.sum() >= min_area and win_int[seg].max() > t_vv:
            segs.append(seg)
    return segs or [comp]


class S1SceneProcessor:
    def __init__(self, grid, land, zone, bbox_4326=None, geoms=None):
        self.grid = grid
        self.T = from_origin(grid["x0"], grid["y1"], PIXEL, PIXEL)
        self.land = land
        self.zone = zone
        self.bbox_4326 = bbox_4326 if bbox_4326 is not None else AOI_BBOX_4326
        self.geoms = geoms if geoms is not None else load_geoms()

    def read_fixed_grid(self, src):
        H, W = self.grid["height"], self.grid["width"]
        gx0, gy1 = self.grid["x0"], self.grid["y1"]
        # geographic AOI corners expressed in the *scene's* CRS (RTC frames can
        # be delivered in different UTM zones: 36N for descending, 37N for ascending)
        b = transform_bounds("EPSG:4326", src.crs, *self.bbox_4326)
        win = from_bounds(b[0] - 150, b[1] - 150, b[2] + 150, b[3] + 150,
                          src.transform).round_offsets()
        win = win.intersection(rasterio.windows.Window(0, 0, src.width, src.height))
        if win.width < 10 or win.height < 10:
            return None
        arr = src.read(1, window=win)
        # normalize: PC RTC is float32 linear gamma0; nodata = -32768
        arr = arr.astype(np.float32)
        arr[(arr <= 0) | ~np.isfinite(arr)] = np.nan
        out = np.full((H, W), np.nan, dtype=np.float32)
        src_tr = rasterio.windows.transform(win, src.transform)
        reproject(arr, out, src_transform=src_tr, src_crs=src.crs,
                  dst_transform=self.T, dst_crs=UTM,
                  resampling=Resampling.nearest, src_nodata=src.nodata, dst_nodata=np.nan)
        return out

    def detect(self, vv, vh, rec):
        D = DETECT
        sea = ~self.land
        valid = np.isfinite(vv) & np.isfinite(vh)
        sea = sea & valid
        vv_lin = np.where(valid, vv, 0.0)
        vh_lin = np.where(valid, vh, 0.0)

        vv_f = lee_filter(vv_lin, D["lee_filter_size"])
        vh_f = lee_filter(vh_lin, D["lee_filter_size"])

        open_sea = sea & (self.zone == 0)
        sample = vv_f[open_sea]
        sample_vh = vh_f[open_sea]
        if sample.size < 5000:
            return None, "insufficient open-sea pixels"
        mu_vv, sig_vv = robust_stats(sample)
        mu_vh, sig_vh = robust_stats(sample_vh)
        noise_floor_db = 10 * np.log10(max(mu_vv, 1e-8))
        sea_roughness = sig_vv / max(mu_vv, 1e-9)

        t_vv = mu_vv + D["vv_k"] * sig_vv
        t_vh = mu_vh + D["vh_k"] * sig_vh
        t_abs = 10 ** (D["min_peak_db"] / 10)

        mask_vv = (vv_f > t_vv) & sea
        mask_vh = (vh_f > t_vh) & sea
        strong = vv_f > max(t_abs, t_vv)
        cand = mask_vv & (mask_vh | strong)
        cand = binary_opening(cand, iterations=1)
        cand = binary_closing(cand, iterations=1)

        lab, n = ndlabel(cand)
        slices = find_objects(lab)
        vessels = []
        n_components_kept = 0
        for i in range(1, n + 1):
            sl = slices[i - 1]
            comp = lab[sl] == i
            area = int(comp.sum())
            if area < D["min_area_px"] or area > D["max_area_px"]:
                continue
            peak = float(vv_f[sl][comp].max())
            peak_db = 10 * np.log10(max(peak, 1e-8))
            if peak_db < D["min_peak_db"]:
                continue
            vh_bright = float((vh_f[sl][comp] > t_vh).mean())
            if vh_bright < 0.20 and peak_db < D["min_peak_db"] + 6:
                continue
            # split berthed clusters into individual ships (marker watershed)
            segments = _split_component(sl, comp, vv_f, t_vv, D["min_area_px"])
            n_components_kept += 1
            demerged = len(segments) > 1
            for j, seg in enumerate(segments, 1):
                v = self._vessel_from_segment(sl, seg, vv_f, vh_f, t_vh, rec, i, j, demerged)
                if v is not None:
                    vessels.append(v)
        for v in vessels:
            v["zone"] = self._zone_of(v)
        # keep only vessels inside the real study area (AOI)
        bb = self.bbox_4326
        vessels = [v for v in vessels if
                   bb[0] <= v["lon"] <= bb[2] and
                   bb[1] <= v["lat"] <= bb[3]]
        return dict(
            n_total=n_components_kept,
            n_est=len(vessels),
            n_in_port=sum(1 for v in vessels if v["zone"] == 2),
            n_anchorage=sum(1 for v in vessels if v["zone"] == 1),
            n_transit=sum(1 for v in vessels if v["zone"] == 0),
            n_est_in_port=sum(1 for v in vessels if v["zone"] == 2),
            noise_floor_db=round(noise_floor_db, 2),
            sea_roughness=round(sea_roughness, 3),
            clutter_mu=float(mu_vv), clutter_sigma=float(sig_vv),
            vessels=vessels, vv_f=vv_f, vh_f=vh_f,
        ), None

    def _vessel_from_segment(self, sl, seg, vv_f, vh_f, t_vh, rec, comp_idx, seg_idx, demerged):
        """Build the vessel record for one (sub-)segment."""
        D = DETECT
        area = int(seg.sum())
        if area < D["min_area_px"] or area > D["max_area_px"]:
            return None
        peak = float(vv_f[sl][seg].max())
        peak_db = 10 * np.log10(max(peak, 1e-8))
        if peak_db < D["min_peak_db"]:
            return None
        ys, xs = np.nonzero(seg)
        xs_g, ys_g = xs + sl[1].start, ys + sl[0].start
        ux = self.grid["x0"] + (xs_g + 0.5) * PIXEL
        uy = self.grid["y1"] - (ys_g + 0.5) * PIXEL
        wgt = vv_f[sl][seg]
        cx = float(np.sum(ux * wgt) / wgt.sum())
        cy = float(np.sum(uy * wgt) / wgt.sum())
        lon, lat = to_lonlat.transform(cx, cy)
        mask8 = seg.astype(np.uint8) * 255
        cnt, _ = cv2.findContours(mask8, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        length_m = width_m = angle = None
        if cnt:
            rect = cv2.minAreaRect(cnt[0])
            w_, h_ = rect[1]
            length_m = max(w_, h_) * PIXEL
            width_m = min(w_, h_) * PIXEL
            angle = rect[2]
        pt = Point(lon, lat)
        d_port = pt.distance(self.geoms["port_boundary"]) * 111320 * math.cos(math.radians(lat))
        return dict(
            vessel_id=f"{rec['id'][:36]}_{comp_idx:03d}_{seg_idx:02d}",
            lon=round(lon, 6), lat=round(lat, 6),
            utm_x=round(cx, 1), utm_y=round(cy, 1),
            area_px=area,
            length_m=round(length_m, 0) if length_m else None,
            width_m=round(width_m, 0) if width_m else None,
            peak_db=round(peak_db, 2),
            mean_db=round(10 * np.log10(max(float(vv_f[sl][seg].mean()), 1e-8)), 2),
            vh_bright_frac=round(float((vh_f[sl][seg] > t_vh).mean()), 2),
            dist_port_m=round(d_port, 0),
            demerged=bool(demerged),
            sl=[sl[0].start, sl[0].stop, sl[1].start, sl[1].stop],
        )

    def _zone_of(self, v):
        pt = Point(v["lon"], v["lat"])
        d = pt.distance(self.geoms["port_boundary"]) * 111320 * math.cos(math.radians(v["lat"]))
        if d <= 400:
            return 2
        if d <= 4000:
            return 1
        return 0

    # -------------------------------------------------------------- visuals
    @staticmethod
    def _stretch(db, vmin, vmax):
        db = np.where(np.isfinite(db), db, vmin)
        x = np.clip((db - vmin) / (vmax - vmin), 0, 1)
        x = np.sqrt(x)
        rgb = (x[..., None] * np.array([[[0.10, 0.28, 0.62]]]) * 255)
        return np.clip(rgb, 0, 255).astype(np.uint8)

    @staticmethod
    def _save(img, path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        Image.fromarray(img).save(path, "JPEG", quality=82, optimize=True)

    def save_products(self, rec, res, outdir):
        vv_db = 10 * np.log10(np.clip(res["vv_f"], 1e-6, None))
        vh_db = 10 * np.log10(np.clip(res["vh_f"], 1e-6, None))
        vv_db[self.land] = np.nan
        vh_db[self.land] = np.nan

        img1 = self._stretch(vv_db, -27, -2)
        img1[self.land] = [28, 28, 28]
        self._save(img1, os.path.join(outdir, "vv_original.jpg"))

        img2 = img1.copy()
        for v in res["vessels"]:
            x0, y0 = v["sl"][2], v["sl"][0]
            x1, y1 = v["sl"][3], v["sl"][1]
            c = (255, 45, 45)
            cv2.rectangle(img2, (x0, y0), (x1, y1), c, 2)
            cv2.putText(img2, v["vessel_id"].split("_")[-1], (x0, max(0, y0 - 4)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, c, 1, cv2.LINE_AA)
        self._save(img2, os.path.join(outdir, "detection_overlay.jpg"))

        vdir = os.path.join(outdir, "vessels")
        for v in res["vessels"]:
            cy, cx = (v["sl"][0] + v["sl"][1]) / 2, (v["sl"][2] + v["sl"][3]) / 2
            half = 75
            y0 = max(0, int(cy) - half); y1 = min(vv_db.shape[0], int(cy) + half)
            x0 = max(0, int(cx) - half); x1 = min(vv_db.shape[1], int(cx) + half)
            a = self._stretch(vv_db[y0:y1, x0:x1], -27, -2)
            b = self._stretch(vh_db[y0:y1, x0:x1], -30, -8)
            sep = np.full((a.shape[0], 6, 3), 255, np.uint8)
            panel = np.concatenate([a, sep, b], axis=1)
            cv2.rectangle(panel, (0, 0), (panel.shape[1] - 1, panel.shape[0] - 1), (255, 45, 45), 1)
            self._save(panel, os.path.join(vdir, f"{v['vessel_id']}.jpg"))

    @staticmethod
    def _load_vessels(rec):
        js = os.path.join(S1_DIR, rec["id"], "vessels.json")
        return json.load(open(js, encoding="utf-8")) if os.path.exists(js) else []


def process_scene(rec, grid, land, zone, write_products=True, bbox_4326=None, geoms=None,
                   out_dir=None):
    """Full pipeline for one Sentinel-1 RTC scene."""
    import planetary_computer as pc
    from stac import load_item
    item = load_item(rec)
    if item is None:
        return dict(**rec, error="item not found")
    item = pc.sign_item(item)
    proc = S1SceneProcessor(grid, land, zone, bbox_4326=bbox_4326, geoms=geoms)
    try:
        with rasterio.open(item.assets["vv"].href) as src_vv:
            vv = proc.read_fixed_grid(src_vv)
        with rasterio.open(item.assets["vh"].href) as src_vh:
            vh = proc.read_fixed_grid(src_vh)
    except Exception as e:
        return dict(**rec, error=f"read: {e}")
    if vv is None or vh is None:
        return dict(**rec, error="no overlap")
    frac_valid = float(np.isfinite(vv[~land]).mean())
    if frac_valid < 0.70:
        return dict(**rec, error=f"coverage {frac_valid:.2f}")
    # zone-specific sea coverage (which zones are fully seen by the radar?)
    def _zone_cov(zcode):
        m = (zone == zcode)
        if m.sum() == 0:
            return None
        return float(np.isfinite(vv[m]).mean())
    cov_port = _zone_cov(2)
    cov_anchor = _zone_cov(1)

    res, err = proc.detect(vv, vh, rec)
    if err:
        return dict(**rec, error=err)

    # products go to S1_DIR/<scene> by default (Latakia archive); other ports
    # pass their OWN base directory, and the scene folder is appended so each
    # port keeps a per-scene archive and never touches the Latakia detections.
    base = out_dir if out_dir is not None else S1_DIR
    outdir = os.path.join(base, rec["id"])
    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, "vessels.json"), "w", encoding="utf-8") as f:
        json.dump(res["vessels"], f, ensure_ascii=False, indent=1)

    out = dict(
        id=rec["id"], datetime=rec["datetime"], year=rec["year"], month=rec["month"],
        satellite="Sentinel-1 RTC", platform=rec["sat"], orbit=rec.get("orbit"),
        n_total=int(res["n_total"]), n_est=int(res["n_est"]),
        n_in_port=int(res["n_in_port"]), n_est_in_port=int(res["n_est_in_port"]),
        n_anchorage=int(res["n_anchorage"]), n_transit=int(res["n_transit"]),
        noise_floor_db=float(res["noise_floor_db"]), sea_roughness=float(res["sea_roughness"]),
        coverage=float(round(frac_valid, 3)),
        cov_port=round(cov_port, 3) if cov_port is not None else None,
        cov_anchor=round(cov_anchor, 3) if cov_anchor is not None else None,
        error=None,
    )
    if write_products:
        proc.save_products(rec, res, outdir)
    return out
