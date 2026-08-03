#!/usr/bin/env python3
"""Classify predictors by how much of this benchmark's answer they could have seen.

The labels here are ClinVar reclassifications between a baseline and an
endpoint. A predictor trained on data from within that window may already have
been told the outcome, so accuracy on this benchmark would be partly
memorisation. This turns that worry into a per-tool verdict, and — using the
measured survival curve — into a bound on how many labels were exposed.

Three tiers relative to a baseline B and endpoint E:

  CLEAN         cutoff <= B   nothing after the baseline could have leaked
  PARTIAL       B < cutoff < E  some reclassifications had already happened
  CONTAMINATED  cutoff >= E   every label in the window was potentially visible
  UNVERIFIED    no sourced cutoff

UNVERIFIED is deliberately not folded into CLEAN. A tool whose training cutoff
nobody has checked is not a clean tool; it is an unmeasured one, and reporting
it as clean is how a contaminated result gets published.

Leakage is quoted as a RANGE between the survival curve's measured time points
rather than interpolated to a single number, because interpolation here would
invent precision the data does not have.

Usage:
  11_contamination_audit.py [--registry predictors.yaml] [--baseline 2021-06]
"""
import argparse
import json
import os
from datetime import date

import yaml

RESULTS = "results"


def months_between(a, b):
    return (b.year - a.year) * 12 + (b.month - a.month)


def parse_month(label):
    y, m = (int(x) for x in label.split("-")[:2])
    return date(y, m, 1)


