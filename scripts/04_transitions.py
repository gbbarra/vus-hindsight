#!/usr/bin/env python3
"""Count VUS -> definitive-classification transitions between two ClinVar snapshots.

Streams both gzipped snapshots through DuckDB's read_csv (never pandas, never a
full in-memory load), filters to GRCh38, deduplicates on VariationID, and emits:

  * the baseline -> current transition table
  * for the VUS -> P/LP arm: consequence breakdown, review-status breakdown,
    distinct gene count, and the missense AND >=2-star stratum
  * results/_counts_<label>.json   (machine-readable, consumed by 06_report.py)
  * results/reclassified_pathogenic.tsv rows for this baseline

Usage:
  04_transitions.py --baseline data/variant_summary_2021-06.txt.gz \
                    --current  data/variant_summary.txt.gz \
                    --label    2021-06
"""
import argparse
import csv
import json
import os
import sys

import duckdb

from snapshot import load_snapshot

RESULTS = "results"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--current", required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--consequence-map", required=True,
                    help="parquet from 03b_extract_mc.py (VCF MC field)")
    ap.add_argument("--memory-limit", default="6GB")
    ap.add_argument("--temp-dir", default="data/duckdb_tmp")
    args = ap.parse_args()

    os.makedirs(RESULTS, exist_ok=True)
    os.makedirs(args.temp_dir, exist_ok=True)

    con = duckdb.connect()
    con.execute(f"PRAGMA memory_limit='{args.memory_limit}'")
    con.execute(f"PRAGMA temp_directory='{args.temp_dir}'")

    meta = {"label": args.label,
            "baseline_file": os.path.basename(args.baseline),
            "current_file": os.path.basename(args.current)}
    meta["baseline"] = load_snapshot(con, "base", args.baseline, f"baseline {args.label}")
    meta["current"] = load_snapshot(con, "cur", args.current, "current")

    # Baseline VUS cohort: uncertain at baseline, with assertion criteria.
    con.execute("""
        CREATE OR REPLACE TABLE vus_base AS
        SELECT * FROM base
        WHERE bucket = 'Still VUS' AND stars >= 1
    """)
    n_vus = con.execute("SELECT count(*) FROM vus_base").fetchone()[0]
    n_vus_excluded = con.execute("""
        SELECT count(*) FROM base WHERE bucket = 'Still VUS' AND stars = 0
    """).fetchone()[0]
    print(f"[{args.label}] baseline VUS (criteria provided): {n_vus:,} "
          f"(excluded {n_vus_excluded:,} with no assertion criteria)")
    meta["baseline_vus"] = n_vus
    meta["baseline_vus_excluded_no_criteria"] = n_vus_excluded

    # Molecular consequence comes from the ClinVar VCF MC field, not from HGVS.
    if not os.path.exists(args.consequence_map):
        raise SystemExit(
            f"FATAL: consequence map {args.consequence_map!r} not found. "
            "Run scripts/03b_extract_mc.py against the ClinVar VCF first — "
            "consequence is sourced from the VCF, never inferred here.")
    con.execute(f"""
        CREATE OR REPLACE TABLE cons AS
        SELECT * FROM read_parquet('{args.consequence_map}')
    """)
    n_cons = con.execute("SELECT count(*) FROM cons").fetchone()[0]
    print(f"consequence map: {n_cons:,} VariationIDs from "
          f"{os.path.basename(args.consequence_map)}")
    meta["consequence_map_rows"] = n_cons

    # Follow each baseline VUS into the current snapshot.
    # 'not_in_vcf' is kept as its own bucket rather than folded into 'other',
    # so unmatched variants are visible instead of silently miscounted.
    con.execute("""
        CREATE OR REPLACE TABLE followed AS
        SELECT b.variation_id,
               coalesce(c.gene, b.gene)   AS gene,
               coalesce(c.hgvs, b.hgvs)   AS hgvs,
               coalesce(m.consequence, 'not_in_vcf') AS consequence,
               m.mc_raw                   AS mc_raw,
               coalesce(c.hgvs_consequence, b.hgvs_consequence) AS hgvs_consequence,
               b.raw_class  AS baseline_class,
               b.raw_review AS baseline_review,
               c.raw_class  AS current_class,
               c.raw_review AS current_review,
               c.stars      AS current_stars,
               CASE WHEN c.variation_id IS NULL THEN 'Retired/absent'
                    ELSE c.bucket END AS current_bucket
        FROM vus_base b
        LEFT JOIN cur c USING (variation_id)
        LEFT JOIN cons m USING (variation_id)
    """)

    rows = con.execute("""
        SELECT current_bucket, count(*) AS n
        FROM followed GROUP BY 1 ORDER BY n DESC
    """).fetchall()
    print(f"\n=== [{args.label}] transition table ===")
    for bucket, n in rows:
        print(f"  {bucket:16s} {n:>10,}  {100.0 * n / n_vus:5.2f}%")
    meta["transitions"] = [{"current_bucket": b, "n": n,
                            "pct": round(100.0 * n / n_vus, 4)} for b, n in rows]

    # --- VUS -> P/LP arm ------------------------------------------------------
    plp_n = con.execute(
        "SELECT count(*) FROM followed WHERE current_bucket = 'P/LP'").fetchone()[0]
    genes = con.execute("""
        SELECT count(DISTINCT gene) FROM followed
        WHERE current_bucket = 'P/LP' AND gene IS NOT NULL AND gene NOT IN ('','-')
    """).fetchone()[0]
    meta["vus_to_plp"] = plp_n
    meta["vus_to_plp_distinct_genes"] = genes
    print(f"\n=== [{args.label}] VUS -> P/LP: {plp_n:,} variants, "
          f"{genes:,} distinct genes ===")

    by_cons = con.execute("""
        SELECT consequence, count(*) n FROM followed
        WHERE current_bucket = 'P/LP' GROUP BY 1 ORDER BY n DESC
    """).fetchall()
    print("  by molecular consequence (source: ClinVar VCF MC field):")
    for c, n in by_cons:
        print(f"    {c:12s} {n:>9,}")
    meta["vus_to_plp_by_consequence"] = [{"consequence": c, "n": n} for c, n in by_cons]

    not_in_vcf = con.execute("""
        SELECT count(*) FROM followed
        WHERE current_bucket = 'P/LP' AND consequence = 'not_in_vcf'
    """).fetchone()[0]
    meta["vus_to_plp_not_in_vcf"] = not_in_vcf
    if plp_n:
        print(f"    ({not_in_vcf:,} of {plp_n:,} have no VCF record — "
              f"{100.0 * not_in_vcf / plp_n:.2f}% — reported separately, "
              "not folded into 'other')")

    # Diagnostic only: agreement between the VCF MC term and an independent
    # derivation from HGVS. Not used for any published count.
    conc = con.execute("""
        SELECT
          count(*) FILTER (WHERE consequence <> 'not_in_vcf')                        AS matched,
          count(*) FILTER (WHERE consequence <> 'not_in_vcf'
                             AND consequence = hgvs_consequence)                     AS agree
        FROM followed WHERE current_bucket = 'P/LP'
    """).fetchone()
    matched, agree = conc
    meta["consequence_concordance"] = {
        "matched": matched, "agree": agree,
        "pct": round(100.0 * agree / matched, 4) if matched else None}
    if matched:
        print(f"  cross-check vs HGVS derivation: {agree:,}/{matched:,} agree "
              f"({100.0 * agree / matched:.2f}%) — diagnostic only")

    by_rev = con.execute("""
        SELECT current_review, current_stars, count(*) n FROM followed
        WHERE current_bucket = 'P/LP' GROUP BY 1,2 ORDER BY n DESC
    """).fetchall()
    print("  by current review status:")
    for r, s, n in by_rev:
        print(f"    [{s}*] {str(r):55s} {n:>9,}")
    meta["vus_to_plp_by_review"] = [
        {"review_status": r, "stars": s, "n": n} for r, s, n in by_rev]

    # The hard stratum: missense AND >= "criteria provided, multiple submitters".
    hard = con.execute("""
        SELECT count(*) FROM followed
        WHERE current_bucket = 'P/LP' AND consequence = 'missense' AND current_stars >= 2
    """).fetchone()[0]
    hard_genes = con.execute("""
        SELECT count(DISTINCT gene) FROM followed
        WHERE current_bucket = 'P/LP' AND consequence = 'missense' AND current_stars >= 2
          AND gene IS NOT NULL AND gene NOT IN ('','-')
    """).fetchone()[0]
    meta["vus_to_plp_missense_2star_plus"] = hard
    meta["vus_to_plp_missense_2star_plus_genes"] = hard_genes
    print(f"\n  HARD STRATUM (missense AND >=2-star): {hard:,} variants "
          f"across {hard_genes:,} genes")

    # --- Per-variant output ---------------------------------------------------
    out_tsv = os.path.join(RESULTS, "reclassified_pathogenic.tsv")
    write_header = not os.path.exists(out_tsv)
    cur = con.execute("""
        SELECT variation_id, gene, hgvs, consequence, mc_raw,
               baseline_class, current_class, current_review
        FROM followed WHERE current_bucket = 'P/LP'
        ORDER BY variation_id
    """)
    n_written = 0
    with open(out_tsv, "a", newline="") as fh:
        w = csv.writer(fh, delimiter="\t", lineterminator="\n")
        if write_header:
            w.writerow(["baseline", "VariationID", "gene", "HGVS", "consequence",
                        "mc_raw", "baseline_class", "current_class", "review_status"])
        while True:
            batch = cur.fetchmany(50_000)
            if not batch:
                break
            for row in batch:
                w.writerow([args.label] + list(row))
                n_written += 1
    print(f"\n  wrote {n_written:,} rows -> {out_tsv}")
    meta["tsv_rows_written"] = n_written

    with open(os.path.join(RESULTS, f"_counts_{args.label}.json"), "w") as fh:
        json.dump(meta, fh, indent=2)
    print(f"  wrote results/_counts_{args.label}.json")
    con.close()


if __name__ == "__main__":
    main()
