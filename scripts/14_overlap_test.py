#!/usr/bin/env python3
"""Test any published evaluation set for overlap with this benchmark's labels.

Generalises the AlphaMissense analysis. Any predictor that publishes the list of
variants it was evaluated or calibrated on can be checked the same way, and the
check yields two things:

  MAGNITUDE   how much of the reclassified arm sits in the list, against a
              control arm of variants that stayed VUS. The control is what
              separates real exposure from two large variant sets happening to
              intersect.

  DATE        the overlap broken down by horizon — when each label first
              appeared. A list drawn from a snapshot taken at date D shows a
              cliff: high overlap for horizons before D, near-zero after. The
              position of the cliff dates a snapshot the publication may never
              have named.

A BUILD GUARD matters more than it looks. This benchmark keys on GRCh38. A list
in GRCh37 coordinates joins to almost nothing, and 0% overlap reads exactly like
"no contamination" — the most dangerous possible failure for this analysis. So a
near-zero overlap combined with IDs that do not look like GRCh38 is reported as
UNUSABLE rather than clean.

Usage:
  14_overlap_test.py --export data/exports/vus_hindsight_for_am_join.csv \
      --list "AlphaMissense S5:data/s5.csv:variant_id:label" \
      --list "AlphaMissense S6:data/s6.csv:variant_id:label"
"""
import argparse
import hashlib
import json
import os
import sys

import duckdb
from scipy.stats import fisher_exact

RESULTS = "results"


