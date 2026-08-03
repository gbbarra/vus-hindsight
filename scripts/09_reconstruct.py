#!/usr/bin/env python3
"""Reconstruct ClinVar's aggregate classification as it would have stood at a past date.

Reads submission_summary.txt.gz, keeps only submissions evaluated on or before
`--as-of`, and re-aggregates them into a per-variant classification and review
status using the rules in aggregate.py.

This is the machinery a properly time-blinded benchmark needs: without it,
"the variant was a VUS in 2021" is known but "what evidence supported that in
2021" is not, and a method evaluated on the cohort can be fed post-baseline
information without anyone noticing.

Usage:
  09_reconstruct.py --submissions data/submission_summary.txt.gz \
                    --as-of 2021-06-03 --out data/reconstructed_2021-06.parquet
"""
import argparse
import json
import os
import sys

import duckdb

from aggregate import DATE_PARSE, reconstruct_sql

LINE_DELIM = "\x01"
RESULTS = "results"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--submissions", required=True)
    ap.add_argument("--as-of", required=True, help="YYYY-MM-DD")
    ap.add_argument("--out", required=True)
    ap.add_argument("--memory-limit", default="6GB")
    ap.add_argument("--temp-dir", default="data/duckdb_tmp")
    args = ap.parse_args()

    os.makedirs(args.temp_dir, exist_ok=True)
    os.makedirs(RESULTS, exist_ok=True)

    con = duckdb.connect()
    con.execute(f"PRAGMA memory_limit='{args.memory_limit}'")
    con.execute(f"PRAGMA temp_directory='{args.temp_dir}'")

    reader = (
        f"read_csv('{args.submissions}', delim='{LINE_DELIM}', header=false, "
        f"columns={{'line': 'VARCHAR'}}, quote='', escape='', ignore_errors=false)"
    )
    # Column order is fixed by ClinVar's documented layout, printed into the run
    # log by 05_submission_summary_probe.sh before this ever executes.
    con.execute(f"""
        CREATE OR REPLACE TABLE subs AS
        SELECT
            TRY_CAST(split_part(line, chr(9), 1) AS BIGINT) AS variation_id,
            split_part(line, chr(9), 2)  AS scv_class,
            split_part(line, chr(9), 3)  AS date_last_evaluated,
            split_part(line, chr(9), 7)  AS scv_review,
            split_part(line, chr(9), 10) AS submitter,
            split_part(line, chr(9), 11) AS scv,
            split_part(line, chr(9), 16) AS contributes
        FROM {reader}
        WHERE line NOT LIKE '#%'
    """)
    total = con.execute("SELECT count(*) FROM subs").fetchone()[0]
    if total == 0:
        print("FATAL: no submission rows parsed — inspect the file layout.",
              file=sys.stderr)
        return 1

    stats = con.execute(f"""
        SELECT
          count(*)                                                       AS rows_total,
          count(*) FILTER (WHERE lower(trim(contributes)) = 'yes')        AS contributing,
          count(*) FILTER (WHERE {DATE_PARSE} IS NOT NULL)                AS dated,
          count(*) FILTER (WHERE lower(trim(contributes)) = 'yes'
                             AND {DATE_PARSE} IS NOT NULL
                             AND {DATE_PARSE} <= DATE '{args.as_of}')     AS eligible,
          count(DISTINCT variation_id)                                    AS variants_total
        FROM subs
    """).fetchone()
    rows_total, contributing, dated, eligible, variants_total = stats
    print(f"submission rows            : {rows_total:,}")
    print(f"  contributing to aggregate: {contributing:,} "
          f"({100.0 * contributing / rows_total:.2f}%)")
    print(f"  with a parseable date    : {dated:,} "
          f"({100.0 * dated / rows_total:.2f}%)")
    print(f"  eligible as of {args.as_of}: {eligible:,}")
    print(f"distinct VariationIDs      : {variants_total:,}")

    if dated == 0:
        print("FATAL: no DateLastEvaluated parsed. The date format changed — "
              "fix aggregate.DATE_PARSE rather than proceeding.", file=sys.stderr)
        return 1

    con.execute(f"""
        CREATE OR REPLACE TABLE reconstructed AS {reconstruct_sql(args.as_of)}
    """)
    n = con.execute("SELECT count(*) FROM reconstructed").fetchone()[0]
    print(f"\nreconstructed variants as of {args.as_of}: {n:,}")

    print("\nreconstructed review-status distribution:")
    for r, s, c in con.execute("""
            SELECT review_status, stars, count(*) n FROM reconstructed
            GROUP BY 1,2 ORDER BY n DESC""").fetchall():
        print(f"  [{s}*] {r:55s} {c:>9,}")

    print("\nreconstructed classification distribution (top 12):")
    for c, n_ in con.execute("""
            SELECT classification, count(*) n FROM reconstructed
            GROUP BY 1 ORDER BY n DESC LIMIT 12""").fetchall():
        print(f"  {c:55s} {n_:>9,}")

    con.execute(f"COPY reconstructed TO '{args.out}' (FORMAT parquet)")
    print(f"\nwrote {args.out}")

    with open(os.path.join(RESULTS, f"_reconstruction_{args.as_of}.json"), "w") as fh:
        json.dump({"as_of": args.as_of,
                   "submissions_file": os.path.basename(args.submissions),
                   "submission_rows": rows_total,
                   "contributing": contributing,
                   "dated": dated,
                   "eligible_as_of": eligible,
                   "variants_reconstructed": n}, fh, indent=2)
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