def leakage_range(months, points):
    """Bound the labels visible by `months` after baseline, from measured points.

    Returns (low, high, description). Uses only the measured survival points,
    so the answer is a bracket rather than a fabricated interpolation.
    """
    if not points:
        return None, None, "no survival curve available"
    ordered = sorted(points, key=lambda p: p["months_elapsed"])
    first, last = ordered[0], ordered[-1]
    if months <= 0:
        return 0, 0, "cutoff at or before the baseline"
    if months >= last["months_elapsed"]:
        return last["p_lp"], last["p_lp"], (
            f"cutoff at or beyond the last measured point "
            f"({last['months_elapsed']} months)")
    if months < first["months_elapsed"]:
        return 0, first["p_lp"], (
            f"cutoff before the first measured point "
            f"({first['months_elapsed']} months)")
    for lo, hi in zip(ordered, ordered[1:]):
        if lo["months_elapsed"] <= months < hi["months_elapsed"]:
            return lo["p_lp"], hi["p_lp"], (
                f"cutoff between the {lo['months_elapsed']}- and "
                f"{hi['months_elapsed']}-month points")
    return None, None, "could not bracket the cutoff"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--registry", default="predictors.yaml")
    ap.add_argument("--baseline", default="2021-06")
    ap.add_argument("--survival", default=os.path.join(RESULTS, "_survival.json"))
    args = ap.parse_args()

    reg = yaml.safe_load(open(args.registry))
    preds = reg.get("predictors", [])
    baseline = parse_month(args.baseline)

    points = []
    if os.path.exists(args.survival):
        points = json.load(open(args.survival))
    total_plp = max((p["p_lp"] for p in points), default=None)
    endpoint_months = max((p["months_elapsed"] for p in points), default=None)

    rows = []
    for p in preds:
        label = p["name"] + (f" ({p['version']})" if p.get("version") else "")
        cutoff = p.get("training_cutoff")
        verified = bool(p.get("verified"))

        if not cutoff or not verified:
            tier = "UNVERIFIED"
            months = None
            lo = hi = None
            why = ("no sourced training cutoff" if not cutoff
                   else "cutoff present but not verified against a source")
        else:
            c = date.fromisoformat(str(cutoff)) if len(str(cutoff)) > 7 \
                else parse_month(str(cutoff))
            months = months_between(baseline, c)
            if months <= 0:
                tier = "CLEAN"
            elif endpoint_months is not None and months >= endpoint_months:
                tier = "CONTAMINATED"
            else:
                tier = "PARTIAL"
            lo, hi, why = leakage_range(months, points)

        rows.append({"predictor": label, "tier": tier, "cutoff": cutoff,
                     "verified": verified, "months_past_baseline": months,
                     "leak_low": lo, "leak_high": hi, "leak_note": why,
                     "uses_clinvar": p.get("uses_clinvar", "unknown"),
                     "category": p.get("category"),
                     "source": p.get("source")})

    order = {"CLEAN": 0, "PARTIAL": 1, "CONTAMINATED": 2, "UNVERIFIED": 3}
    rows.sort(key=lambda r: (order[r["tier"]], r["predictor"]))

    counts = {}
    for r in rows:
        counts[r["tier"]] = counts.get(r["tier"], 0) + 1

    print(f"baseline: {args.baseline}")
    if total_plp is not None:
        print(f"labels in the window: {total_plp:,} VUS -> P/LP over "
              f"{endpoint_months} months")
    print()
    for tier in ("CLEAN", "PARTIAL", "CONTAMINATED", "UNVERIFIED"):
        n = counts.get(tier, 0)
        print(f"  {tier:13s} {n:>3d}")
    print()
    for r in rows:
        leak = ""
        if r["leak_low"] is not None and total_plp:
            if r["leak_low"] == r["leak_high"]:
                leak = f"  up to {r['leak_low']:,} labels " \
                       f"({100.0 * r['leak_low'] / total_plp:.0f}%)"
            else:
                leak = (f"  {r['leak_low']:,}-{r['leak_high']:,} labels "
                        f"({100.0 * r['leak_low'] / total_plp:.0f}-"
                        f"{100.0 * r['leak_high'] / total_plp:.0f}%)")
        print(f"  [{r['tier']:12s}] {r['predictor']:24s}{leak}")

    # --- report --------------------------------------------------------------
    L = [f"# Contamination audit — baseline {args.baseline}\n"]
    L.append("Whether a predictor could already have been told this benchmark's "
             "answer. The labels are ClinVar reclassifications between the "
             "baseline and the endpoint; a model trained on data from inside "
             "that window may be recalling them rather than predicting them.\n")
    if total_plp is not None:
        L.append(f"Window: **{total_plp:,}** VUS → P/LP reclassifications over "
                 f"{endpoint_months} months, from "
                 f"[`survival.md`](survival.md).\n")
    L.append("| tier | meaning |\n|---|---|\n"
             "| CLEAN | training cutoff at or before the baseline |\n"
             "| PARTIAL | cutoff inside the window; some labels were visible |\n"
             "| CONTAMINATED | cutoff at or beyond the endpoint |\n"
             "| UNVERIFIED | no sourced cutoff — **not** the same as clean |\n")
    L.append("")
    L.append("| predictor | tier | cutoff | labels potentially seen | uses ClinVar |")
    L.append("|---|---|---|---|---|")
    for r in rows:
        if r["leak_low"] is None or not total_plp:
            leak = "—"
        elif r["leak_low"] == r["leak_high"]:
            leak = f"{r['leak_low']:,} ({100.0 * r['leak_low'] / total_plp:.0f}%)"
        else:
            leak = (f"{r['leak_low']:,}–{r['leak_high']:,} "
                    f"({100.0 * r['leak_low'] / total_plp:.0f}–"
                    f"{100.0 * r['leak_high'] / total_plp:.0f}%)")
        L.append(f"| {r['predictor']} | {r['tier']} | {r['cutoff'] or '—'} "
                 f"| {leak} | {r['uses_clinvar']} |")
    L.append("")
    n_unver = counts.get("UNVERIFIED", 0)
    if n_unver:
        L.append(f"**{n_unver} of {len(rows)} predictors have no sourced training "
                 "cutoff.** Until those are filled in from the literature, this "
                 "audit cannot say the benchmark is uncontaminated for them — "
                 "and an unverified tool must not be reported as a clean "
                 "baseline. Fill `training_cutoff`, `source` and `verified` in "
                 "`predictors.yaml`.\n")
    L.append("Leakage is quoted as a range between the survival curve's measured "
             "time points rather than interpolated, so the bound comes from "
             "measurement rather than from a fitted line. It is an upper bound "
             "on exposure: a predictor may have used ClinVar without using "
             "every reclassification in it.\n")

    os.makedirs(RESULTS, exist_ok=True)
    out_md = os.path.join(RESULTS, "contamination_audit.md")
    with open(out_md, "w") as fh:
        fh.write("\n".join(L))
    with open(os.path.join(RESULTS, "_contamination_audit.json"), "w") as fh:
        json.dump({"baseline": args.baseline, "labels_in_window": total_plp,
                   "endpoint_months": endpoint_months,
                   "counts": counts, "predictors": rows}, fh, indent=2)
    print(f"\nwrote {out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
