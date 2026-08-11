# -*- coding: utf-8 -*-
"""
Time-series analysis of the Latakia port vessel detections.

Core principle: every period metric is normalized by the number of satellite
observations available in that period. Months/years without observations are
reported as "No data available" — never filled with synthetic numbers.

Key outputs:
  * monthly.csv / yearly.csv  — normalized activity series
  * summary.json              — trend tests & regime comparisons
"""
import os, json, math
import numpy as np
import pandas as pd
from scipy import stats as sps

from config import DET_DIR

S1_JSONL = os.path.join(DET_DIR, "s1_scenes.jsonl")


def _reconcile_scene_counts():
    """Ensure s1_scenes.jsonl n_est* match the actual vessels.json files.
    Called at load time so stale counts can never leak into analytics."""
    import os as _os
    from config import S1_DIR as _S1
    changed = 0
    rows = []
    with open(S1_JSONL, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            r = json.loads(line)
            if not r.get("error"):
                vj = _os.path.join(_S1, r["id"], "vessels.json")
                if _os.path.exists(vj):
                    vessels = json.load(open(vj, encoding="utf-8"))
                    n = len(vessels)
                    if n != int(r.get("n_est", 0)):
                        r["n_est"] = n
                        r["n_est_in_port"] = sum(1 for v in vessels if v.get("zone") == 2)
                        r["n_anchorage"] = sum(1 for v in vessels if v.get("zone") == 1)
                        r["n_transit"] = sum(1 for v in vessels if v.get("zone") == 0)
                        r["n_total"] = len({v["vessel_id"].rsplit("_", 2)[-2] for v in vessels})
                        changed += 1
            rows.append(r)
    if changed:
        with open(S1_JSONL, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"[analysis] auto-reconciled {changed} scenes")
    return rows


def load_scenes():
    rows = _reconcile_scene_counts()
    df = pd.DataFrame(rows)
    df["datetime"] = pd.to_datetime(df["datetime"])
    df["date"] = df["datetime"].dt.date
    # normalize platform names (mixed case in source) and mark failed scenes
    if "platform" in df.columns:
        df["platform"] = df["platform"].str.upper().str.strip()
        df.loc[df["error"].notna(), "platform"] = None
    if "orbit" in df.columns:
        df["orbit"] = df["orbit"].str.strip()
    return df


def mann_kendall(x):
    """Mann-Kendall trend test (two-sided). Returns tau, p, direction."""
    n = len(x)
    if n < 4:
        return None, None, None
    s = 0
    for i in range(n - 1):
        for j in range(i + 1, n):
            s += np.sign(x[j] - x[i])
    # variance (no ties correction needed for continuous-ish data)
    var = n * (n - 1) * (2 * n + 5) / 18
    if var == 0:
        return None, None, None
    z = (s - np.sign(s)) / math.sqrt(var) if s != 0 else 0.0
    p = 2 * (1 - sps.norm.cdf(abs(z)))
    tau = 2 * s / (n * (n - 1))
    return tau, p, "increase" if tau > 0 else "decrease"


def sen_slope(x, y):
    n = len(x)
    slopes = []
    for i in range(n - 1):
        for j in range(i + 1, n):
            if x[j] != x[i]:
                slopes.append((y[j] - y[i]) / (x[j] - x[i]))
    if not slopes:
        return None
    return float(np.median(slopes))


def build_monthly(scenes=None):
    df = scenes if scenes is not None else load_scenes()
    good = df[df["error"].isna() | (df["error"] == "")]
    # month series: mean ships per observation, normalized by coverage
    m = good.copy()
    m["ym"] = m["datetime"].dt.strftime("%Y-%m")
    # zone-specific coverage: a scene only counts for the port metric if the
    # port basin itself was fully seen (cov_port >= 0.7)
    m["ships_port_adj"] = np.where(
        m["cov_port"].fillna(0) >= 0.7,
        m["n_est_in_port"] / m["cov_port"].clip(0.7, 1.0), np.nan)
    m["anchor_adj"] = np.where(
        m["cov_anchor"].fillna(0) >= 0.7,
        m["n_anchorage"] / m["cov_anchor"].clip(0.7, 1.0), np.nan)
    m["port_obs_ok"] = m["cov_port"].fillna(0) >= 0.7

    rows = []
    for ym, g in m.groupby("ym"):
        n_obs = len(g)
        gp = g[g["port_obs_ok"]]  # scenes that fully saw the port basin
        rows.append(dict(
            ym=ym,
            year=int(ym[:4]), month=int(ym[5:7]),
            n_obs=n_obs,
            n_obs_good=len(g),
            n_obs_port=len(gp),
            mean_ships_port=round(float(g["n_est_in_port"].mean()), 2) if n_obs else None,
            mean_ships_port_adj=round(float(gp["ships_port_adj"].mean()), 2) if len(gp) else None,
            mean_ships_total=round(float(g["n_est"].mean()), 2),
            mean_components=round(float(g["n_total"].mean()), 2),
            median_ships_port=float(g["n_est_in_port"].median()),
            max_ships_port=int(g["n_est_in_port"].max()),
            min_ships_port=int(g["n_est_in_port"].min()),
            mean_anchorage=round(float(g["n_anchorage"].mean()), 2),
            mean_coverage=round(float(g["coverage"].mean()), 3),
            mean_roughness=round(float(g["sea_roughness"].mean()), 3),
            mean_noise_floor=round(float(g["noise_floor_db"].mean()), 2),
            scenes_ids=list(g["id"]),
        ))
    out = pd.DataFrame(rows).sort_values("ym").reset_index(drop=True)
    out["data_status"] = np.where(out["n_obs"] == 0, "No data available",
                          np.where(out["n_obs"] < 3, "limited", "ok"))
    out.to_csv(os.path.join(DET_DIR, "monthly.csv"), index=False)
    return out


def build_yearly(monthly):
    rows = []
    for y, g in monthly.groupby("year"):
        g = g[g["n_obs"] > 0]
        if len(g) == 0:
            rows.append(dict(year=y, data_status="No data available"))
            continue
        rows.append(dict(
            year=y,
            n_months=len(g),
            n_obs=int(g["n_obs"].sum()),
            annual_mean_ships_port=round(float(g["mean_ships_port"].mean()), 2),
            annual_mean_adj=round(float(g["mean_ships_port_adj"].mean()), 2),
            peak_month=int(g.loc[g["mean_ships_port"].idxmax(), "month"]),
            peak_value=float(g["mean_ships_port"].max()),
            low_month=int(g.loc[g["mean_ships_port"].idxmin(), "month"]),
            low_value=float(g["mean_ships_port"].min()),
            max_scene_ships=int(g["max_ships_port"].max()),
            data_status="ok",
        ))
    out = pd.DataFrame(rows)
    # YoY change on a like-for-like basis (same calendar months both years),
    # so a partial year is never compared against a full one.
    out["yoy_pct"] = np.nan
    out["yoy_basis"] = ""
    for i in range(1, len(out)):
        cur = out.iloc[i]
        prev = out.iloc[i - 1]
        if prev["data_status"] != "ok" or cur["data_status"] != "ok":
            continue
        cur_months = sorted(monthly[monthly["year"] == cur["year"]]["month"].tolist())
        if len(cur_months) == 12:
            a, b = cur["annual_mean_ships_port"], prev["annual_mean_ships_port"]
            basis = "12 شهرًا"
        else:
            # same months in the previous year
            pm = monthly[(monthly["year"] == prev["year"]) & (monthly["month"].isin(cur_months))]
            cm = monthly[(monthly["year"] == cur["year"]) & (monthly["month"].isin(cur_months))]
            a = float(cm["mean_ships_port_adj"].mean())
            b = float(pm["mean_ships_port_adj"].mean())
            basis = f"نفس الأشهر ({cur_months[0]}-{cur_months[-1]})"
        if b > 0:
            out.loc[out.index[i], "yoy_pct"] = round((a - b) / b * 100, 1)
            out.loc[out.index[i], "yoy_basis"] = basis
    out.to_csv(os.path.join(DET_DIR, "yearly.csv"), index=False)
    return out


def regime_test(monthly, before, after, col="mean_ships_port_adj"):
    """Compare two periods (months with data). Returns dict with stats."""
    b = monthly[(monthly["ym"] >= before[0]) & (monthly["ym"] <= before[1])]
    a = monthly[(monthly["ym"] >= after[0]) & (monthly["ym"] <= after[1])]
    b = b[b["n_obs"] > 0][col].values
    a = a[a["n_obs"] > 0][col].values
    if len(b) < 3 or len(a) < 3:
        return dict(valid=False, reason="insufficient months with data")
    t, p = sps.mannwhitneyu(b, a, alternative="two-sided")
    # bootstrap 95% CI of the difference
    rng = np.random.default_rng(42)
    diffs = []
    for _ in range(2000):
        bb = rng.choice(b, len(b), replace=True)
        aa = rng.choice(a, len(a), replace=True)
        diffs.append(aa.mean() - bb.mean())
    ci = np.percentile(diffs, [2.5, 97.5])
    return dict(
        valid=True,
        n_before=int(len(b)), n_after=int(len(a)),
        mean_before=round(float(b.mean()), 2), mean_after=round(float(a.mean()), 2),
        diff=round(float(a.mean() - b.mean()), 2),
        diff_pct=round(float((a.mean() - b.mean()) / max(b.mean(), 1e-9) * 100), 1),
        p_value=round(float(p), 4),
        ci95=[round(float(ci[0]), 2), round(float(ci[1]), 2)],
        direction="increase" if a.mean() > b.mean() else "decrease",
    )


def monthly_changes(monthly):
    """Month-over-month % change on the normalized index."""
    m = monthly[monthly["n_obs"] > 0].copy()
    m["mom_pct"] = m["mean_ships_port_adj"].pct_change() * 100
    return m[["ym", "mean_ships_port_adj", "mom_pct"]].round(2)


def full_analysis(scenes=None):
    monthly = build_monthly(scenes)
    yearly = build_yearly(monthly)
    chg = monthly_changes(monthly)

    # trend on the monthly normalized index (months with >=1 obs)
    idx = monthly[monthly["n_obs"] > 0]
    tau, p, direction = None, None, None
    if len(idx) >= 4:
        tau, p, direction = mann_kendall(idx["mean_ships_port_adj"].values)
        slope = sen_slope(np.arange(len(idx)), idx["mean_ships_port_adj"].values)
    else:
        slope = None

    summary = dict(
        monthly_rows=int(len(monthly)),
        months_with_data=int(len(idx)),
        months_no_data=[str(x) for x in monthly[monthly["n_obs"] == 0]["ym"]],
        mk_tau=round(tau, 3) if tau is not None else None,
        mk_p=round(p, 4) if p is not None else None,
        mk_direction=direction,
        sen_slope_units_per_month=round(slope, 3) if slope is not None else None,
        regimes=dict(
            pre_2023={"label": "2022 (baseline)", "range": ["2022-01", "2022-12"]},
            y2023={"label": "2023", "range": ["2023-01", "2023-12"]},
            y2024={"label": "2024", "range": ["2024-01", "2024-12"]},
            y2025={"label": "2025", "range": ["2025-01", "2025-12"]},
            y2026={"label": "2026 (to Aug)", "range": ["2026-01", "2026-08"]},
            pre_dec2024={"label": "before Dec-2024", "range": ["2022-01", "2024-11"]},
            post_dec2024={"label": "after Dec-2024", "range": ["2024-12", "2026-08"]},
        ),
    )
    for key, spec in summary["regimes"].items():
        summary["regimes"][key]["test"] = regime_test(monthly, spec["range"], spec["range"], "mean_ships_port_adj")

    # pairwise regime comparisons
    pairs = [
        ("y2023_vs_2022", "y2022 (baseline)", "2023", ["2022-01","2022-12"], ["2023-01","2023-12"]),
        ("y2024_vs_2023", "2024", "2023", ["2023-01","2023-12"], ["2024-01","2024-12"]),
        ("y2025_vs_2024", "2025", "2024", ["2024-01","2024-12"], ["2025-01","2025-12"]),
        ("y2026_vs_2025", "2026 (Jan-Aug)", "2025 (Jan-Aug)", ["2025-01","2025-08"], ["2026-01","2026-08"]),
        ("post_vs_pre_dec2024", "after Dec-2024", "before Dec-2024", ["2022-01","2024-11"], ["2024-12","2026-08"]),
    ]
    for key, lab_a, lab_b, rng_a, rng_b in pairs:
        t = regime_test(monthly, rng_a, rng_b, "mean_ships_port_adj")
        summary["regimes"].setdefault(key, {"label": f"{lab_a} vs {lab_b}", "test": t})

    with open(os.path.join(DET_DIR, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=1)
    return monthly, yearly, chg, summary


if __name__ == "__main__":
    monthly, yearly, chg, summary = full_analysis()
    print(monthly.to_string())
    print()
    print(yearly.to_string())
    print()
    print("MK:", summary["mk_tau"], summary["mk_p"], summary["mk_direction"], summary["sen_slope_units_per_month"])
    print("months without data:", summary["months_no_data"])
