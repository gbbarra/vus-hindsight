#!/usr/bin/env python3
"""Follow ONE fixed VUS cohort through several later snapshots.

The transition analysis varies the start date and holds the end fixed. This
does the opposite: it freezes a single cohort — the VUS present at one baseline
— and asks what fraction had resolved at each of several later dates.

Holding the cohort fixed is the point. The transition analysis compares
different baselines, so a difference in rate is confounded with cohort
composition: a later baseline contains many recently submitted, less mature
variants. Here the denominator never changes, so the only thing varying is
elapsed time.

Two modes:

  build the cohort once
    07_survival.py --baseline data/variant_summary_2021-06.txt.gz \
                   --baseline-label 2021-06 --out-cohort data/cohort.parquet

  evaluate it at one later snapshot (repeat per endpoint)
    07_survival.py --cohort data/cohort.parquet --baseline-label 2021-06 \
                   --endpoint data/variant_summary_2022-12.txt.gz \
                   --endpoint-label 2022-12 \
                   --consequence-map data/consequence_map.parquet

Each evaluation appends one point to results/_survival.json.
"""

import argparse
import json
import os
import sys

import duckdb
from snapshot import load_snapshot

RESULTS = "results"
SURVIVAL_JSON = os.path.join(RESULTS, "_survival.json")


def months_between(a, b):
    """Whole months between two YYYY-MM labels."""
    ay, am = (int(x) for x in a.split("-")[:2])
    by, bm = (int(x) for x in b.split("-")[:2])
    return (by - ay) * 12 + (bm - am)


def build_cohort(args, con):
    meta = load_snapshot(
        con, "base", args.baseline, f"cohort baseline {args.baseline_label}"
    )
    con.execute("""
        CREATE OR REPLACE TABLE cohort AS
        SELECT variation_id, gene, hgvs, raw_class, raw_review
        FROM base WHERE bucket = 'Still VUS' AND stars >= 1
    """)
    n = con.execute("SELECT count(*) FROM cohort").fetchone()[0]
    print(f"\ncohort fixed at {args.baseline_label}: {n:,} VUS with assertion criteria")
    con.execute(f"COPY cohort TO '{args.out_cohort}' (FORMAT parquet)")
    print(f"wrote {args.out_cohort}")

    os.makedirs(RESULTS, exist_ok=True)
    with open(os.path.join(RESULTS, "_survival_cohort.json"), "w") as fh:
        json.dump(
            {
                "baseline_label": args.baseline_label,
                "baseline_file": os.path.basename(args.baseline),
                "cohort_size": n,
                "snapshot": meta,
            },
            fh,
            indent=2,
        )
    return 0


def evaluate_point(args, con):
    con.execute(
        f"CREATE OR REPLACE TABLE cohort AS SELECT * FROM read_parquet('{args.cohort}')"
    )
    n_cohort = con.execute("SELECT count(*) FROM cohort").fetchone()[0]
    load_snapshot(con, "endp", args.endpoint, f"endpoint {args.endpoint_label}")

    con.execute(f"""
        CREATE OR REPLACE TABLE cons AS
        SELECT * FROM read_parquet('{args.consequence_map}')
    """)

    con.execute("""
        CREATE OR REPLACE TABLE state AS
        SELECT c.variation_id,
               coalesce(e.gene, c.gene) AS gene,
               coalesce(m.consequence, 'not_in_vcf') AS consequence,
               e.stars AS stars,
               CASE WHEN e.variation_id IS NULL THEN 'Retired/absent'
                    ELSE e.bucket END AS bucket
        FROM cohort c
        LEFT JOIN endp e USING (variation_id)
        LEFT JOIN cons m USING (variation_id)
    """)

    rows = con.execute("""
        SELECT bucket, count(*) n FROM state GROUP BY 1 ORDER BY n DESC
    """).fetchall()
    dist = {b: n for b, n in rows}

    plp = dist.get("P/LP", 0)
    blb = dist.get("B/LB", 0)
    still = dist.get("Still VUS", 0)
    hard = con.execute("""
        SELECT count(*) FROM state
        WHERE bucket = 'P/LP' AND consequence = 'missense' AND stars >= 2
    """).fetchone()[0]
    genes = con.execute("""
        SELECT count(DISTINCT gene) FROM state
        WHERE bucket = 'P/LP' AND gene IS NOT NULL AND gene NOT IN ('','-')
    """).fetchone()[0]

    months = months_between(args.baseline_label, args.endpoint_label)
    point = {
        "endpoint_label": args.endpoint_label,
        "endpoint_file": os.path.basename(args.endpoint),
        "months_elapsed": months,
        "cohort_size": n_cohort,
        "distribution": dist,
        "p_lp": plp,
        "b_lb": blb,
        "still_vus": still,
        "definitive": plp + blb,
        "hard_stratum": hard,
        "p_lp_genes": genes,
        "pct_p_lp": round(100.0 * plp / n_cohort, 4),
        "pct_definitive": round(100.0 * (plp + blb) / n_cohort, 4),
        "pct_still_vus": round(100.0 * still / n_cohort, 4),
    }

    print(
        f"\n=== {args.baseline_label} cohort at {args.endpoint_label} "
        f"(+{months} months) ==="
    )
    for b, n in rows:
        print(f"  {b:16s} {n:>10,}  {100.0 * n / n_cohort:5.2f}%")
    print(
        f"  -> P/LP {plp:,} ({point['pct_p_lp']:.2f}%), "
        f"definitive {plp + blb:,} ({point['pct_definitive']:.2f}%), "
        f"hard stratum {hard:,}, genes {genes:,}"
    )

    os.makedirs(RESULTS, exist_ok=True)
    points = []
    if os.path.exists(SURVIVAL_JSON):
        points = json.load(open(SURVIVAL_JSON))
    points = [p for p in points if p["endpoint_label"] != args.endpoint_label]
    points.append(point)
    points.sort(key=lambda p: p["months_elapsed"])
    with open(SURVIVAL_JSON, "w") as fh:
        json.dump(points, fh, indent=2)
    print(f"  appended to {SURVIVAL_JSON} ({len(points)} points)")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline")
    ap.add_argument("--baseline-label", required=True)
    ap.add_argument("--out-cohort")
    ap.add_argument("--cohort")
    ap.add_argument("--endpoint")
    ap.add_argument("--endpoint-label")
    ap.add_argument("--consequence-map")
    ap.add_argument("--memory-limit", default="6GB")
    ap.add_argument("--temp-dir", default="data/duckdb_tmp")
    args = ap.parse_args()

    os.makedirs(args.temp_dir, exist_ok=True)
    con = duckdb.connect()
    con.execute(f"PRAGMA memory_limit='{args.memory_limit}'")
    con.execute(f"PRAGMA temp_directory='{args.temp_dir}'")

    if args.baseline and args.out_cohort:
        return build_cohort(args, con)
    if args.cohort and args.endpoint and args.endpoint_label:
        if not args.consequence_map or not os.path.exists(args.consequence_map):
            print(
                "FATAL: --consequence-map is required and must exist; the hard "
                "stratum is defined by the VCF MC field, never inferred here.",
                file=sys.stderr,
            )
            return 1
        return evaluate_point(args, con)
    ap.error("either --baseline/--out-cohort or --cohort/--endpoint/--endpoint-label")


if __name__ == "__main__":
    sys.exit(main())
