#!/usr/bin/env python3
"""Measure how closely a frozen-date reconstruction matches the real snapshot.

The reconstruction in 09_reconstruct.py rebuilds what ClinVar would have said at
a past date from submission dates. Whether that is trustworthy is an empirical
question, and it is answerable: for dates where an archived snapshot exists, the
reconstruction can be compared against the truth.

This reports coverage, agreement on the coarse bucket and on the star rating,
the confusion between buckets, and — the number that decides whether the
approach is usable — how much of the real VUS cohort the reconstruction
recovers.

Usage:
  10_validate_reconstruction.py --reconstructed data/reconstructed_2021-06.parquet \
                                --actual data/variant_summary_2021-06.txt.gz \
                                --label 2021-06
"""
import argparse
import json
import os
import sys

import duckdb
from schema import bucket_sql
from snapshot import load_snapshot

RESULTS = "results"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reconstructed", required=True)
    ap.add_argument("--actual", required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--memory-limit", default="6GB")
    ap.add_argument("--temp-dir", default="data/duckdb_tmp")
    args = ap.parse_args()

    os.makedirs(args.temp_dir, exist_ok=True)
    os.makedirs(RESULTS, exist_ok=True)

    con = duckdb.connect()
    con.execute(f"PRAGMA memory_limit='{args.memory_limit}'")
    con.execute(f"PRAGMA temp_directory='{args.temp_dir}'")

    load_snapshot(con, "actual", args.actual, f"actual {args.label}")
    con.execute(f"""
        CREATE OR REPLACE TABLE recon AS
        SELECT variation_id,
               classification AS raw_class,
               review_status  AS raw_review,
               stars,
               {bucket_sql('classification')} AS bucket
        FROM read_parquet('{args.reconstructed}')
    """)

    n_actual = con.execute("SELECT count(*) FROM actual").fetchone()[0]
    n_recon = con.execute("SELECT count(*) FROM recon").fetchone()[0]

    # Compare only on GRCh38 variants present in the real snapshot: those are the
    # ones a cohort would ever be drawn from.
    con.execute("""
        CREATE OR REPLACE TABLE cmp AS
        SELECT a.variation_id,
               a.bucket AS actual_bucket, a.stars AS actual_stars,
               r.bucket AS recon_bucket,  r.stars AS recon_stars,
               r.variation_id IS NOT NULL AS covered
        FROM actual a LEFT JOIN recon r USING (variation_id)
    """)
    covered = con.execute("SELECT count(*) FROM cmp WHERE covered").fetchone()[0]

    print(f"\n=== reconstruction vs actual, {args.label} ===")
    print(f"variants in real snapshot (GRCh38, deduped): {n_actual:,}")
    print(f"variants reconstructed (all assemblies)    : {n_recon:,}")
    print(f"real variants with a reconstruction        : {covered:,} "
          f"({100.0 * covered / n_actual:.2f}%)")

    agree = con.execute("""
        SELECT
          count(*) FILTER (WHERE covered)                                   AS n,
          count(*) FILTER (WHERE covered AND actual_bucket = recon_bucket)  AS bucket_ok,
          count(*) FILTER (WHERE covered AND actual_stars  = recon_stars)   AS stars_ok,
          count(*) FILTER (WHERE covered AND actual_bucket = recon_bucket
                             AND actual_stars = recon_stars)                AS both_ok
        FROM cmp
    """).fetchone()
    n_cov, bucket_ok, stars_ok, both_ok = agree
    print(f"\nagreement among covered variants ({n_cov:,}):")
    print(f"  bucket           : {bucket_ok:,} ({100.0 * bucket_ok / n_cov:.2f}%)")
    print(f"  review stars     : {stars_ok:,} ({100.0 * stars_ok / n_cov:.2f}%)")
    print(f"  both             : {both_ok:,} ({100.0 * both_ok / n_cov:.2f}%)")

    print("\nbucket confusion (actual -> reconstructed), top 15:")
    conf = con.execute("""
        SELECT actual_bucket, recon_bucket, count(*) n
        FROM cmp WHERE covered GROUP BY 1,2 ORDER BY n DESC LIMIT 15
    """).fetchall()
    for a, r, n_ in conf:
        flag = "" if a == r else "   <-- mismatch"
        print(f"  {a:16s} -> {r:16s} {n_:>9,}{flag}")

    print("\nstar drift (reconstructed minus actual), covered variants:")
    drift = con.execute("""
        SELECT recon_stars - actual_stars AS d, count(*) n
        FROM cmp WHERE covered GROUP BY 1 ORDER BY d
    """).fetchall()
    for d, n_ in drift:
        print(f"  {d:+d}  {n_:>9,}  ({100.0 * n_ / n_cov:5.2f}%)")

    # The decisive number: the benchmark's cohort is "VUS with criteria at
    # baseline". If the reconstruction cannot recover that set, it cannot
    # support a frozen-date evaluation no matter how good the totals look.
    coh = con.execute("""
        SELECT
          count(*) FILTER (WHERE actual_bucket = 'Still VUS' AND actual_stars >= 1) AS real_cohort,
          count(*) FILTER (WHERE actual_bucket = 'Still VUS' AND actual_stars >= 1
                             AND covered)                                           AS covered_cohort,
          count(*) FILTER (WHERE actual_bucket = 'Still VUS' AND actual_stars >= 1
                             AND recon_bucket = 'Still VUS')                        AS recovered_vus,
          count(*) FILTER (WHERE actual_bucket = 'Still VUS' AND actual_stars >= 1
                             AND recon_bucket = 'Still VUS' AND recon_stars >= 1)   AS recovered_cohort
        FROM cmp
    """).fetchone()
    real_cohort, covered_cohort, recovered_vus, recovered_cohort = coh
    print("\n=== the cohort that matters ===")
    print(f"real VUS cohort (>=1 star)          : {real_cohort:,}")
    print(f"  with any reconstruction           : {covered_cohort:,} "
          f"({100.0 * covered_cohort / real_cohort:.2f}%)")
    print(f"  reconstructed as VUS              : {recovered_vus:,} "
          f"({100.0 * recovered_vus / real_cohort:.2f}%)")
    print(f"  reconstructed as VUS with >=1 star: {recovered_cohort:,} "
          f"({100.0 * recovered_cohort / real_cohort:.2f}%)")

    out = {
        "label": args.label,
        "actual_file": os.path.basename(args.actual),
        "variants_actual": n_actual,
        "variants_reconstructed": n_recon,
        "covered": covered,
        "pct_covered": round(100.0 * covered / n_actual, 4),
        "agreement": {
            "n": n_cov,
            "bucket": bucket_ok, "pct_bucket": round(100.0 * bucket_ok / n_cov, 4),
            "stars": stars_ok, "pct_stars": round(100.0 * stars_ok / n_cov, 4),
            "both": both_ok, "pct_both": round(100.0 * both_ok / n_cov, 4)},
        "confusion": [{"actual": a, "reconstructed": r, "n": n_} for a, r, n_ in conf],
        "star_drift": [{"delta": d, "n": n_} for d, n_ in drift],
        "cohort": {
            "real": real_cohort, "covered": covered_cohort,
            "recovered_as_vus": recovered_vus,
            "recovered_with_criteria": recovered_cohort,
            "pct_recovered_with_criteria": round(
                100.0 * recovered_cohort / real_cohort, 4)},
    }
    path = os.path.join(RESULTS, f"_reconstruction_validation_{args.label}.json")
    with open(path, "w") as fh:
        json.dump(out, fh, indent=2)
    print(f"\nwrote {path}")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
