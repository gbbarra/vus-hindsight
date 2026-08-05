#!/usr/bin/env python3
"""Extract the molecular-consequence map from the ClinVar VCF's MC field.

The VCF's ID column is the ClinVar VariationID, which is the join key back to
variant_summary. INFO carries MC=SO:0001583|missense_variant[,...].

Streams the gzipped VCF through DuckDB one line at a time (the file is read with
a delimiter that cannot occur in it, so each line arrives as a single field and
the ## meta lines never cause a column-count mismatch). Writes
data/consequence_map.parquet with one row per VariationID.

Fails loudly rather than degrading: if no MC field is present at all, or if
essentially nothing parses, it exits non-zero instead of returning a map full of
'other'.

Usage: 03b_extract_mc.py data/clinvar.vcf.gz [--out data/consequence_map.parquet]
"""
import argparse
import json
import os
import sys

import duckdb
from schema import mc_bucket_sql

# A byte that cannot appear in a VCF text line, so read_csv yields whole lines.
LINE_DELIM = "\x01"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("vcf")
    ap.add_argument("--out", default="data/consequence_map.parquet")
    ap.add_argument("--memory-limit", default="6GB")
    ap.add_argument("--temp-dir", default="data/duckdb_tmp")
    args = ap.parse_args()

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    os.makedirs(args.temp_dir, exist_ok=True)

    con = duckdb.connect()
    con.execute(f"PRAGMA memory_limit='{args.memory_limit}'")
    con.execute(f"PRAGMA temp_directory='{args.temp_dir}'")

    reader = (
        f"read_csv('{args.vcf}', delim='{LINE_DELIM}', header=false, "
        f"columns={{'line': 'VARCHAR'}}, quote='', escape='', ignore_errors=false)"
    )

    con.execute(f"""
        CREATE OR REPLACE TABLE vcf_rows AS
        SELECT
            TRY_CAST(split_part(line, chr(9), 3) AS BIGINT) AS variation_id,
            split_part(line, chr(9), 8)                     AS info
        FROM {reader}
        WHERE line NOT LIKE '#%'
    """)
    n_rows = con.execute("SELECT count(*) FROM vcf_rows").fetchone()[0]
    n_ids = con.execute(
        "SELECT count(*) FROM vcf_rows WHERE variation_id IS NOT NULL").fetchone()[0]
    print(f"VCF data lines: {n_rows:,}; with a numeric ID (VariationID): {n_ids:,}")
    if n_ids == 0:
        print("FATAL: no numeric IDs parsed from the VCF ID column. The VCF layout "
              "is not what this script expects — inspect the file before trusting "
              "any downstream count.", file=sys.stderr)
        return 1

    con.execute(f"""
        CREATE OR REPLACE TABLE consequence_map AS
        SELECT variation_id,
               mc_raw,
               {mc_bucket_sql('mc_raw')} AS consequence
        FROM (
            SELECT variation_id,
                   regexp_extract(info, '(^|;)MC=([^;]*)', 2) AS mc_raw
            FROM vcf_rows
            WHERE variation_id IS NOT NULL
            QUALIFY row_number() OVER (PARTITION BY variation_id ORDER BY info) = 1
        )
    """)

    n_map = con.execute("SELECT count(*) FROM consequence_map").fetchone()[0]
    n_with_mc = con.execute(
        "SELECT count(*) FROM consequence_map WHERE mc_raw <> ''").fetchone()[0]
    print(f"VariationIDs in map: {n_map:,}; carrying an MC field: {n_with_mc:,} "
          f"({100.0 * n_with_mc / n_map:.2f}%)")
    if n_with_mc == 0:
        print("FATAL: the VCF carries no MC= field. Consequence cannot be sourced "
              "from it. Stop — do not fall back silently.", file=sys.stderr)
        return 1

    print("\nconsequence distribution across the whole VCF:")
    for cons, n in con.execute("""
            SELECT consequence, count(*) n FROM consequence_map
            GROUP BY 1 ORDER BY n DESC""").fetchall():
        print(f"  {cons:12s} {n:>10,}")

    # Make the 'other' bucket auditable: show which SO terms landed there.
    print("\ntop SO terms falling into 'other' (audit for anything miscategorised):")
    other_terms = con.execute("""
        SELECT term, count(*) n FROM (
            SELECT unnest(string_split(mc_raw, ',')) AS term
            FROM consequence_map WHERE consequence = 'other' AND mc_raw <> ''
        ) GROUP BY 1 ORDER BY n DESC LIMIT 25
    """).fetchall()
    for term, n in other_terms:
        print(f"  {term:55s} {n:>10,}")

    con.execute(f"COPY consequence_map TO '{args.out}' (FORMAT parquet)")
    print(f"\nwrote {args.out}")

    stats = {
        "vcf_file": os.path.basename(args.vcf),
        "vcf_data_lines": n_rows,
        "variation_ids": n_map,
        "with_mc_field": n_with_mc,
        "other_bucket_top_terms": [{"term": t, "n": n} for t, n in other_terms],
    }
    with open(os.path.join("results", "_vcf_mc_stats.json"), "w") as fh:
        json.dump(stats, fh, indent=2)
    print("wrote results/_vcf_mc_stats.json")
    con.close()
    return 0


if __name__ == "__main__":
    os.makedirs("results", exist_ok=True)
    sys.exit(main())
