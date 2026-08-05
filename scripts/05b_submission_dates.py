#!/usr/bin/env python3
"""Quantify per-submission date coverage in ClinVar's submission_summary.

The question this answers: does submission_summary carry dates good enough to
reconstruct the evidence available at a frozen past date?

The file has one row per SCV (per submission, not per variant) and carries
DateLastEvaluated. That column is what a frozen-date reconstruction would key
on, so its *coverage* decides whether the approach is viable — a column that is
frequently '-' cannot support it. This reports the real fraction.

Important caveat, reported alongside the numbers: DateLastEvaluated is the date
the SUBMITTER last evaluated the record, not the date ClinVar published it. A
record evaluated in 2019 may have reached ClinVar years later, so filtering on
this date is an upper bound on what was publicly knowable, not an exact replay.

Usage: 05b_submission_dates.py data/submission_summary.txt.gz
"""

import argparse
import json
import os
import sys

import duckdb

LINE_DELIM = "\x01"
RESULTS = "results"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--memory-limit", default="6GB")
    ap.add_argument("--temp-dir", default="data/duckdb_tmp")
    ap.add_argument(
        "--reclassified",
        default="results/reclassified_pathogenic.tsv",
        help="optional; restricts a second report to the VUS->P/LP set",
    )
    args = ap.parse_args()

    os.makedirs(args.temp_dir, exist_ok=True)
    os.makedirs(RESULTS, exist_ok=True)

    con = duckdb.connect()
    con.execute(f"PRAGMA memory_limit='{args.memory_limit}'")
    con.execute(f"PRAGMA temp_directory='{args.temp_dir}'")

    reader = (
        f"read_csv('{args.path}', delim='{LINE_DELIM}', header=false, "
        f"columns={{'line': 'VARCHAR'}}, quote='', escape='', ignore_errors=false)"
    )
    con.execute(f"""
        CREATE OR REPLACE TABLE subs AS
        SELECT
            TRY_CAST(split_part(line, chr(9), 1) AS BIGINT) AS variation_id,
            split_part(line, chr(9), 3)                     AS date_last_evaluated,
            split_part(line, chr(9), 7)                     AS review_status,
            split_part(line, chr(9), 11)                    AS scv
        FROM {reader}
        WHERE line NOT LIKE '#%'
    """)

    total = con.execute("SELECT count(*) FROM subs").fetchone()[0]
    if total == 0:
        print(
            "FATAL: no submission rows parsed — inspect the file layout.",
            file=sys.stderr,
        )
        return 1

    row = con.execute("""
        SELECT
          count(*)                                                        AS rows_total,
          count(DISTINCT variation_id)                                    AS variants,
          count(DISTINCT scv)                                             AS submissions,
          count(*) FILTER (WHERE date_last_evaluated NOT IN ('-', '', 'na')) AS dated
        FROM subs
    """).fetchone()
    rows_total, variants, submissions, dated = row
    pct = 100.0 * dated / rows_total

    print(f"submission rows (one per SCV): {rows_total:,}")
    print(f"distinct VariationIDs:         {variants:,}")
    print(f"distinct SCV accessions:       {submissions:,}")
    print(f"rows with a DateLastEvaluated: {dated:,} ({pct:.2f}%)")
    print(f"rows with no usable date:      {rows_total - dated:,} ({100.0 - pct:.2f}%)")

    print("\nDateLastEvaluated by year:")
    years = con.execute("""
        SELECT regexp_extract(date_last_evaluated, '(\\d{4})', 1) AS yr, count(*) n
        FROM subs
        WHERE date_last_evaluated NOT IN ('-', '', 'na')
        GROUP BY 1 HAVING yr <> '' ORDER BY yr
    """).fetchall()
    for yr, n in years:
        print(f"  {yr}  {n:>10,}")

    stats = {
        "file": os.path.basename(args.path),
        "submission_rows": rows_total,
        "distinct_variation_ids": variants,
        "distinct_scv": submissions,
        "rows_with_date": dated,
        "pct_with_date": round(pct, 4),
        "by_year": [{"year": y, "n": n} for y, n in years],
        "caveat": (
            "DateLastEvaluated is the submitter's evaluation date, not the "
            "ClinVar publication date; filtering on it bounds what was "
            "knowable rather than replaying what was public."
        ),
    }

    # If the reclassified set is present, report coverage on it specifically —
    # that is the cohort a frozen-date reconstruction would actually run on.
    if os.path.exists(args.reclassified):
        con.execute(f"""
            CREATE OR REPLACE TABLE recl AS
            SELECT DISTINCT TRY_CAST(VariationID AS BIGINT) AS variation_id
            FROM read_csv('{args.reclassified}', delim='\\t', header=true,
                          all_varchar=true, quote='', escape='')
        """)
        r = con.execute("""
            SELECT
              (SELECT count(*) FROM recl)                                   AS n_recl,
              count(DISTINCT s.variation_id)                                AS matched,
              count(DISTINCT s.variation_id) FILTER (
                  WHERE s.date_last_evaluated NOT IN ('-', '', 'na'))       AS with_date
            FROM subs s
            WHERE s.variation_id IN (SELECT variation_id FROM recl)
        """).fetchone()
        n_recl, matched, with_date = r
        print(f"\nVUS -> P/LP cohort ({n_recl:,} distinct variants):")
        print(f"  present in submission_summary:        {matched:,}")
        print(
            f"  with >=1 dated submission:            {with_date:,} "
            f"({100.0 * with_date / n_recl:.2f}% of the cohort)"
        )
        stats["reclassified_cohort"] = {
            "distinct_variants": n_recl,
            "present": matched,
            "with_dated_submission": with_date,
            "pct_with_dated_submission": round(100.0 * with_date / n_recl, 4),
        }

    with open(os.path.join(RESULTS, "_submission_dates.json"), "w") as fh:
        json.dump(stats, fh, indent=2)
    print("\nwrote results/_submission_dates.json")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
