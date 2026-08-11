#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Update the Latakia port monitoring dataset with the newest satellite scenes.

Usage:
  python3 update_data.py                       # update S1 + S2
  python3 update_data.py --s1-only             # radar only
  python3 update_data.py --s2-only             # optical only
  python3 update_data.py --to 2026-12-31       # extend the time range
  python3 update_data.py --full                # + regenerate all reports/exports
  python3 update_data.py --ais <aishub-user>   # + fetch live AIS from AISHub
  python3 update_data.py --offline             # refresh outputs from existing data

The pipeline is resumable: already-processed scenes are skipped, only new
acquisitions are downloaded and analysed. `--full` is the mode used by the
weekly cron (scripts/run_weekly_update.sh): analytics, charts, the four
report formats, GIS layers (GeoJSON + GeoTIFF) and the AIS profile are all
rebuilt from the freshly updated detection files.
"""
import os, sys, json, argparse, subprocess, traceback
from datetime import date, datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

ROOT = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(ROOT, "logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG = os.path.join(LOG_DIR, "update.log")


def log(msg):
    line = f"[{datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S}Z] {msg}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def step(name, fn):
    log(f"== {name} ==")
    try:
        fn()
        log(f"== {name}: OK ==")
    except Exception:
        log(f"== {name}: FAILED ==")
        log(traceback.format_exc())
        return False
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--s1-only", action="store_true")
    ap.add_argument("--s2-only", action="store_true")
    ap.add_argument("--to", type=str, default=None,
                    help="end date YYYY-MM-DD (default: today)")
    ap.add_argument("--full", action="store_true",
                    help="regenerate analytics, charts, reports and exports")
    ap.add_argument("--ais", type=str, default=None, metavar="AISHUB_USERNAME",
                    help="fetch live AIS from AISHub into data/ais/")
    ap.add_argument("--offline", action="store_true",
                    help="skip downloads; only refresh outputs from existing data")
    args = ap.parse_args()

    log("update_data.py started (full=%s offline=%s)" % (args.full, args.offline))

    from src.config import TIME_RANGE
    import src.config as config

    end = (args.to or date.today().isoformat()) + "T23:59:59Z"
    config.TIME_RANGE = (config.TIME_RANGE[0], end)

    if not args.offline:
        from src.stac import select_s1_scenes, select_s2_scenes
        from src.pipeline import run_s1, run_s2
        if not args.s2_only:
            log("Sentinel-1 update")
            recs = select_s1_scenes(config.S1_PER_MONTH * 2, force=True)
            run_s1(recs, workers=6)
        if not args.s1_only:
            log("Sentinel-2 update")
            recs2 = select_s2_scenes(config.S2_PER_MONTH, force=True)
            run_s2(recs2, workers=5)

    if args.ais:
        from src.ais_verify import fetch_aishub
        try:
            fetch_aishub(args.ais)
        except Exception as e:
            log(f"AISHub fetch failed (continuing): {e}")

    # ---- refresh analytics & charts ----
    from src.analysis import load_scenes, full_analysis
    scenes = load_scenes()
    monthly, yearly, chg, summary = full_analysis(scenes)
    n_ok = int((scenes["error"].isna() | (scenes["error"] == "")).sum())
    log(f"analytics refreshed | valid scenes: {n_ok}/{len(scenes)} "
        f"| vessel records: {int(scenes['n_est'].sum())}")

    if not args.full:
        log("done (analytics only — use --full for reports/exports)")
        return

    from src.charts import save_all
    step("charts", lambda: save_all(monthly, yearly, scenes))

    step("HTML report", lambda: _run("src.report"))
    step("PBI report", lambda: _run("src.report_pbi"))
    step("DOCX report", lambda: _run("src.report_docx"))
    step("Excel workbook", lambda: _run("src.report_excel"))
    step("exec brief", lambda: _run("src.onepager"))

    from src.exporter import export_geojson, export_summary_json
    step("GeoJSON export", lambda: export_geojson(scenes))
    step("summary JSON", lambda: export_summary_json(scenes))

    from src.tracking import run as tracks_run
    step("ship tracking", lambda: tracks_run())
    from src.anomaly import run as anomaly_run
    step("anomaly detection", lambda: anomaly_run())
    from src.insights import run as insights_run
    step("operational insights", lambda: insights_run())

    from src.geotiff import run as gtiff_run
    step("GeoTIFF layers", lambda: gtiff_run(scenes, latest_scene=True))

    from src.ais_verify import run as ais_run
    step("AIS verification", lambda: ais_run(scenes))

    # ---- regional ports (Tartus + Baniyas): same scenes, same pipeline ----
    def _regional():
        if getattr(args, "offline", False):
            log("regional ports: skipped (offline mode)")
            return
        # Tartus: catch up any new scenes, rebuild its series
        try:
            from src.process_tartus import process_all as tartus_process, build_series as tartus_series
            tartus_process()
            tartus_series()
        except Exception:
            pass
        try:
            from src.process_baniyas import process as ban_process, build_series as ban_series
            ban_process(since=(date.today().replace(year=date.today().year - 1).isoformat()),
                        to=date.today().isoformat(), per_month=3)
            ban_series()
        except Exception:
            pass
    step("regional ports (Tartus/Baniyas)", _regional)

    step("PDFs (chromium headless)", lambda: _make_pdfs())
    log("update_data.py --full finished")


def _run(module):
    """Run a report module as a script (script dir is auto-added to sys.path,
    which is what the report modules expect — `-m` would pick up the data
    `config/` directory instead of src/config.py)."""
    script = module.replace(".", "/") + ".py"
    subprocess.run([sys.executable, script], cwd=ROOT, check=True)


def _make_pdfs():
    """HTML -> PDF with headless Chromium (skips silently when unavailable)."""
    pdfs = [("docs/FINAL_REPORT.html", "docs/FINAL_REPORT.pdf"),
            ("docs/PBI_REPORT.html", "docs/PBI_REPORT.pdf"),
            ("docs/EXEC_BRIEF.html", "docs/EXEC_BRIEF.pdf")]
    candidates = ["/usr/bin/chromium", "/usr/bin/chromium-browser", "chromium"]
    exe = next((c for c in candidates if os.path.exists(c) or c == "chromium"), None)
    for src, dst in pdfs:
        if not os.path.exists(src):
            continue
        cmd = [exe, "--headless", "--disable-gpu", "--no-sandbox",
               "--print-to-pdf=%s" % os.path.join(ROOT, dst),
               "file://%s" % os.path.join(ROOT, src)]
        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=180)
            log(f"PDF: {dst}")
        except Exception as e:
            log(f"PDF {dst} failed (skip): {e}")


if __name__ == "__main__":
    main()