def md5(path):
    h = hashlib.md5(usedforsecurity=False)
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def analyse(con, name, path, id_col, label_col):
    con.execute(f"""
        CREATE OR REPLACE TABLE lst AS
        SELECT * FROM read_csv('{path}', header=true, all_varchar=true)
    """)
    n_list = con.execute("SELECT count(*) FROM lst").fetchone()[0]

    # Build guard. Count how many of the list's IDs carry a GRCh38 suffix, and
    # how many carry GRCh37 — a list keyed on the wrong build cannot join.
    build = con.execute(f"""
        SELECT
          count(*) FILTER (WHERE "{id_col}" LIKE '%\\_hg38' ESCAPE '\\') AS hg38,
          count(*) FILTER (WHERE "{id_col}" LIKE '%\\_hg19' ESCAPE '\\') AS hg19,
          count(*) AS total
        FROM lst
    """).fetchone()
    hg38, hg19, total = build

    con.execute(f"""
        CREATE OR REPLACE TABLE j AS
        SELECT e.arm, e.horizon_months, e.stratum,
               l."{id_col}" IS NOT NULL AS hit,
               l."{label_col}" AS list_label
        FROM export e
        LEFT JOIN lst l ON e.variant_id_hg38 = l."{id_col}"
        WHERE e.molecular_consequence = 'missense'
    """)
    arms = con.execute("""
        SELECT arm, count(*) n, count(*) FILTER (WHERE hit) hit
        FROM j GROUP BY 1 ORDER BY 1
    """).fetchall()
    stats = {a: {"n": n, "hit": h, "pct": round(100.0 * h / n, 4) if n else None}
             for a, n, h in arms}

    plp, ctl = stats.get("vus_to_plp", {}), stats.get("still_vus", {})
    odds = pval = None
    if plp.get("n") and ctl.get("n"):
        odds, pval = fisher_exact(
            [[plp["hit"], plp["n"] - plp["hit"]],
             [ctl["hit"], ctl["n"] - ctl["hit"]]], alternative="greater")

    horizons = con.execute("""
        SELECT horizon_months, count(*) n, count(*) FILTER (WHERE hit) hit
        FROM j WHERE arm='vus_to_plp'
        GROUP BY 1 ORDER BY TRY_CAST(horizon_months AS INT)
    """).fetchall()
    labels = con.execute("""
        SELECT list_label, count(*) n FROM j
        WHERE hit AND arm='vus_to_plp' GROUP BY 1 ORDER BY n DESC
    """).fetchall()

    # A list whose IDs are predominantly a different build joins to nothing, and
    # that must not be reported as absence of exposure.
    total_hits = sum(h for _, _, h in arms)
    unusable = total_hits == 0 and hg38 < total * 0.5
    verdict = "UNUSABLE (coordinate build mismatch)" if unusable else None
    if verdict is None:
        rate = plp.get("pct") or 0.0
        ctl_rate = ctl.get("pct") or 0.0
        if rate >= 1.0 and rate > 10 * max(ctl_rate, 1e-9):
            verdict = "EXPOSED"
        elif total_hits == 0:
            verdict = "NO OVERLAP"
        else:
            verdict = "MINIMAL"

    return {"name": name, "file": os.path.basename(path), "md5": md5(path),
            "list_rows": n_list, "ids_hg38": hg38, "ids_hg19": hg19,
            "by_arm": stats, "verdict": verdict,
            "odds_ratio": float(odds) if odds is not None else None,
            "p_value": float(pval) if pval is not None else None,
            "labels": {str(lab): n for lab, n in labels},
            "by_horizon": [{"horizon": h, "n": n, "hit": hit,
                            "pct": round(100.0 * hit / n, 4) if n else None}
                           for h, n, hit in horizons]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--export", default="data/exports/vus_hindsight_for_am_join.csv")
    ap.add_argument("--list", action="append", required=True,
                    help="name:path:id_column:label_column")
    args = ap.parse_args()

    os.makedirs(RESULTS, exist_ok=True)
    con = duckdb.connect()
    con.execute(f"""
        CREATE TABLE export AS
        SELECT * FROM read_csv('{args.export}', header=true, all_varchar=true)
    """)

    out = []
    for spec in args.list:
        name, path, id_col, label_col = spec.rsplit(":", 3)
        if not os.path.exists(path):
            print(f"FATAL: {path} not found", file=sys.stderr)
            return 1
        r = analyse(con, name, path, id_col, label_col)
        out.append(r)
        print(f"\n=== {name} ({r['list_rows']:,} rows, "
              f"{r['ids_hg38']:,} hg38 / {r['ids_hg19']:,} hg19) ===")
        for a, s in r["by_arm"].items():
            print(f"  {a:12s} {s['hit']:>6,} / {s['n']:>6,} = {s['pct']:6.3f}%")
        if r["odds_ratio"]:
            print(f"  OR = {r['odds_ratio']:,.0f}")
        for h in r["by_horizon"]:
            print(f"  +{h['horizon']:>3} months: {h['hit']:>5,} / {h['n']:>5,} "
                  f"= {h['pct']:6.2f}%")
        print(f"  verdict: {r['verdict']}")

    L = ["# Overlap tests against published evaluation sets\n"]
    L.append("Any predictor that publishes the variants it was evaluated or "
             "calibrated on can be tested the same way. Each test yields a "
             "magnitude — how much of the reclassified arm is in the list, "
             "against a control that stayed VUS — and a date, from the horizon "
             "at which the overlap collapses.\n")
    L.append("| evaluation set | rows | reclassified | control | OR | verdict |")
    L.append("|---|---|---|---|---|---|")
    for r in out:
        p = r["by_arm"].get("vus_to_plp", {})
        c = r["by_arm"].get("still_vus", {})
        orr = f"{r['odds_ratio']:,.0f}" if r["odds_ratio"] else "—"
        L.append(f"| {r['name']} | {r['list_rows']:,} "
                 f"| {p.get('hit',0):,} / {p.get('n',0):,} "
                 f"({p.get('pct',0):.3f}%) "
                 f"| {c.get('hit',0):,} / {c.get('n',0):,} "
                 f"({c.get('pct',0):.3f}%) | {orr} | **{r['verdict']}** |")
    L.append("")

    for r in out:
        L.append(f"## {r['name']}\n")
        L.append(f"`{r['file']}`, md5 `{r['md5']}` — {r['list_rows']:,} rows, "
                 f"{r['ids_hg38']:,} keyed on GRCh38 and {r['ids_hg19']:,} on "
                 f"GRCh37.\n")
        if r["verdict"].startswith("UNUSABLE"):
            L.append("**This list cannot be tested.** Its identifiers are "
                     "predominantly GRCh37, and this benchmark keys on GRCh38, "
                     "so the join finds nothing for a reason that has nothing to "
                     "do with contamination. Reporting the resulting 0% as "
                     "absence of exposure would be the most misleading outcome "
                     "available, so it is refused instead. Lift the list over to "
                     "GRCh38 to test it.\n")
            continue
        L.append("| horizon | in list | total | rate |\n|---|---|---|---|")
        for h in r["by_horizon"]:
            L.append(f"| +{h['horizon']} months | {h['hit']:,} | {h['n']:,} "
                     f"| **{h['pct']:.2f}%** |")
        L.append("")
        if r["labels"]:
            L.append("Labels carried by the matches: "
                     + ", ".join(f"`{k}` × {v:,}" for k, v in r["labels"].items())
                     + "\n")

    L.append("## Reading these\n")
    L.append("A high rate in the reclassified arm alongside a near-zero rate in "
             "the control is exposure. Comparable rates in both would instead "
             "mean the list simply covers a lot of variants.\n")
    L.append("A cliff across horizons dates the snapshot: the label was already "
             "in ClinVar when the list was built for horizons before the cliff, "
             "and had not appeared yet for horizons after it.\n")

    with open(os.path.join(RESULTS, "overlap_tests.md"), "w") as fh:
        fh.write("\n".join(L))
    with open(os.path.join(RESULTS, "_overlap_tests.json"), "w") as fh:
        json.dump(out, fh, indent=2)
    print(f"\nwrote {os.path.join(RESULTS, 'overlap_tests.md')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
