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
    # Unreachable, and kept anyway. By the time control arrives here the curve
    # is non-empty and first <= months < last, and consecutive pairs partition
    # [first, last), so some pair always matches; with a single measured point
    # the two conditions cannot hold together and an earlier branch returned.
    # Excluded from coverage rather than covered by a test, because the only
    # input that reaches it is a NaN in months_elapsed — every comparison
    # against NaN being false — and the survival curve never produces one.
    return None, None, "could not bracket the cutoff"  # pragma: no cover


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
        exposure = p.get("label_exposure", "unknown")
        measured = p.get("measured_overlap")

        # Date axis. Only meaningful once we know labels were involved at all.
        if not cutoff or not verified:
            date_tier = "UNVERIFIED"
            months = lo = hi = None
            why = ("no sourced training cutoff" if not cutoff
                   else "cutoff present but not verified against a source")
        else:
            c = parse_month(str(cutoff))
            months = months_between(baseline, c)
            if months <= 0:
                date_tier = "CLEAN"
            elif endpoint_months is not None and months >= endpoint_months:
                date_tier = "CONTAMINATED"
            else:
                date_tier = "PARTIAL"
            lo, hi, why = leakage_range(months, points)

        # Verdict combines both axes. A measurement outranks any inference; a
        # model with no clinical labels cannot memorise reclassifications
        # whatever its release date, so dating it is beside the point.
        if measured:
            verdict = "MEASURED LEAK"
        elif exposure == "none":
            verdict = "LABEL-FREE"
        elif exposure == "threshold_only":
            verdict = "LABEL-FREE (score)"
        elif exposure == "evaluation_only":
            verdict = f"INDIRECT / {date_tier}"
        elif exposure == "training_labels":
            verdict = f"DIRECT / {date_tier}"
        else:
            verdict = f"UNKNOWN / {date_tier}"

        rows.append({"predictor": label, "date_tier": date_tier,
                     "exposure": exposure, "verdict": verdict,
                     "cutoff": cutoff, "verified": verified,
                     "months_past_baseline": months,
                     "leak_low": lo, "leak_high": hi, "leak_note": why,
                     "uses_clinvar": p.get("uses_clinvar", "unknown"),
                     "measured": measured, "source": p.get("source")})

    # Riskiest first: measured leaks, then direct label exposure, then the rest.
    def risk(r):
        if r["measured"]:
            return 0
        if r["exposure"] == "training_labels":
            return 1 if r["date_tier"] != "CLEAN" else 3
        if r["exposure"] in ("evaluation_only", "unknown"):
            return 2
        return 4
    rows.sort(key=lambda r: (risk(r), r["predictor"]))

    usable = [r for r in rows if r["verdict"].startswith("LABEL-FREE")
              or r["verdict"].endswith("/ CLEAN")]

    print(f"baseline: {args.baseline}")
    if total_plp is not None:
        print(f"labels in the window: {total_plp:,} VUS -> P/LP over "
              f"{endpoint_months} months\n")
    for r in rows:
        extra = ""
        if r["measured"]:
            extra = "  <-- overlap measured, see report"
        elif r["leak_low"] is not None and total_plp and r["leak_high"]:
            extra = f"  up to {r['leak_high']:,} labels exposed"
        print(f"  [{r['verdict']:22s}] {r['predictor']:24s}{extra}")
    print(f"\nusable without a contamination caveat: {len(usable)}/{len(rows)}")
    for r in usable:
        print(f"  + {r['predictor']}")

    # --- report --------------------------------------------------------------
    L = [f"# Contamination audit — baseline {args.baseline}\n"]
    L.append("Whether a predictor could already have been told this benchmark's "
             "answer. Two things decide that, and they are independent:\n")
    L.append("- **When** its training data was fixed (`training_cutoff`).\n"
             "- **Whether** curated clinical labels entered the model at all "
             "(`label_exposure`), and in what role.\n")
    L.append("A sequence-only model has no clinical labels to memorise, so its "
             "release date barely matters. A model fit on ClinVar P/LP labels is "
             "exposed in proportion to how recent its snapshot was. Ranking on "
             "dates alone would score those two the same, which is wrong.\n")
    if total_plp is not None:
        L.append(f"Window: **{total_plp:,}** VUS → P/LP reclassifications over "
                 f"{endpoint_months} months.\n")

    L.append("## Verdicts\n")
    L.append("| predictor | verdict | label exposure | cutoff | labels exposed |")
    L.append("|---|---|---|---|---|")
    for r in rows:
        if r["measured"]:
            leak = "**measured — see below**"
        elif r["leak_low"] is None or not total_plp:
            leak = "—"
        elif r["leak_low"] == r["leak_high"]:
            leak = f"{r['leak_low']:,}"
        else:
            leak = f"{r['leak_low']:,}–{r['leak_high']:,}"
        L.append(f"| {r['predictor']} | {r['verdict']} | {r['exposure']} "
                 f"| {r['cutoff'] or '—'} | {leak} |")
    L.append("")

    L.append(f"**{len(usable)} of {len(rows)}** carry no contamination caveat "
             "for this baseline:\n")
    for r in usable:
        L.append(f"- {r['predictor']} — {r['verdict']}")
    L.append("")

    for r in rows:
        if not r["measured"]:
            continue
        m = r["measured"]
        L.append(f"## Measured exposure — {r['predictor']}\n")
        L.append("The only entry whose exposure was measured rather than "
                 "inferred from a stated date.\n")
        L.append(f"- Method: {m.get('method','')}\n")
        L.append(f"- Reclassified arm: **{m.get('vus_to_plp','')}**")
        L.append(f"- Control arm: {m.get('control_still_vus','')}")
        L.append(f"- Odds ratio: {m.get('odds_ratio','')}")
        L.append(f"- {m.get('match_labels','')}\n")
        bh = m.get("by_horizon") or {}
        if bh:
            L.append("| horizon | overlap |\n|---|---|")
            for k in sorted(bh):
                L.append(f"| {k} | {bh[k]} |")
            L.append("")
        if m.get("dates_the_snapshot"):
            L.append(f"{m['dates_the_snapshot']}\n")
        if m.get("leak_scope"):
            L.append(f"**Scope.** {m['leak_scope']}\n")

    n_unver = sum(1 for r in rows if r["date_tier"] == "UNVERIFIED"
                  and r["exposure"] in ("training_labels", "evaluation_only", "unknown"))
    if n_unver:
        L.append("## Still unresolved\n")
        L.append(f"{n_unver} predictors have clinical-label exposure and no "
                 "sourced cutoff. An unverified tool is not a clean tool, it is "
                 "an unmeasured one, so none of these may be reported as a clean "
                 "baseline until `training_cutoff`, `source` and `verified` are "
                 "filled in `predictors.yaml`.\n")
        for r in rows:
            if r["date_tier"] == "UNVERIFIED" and r["exposure"] in (
                    "training_labels", "evaluation_only", "unknown"):
                L.append(f"- {r['predictor']} ({r['exposure']})")
        L.append("")

    L.append("Leakage figures are bracketed between the survival curve's "
             "measured time points rather than interpolated, and are upper "
             "bounds: using ClinVar does not mean using every reclassification "
             "in it.\n")

    os.makedirs(RESULTS, exist_ok=True)
    out_md = os.path.join(RESULTS, "contamination_audit.md")
    with open(out_md, "w") as fh:
        fh.write("\n".join(L))
    with open(os.path.join(RESULTS, "_contamination_audit.json"), "w") as fh:
        json.dump({"baseline": args.baseline, "labels_in_window": total_plp,
                   "endpoint_months": endpoint_months,
                   "usable": [r["predictor"] for r in usable],
                   "predictors": rows}, fh, indent=2)
    print(f"\nwrote {out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
