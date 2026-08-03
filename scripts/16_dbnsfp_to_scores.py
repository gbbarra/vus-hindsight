#!/usr/bin/env python3
"""Turn a dbNSFP slice into per-predictor score files keyed on this benchmark's ID.

`15_evaluate.py` wants two columns per predictor: `variant_id_hg38` and a score.
dbNSFP ships one enormous TSV per chromosome with coordinates in four separate
columns and forty predictors side by side. This bridges the two.

THE BUILD IS THE WHOLE PROBLEM. dbNSFP carries both assemblies, and which pair
of columns holds GRCh38 depends on the major version:

  dbNSFP 4.x / 5.x   `#chr` + `pos(1-based)` are GRCh38; GRCh37 sits in
                     `hg19_chr` + `hg19_pos(1-based)`
  dbNSFP 3.x         the reverse — the main columns are GRCh37 and GRCh38 sits
                     in `hg38_chr` + `hg38_pos(1-based)`

Reading the wrong pair produces IDs that join to nothing. An empty join looks
exactly like "this predictor does not cover the cohort", which is a quiet wrong
answer rather than a loud one. So the layout is DETECTED from which alias column
is present, and a run that resolves to neither layout, or that joins to zero
cohort variants, stops instead of writing empty files.

RANKSCORES BY DEFAULT. dbNSFP publishes `*_rankscore` / `*_converted_rankscore`
alongside every raw score, already oriented so that larger is more damaging —
the `converted_` prefix marks exactly those tools whose raw score runs the other
way. Since AUROC and AUPRC depend only on ranking, and a rankscore is a monotone
transform of its raw score, using them changes no metric this benchmark reports
while removing the one error that would silently inverting every number: getting
a sign backwards. `--raw` is there for when the raw values are wanted for their
own sake.

Usage:
  16_dbnsfp_to_scores.py --peek 'data/dbNSFP5.1a_variant.chr1.gz'
  16_dbnsfp_to_scores.py --dbnsfp 'data/dbNSFP5.1a_variant.chr*.gz' \
      --export data/exports/vus_hindsight_for_am_join.csv --out-dir data/scores
"""
import argparse
import json
import os
import sys

import duckdb

RESULTS = "results"

# Column aliases across dbNSFP versions. `raw_direction` is the orientation of
# the RAW score and is taken from each tool's own publication — the same sources
# recorded in predictors.yaml. Rankscore columns are always `high` by dbNSFP's
# own convention, which is why they are the default.
PREDICTORS = [
    {"name": "SIFT", "slug": "sift",
     "raw": ["SIFT_score"],
     "rank": ["SIFT_converted_rankscore"],
     "raw_direction": "low", "agg": "min",
     "note": "0 = damaging, 1 = tolerated; damaging calls are < 0.05."},
    {"name": "PolyPhen-2_HumDiv", "slug": "polyphen2_hdiv",
     "raw": ["Polyphen2_HDIV_score"],
     "rank": ["Polyphen2_HDIV_rankscore"],
     "raw_direction": "high", "agg": "max",
     "note": "0..1, higher = more probably damaging."},
    {"name": "PolyPhen-2_HumVar", "slug": "polyphen2_hvar",
     "raw": ["Polyphen2_HVAR_score"],
     "rank": ["Polyphen2_HVAR_rankscore"],
     "raw_direction": "high", "agg": "max",
     "note": "0..1, higher = more probably damaging."},
    {"name": "FATHMM", "slug": "fathmm",
     "raw": ["FATHMM_score"],
     "rank": ["FATHMM_converted_rankscore"],
     "raw_direction": "low", "agg": "min",
     "note": "negative = damaging; the usual call threshold is <= -1.5."},
    {"name": "PROVEAN", "slug": "provean",
     "raw": ["PROVEAN_score"],
     "rank": ["PROVEAN_converted_rankscore"],
     "raw_direction": "low", "agg": "min",
     "note": "negative = deleterious; the published cutoff is <= -2.5. Use the "
             "continuous score: the cutoff itself was fitted on labels."},
    {"name": "MutationAssessor", "slug": "mutationassessor",
     "raw": ["MutationAssessor_score", "MutationAssessor_score_rankscore"],
     "rank": ["MutationAssessor_rankscore"],
     "raw_direction": "high", "agg": "max",
     "note": "higher = more functionally significant."},
    # Present only in recent dbNSFP builds. Discovery decides; nothing is
    # assumed about whether your copy carries them.
    {"name": "EVE", "slug": "eve",
     "raw": ["EVE_score"],
     "rank": ["EVE_rankscore"],
     "raw_direction": "high", "agg": "max",
     "note": "0..1, higher = more pathogenic. Only in dbNSFP 4.4a and later; "
             "coverage is limited to the ~3,200 genes EVE published."},
    {"name": "ESM-1b", "slug": "esm1b",
     "raw": ["ESM1b_score"],
     "rank": ["ESM1b_rankscore"],
     "raw_direction": "low", "agg": "min",
     "note": "a log-likelihood ratio, so more NEGATIVE = more damaging. Check "
             "the printed score range: if the values are not mostly negative, "
             "your build ships something other than the raw LLR and the "
             "direction must be re-derived before use."},
]


def q(name):
    """Quote a dbNSFP column name — they contain '#', '(' and '-'."""
    return '"' + name.replace('"', '""') + '"'


def header_of(con, path):
    rows = con.execute(f"""
        DESCRIBE SELECT * FROM read_csv('{path}', delim='\t', header=true,
            all_varchar=true, sample_size=1)
    """).fetchall()
    return [r[0] for r in rows]


def resolve(cols, aliases):
    lower = {c.lower(): c for c in cols}
    for a in aliases:
        if a.lower() in lower:
            return lower[a.lower()]
    return None


def coordinate_columns(cols, args):
    """Which pair of columns holds GRCh38, decided from the file's own layout."""
    if args.hg38_chr_col or args.hg38_pos_col:
        if not (args.hg38_chr_col and args.hg38_pos_col):
            return None, None, "both --hg38-chr-col and --hg38-pos-col are needed"
        for c in (args.hg38_chr_col, args.hg38_pos_col):
            if c not in cols:
                return None, None, f"column {c!r} is not in the file"
        return args.hg38_chr_col, args.hg38_pos_col, "explicitly given on the command line"

    main_chr = resolve(cols, ["#chr", "chr"])
    main_pos = resolve(cols, ["pos(1-based)", "pos"])
    hg19_chr = resolve(cols, ["hg19_chr"])
    hg38_chr = resolve(cols, ["hg38_chr"])
    hg38_pos = resolve(cols, ["hg38_pos(1-based)", "hg38_pos"])

    if hg19_chr and main_chr and main_pos:
        return main_chr, main_pos, (
            f"`hg19_chr` is present, so this is the dbNSFP 4.x/5.x layout and "
            f"`{main_chr}` + `{main_pos}` are GRCh38")
    if hg38_chr and hg38_pos:
        return hg38_chr, hg38_pos, (
            "`hg38_chr` is present, so this is the dbNSFP 3.x layout and GRCh38 "
            "lives in the aliased columns")
    return None, None, (
        "neither `hg19_chr` nor `hg38_chr` is present, so which columns hold "
        "GRCh38 cannot be established from the file")


def agg_expr(col, how):
    """Collapse dbNSFP's per-transcript ';'-separated values to one number."""
    parts = (f"list_filter(list_transform(str_split(COALESCE({q(col)}, ''), ';'),"
             f" x -> TRY_CAST(x AS DOUBLE)), x -> x IS NOT NULL)")
    return {"min": f"list_min({parts})", "max": f"list_max({parts})",
            "mean": f"list_avg({parts})"}[how]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dbnsfp", help="path or glob of dbNSFP variant files")
    ap.add_argument("--peek", help="print the header of this file and stop")
    ap.add_argument("--export", default="data/exports/vus_hindsight_for_am_join.csv")
    ap.add_argument("--out-dir", default="data/scores")
    ap.add_argument("--raw", action="store_true",
                    help="emit raw scores instead of dbNSFP rankscores")
    ap.add_argument("--aggregate", default="damaging",
                    choices=["damaging", "mean"],
                    help="how to collapse per-transcript raw values (--raw only)")
    ap.add_argument("--only", help="comma-separated predictor names to emit")
    ap.add_argument("--hg38-chr-col",
                    help="override detection: column holding the GRCh38 chromosome")
    ap.add_argument("--hg38-pos-col",
                    help="override detection: column holding the GRCh38 position")
    ap.add_argument("--memory-limit", default="6GB")
    ap.add_argument("--temp-dir", default="data/duckdb_tmp")
    args = ap.parse_args()

    con = duckdb.connect()
    if args.peek:
        cols = header_of(con, args.peek)
        print(f"{len(cols)} columns in {args.peek}\n")
        for i, c in enumerate(cols, 1):
            print(f"  {i:3d}  {c}")
        chr_col, pos_col, why = coordinate_columns(cols, args)
        print(f"\nGRCh38 coordinates: "
              f"{chr_col + ' + ' + pos_col if chr_col else 'NOT RESOLVED'}")
        print(f"  {why}")
        print("\npredictor columns present:")
        for p in PREDICTORS:
            raw = resolve(cols, p["raw"])
            rank = resolve(cols, p["rank"])
            print(f"  {p['name']:20s} raw={raw or '—':32s} rank={rank or '—'}")
        return 0

    if not args.dbnsfp:
        print("FATAL: --dbnsfp is required (or --peek to inspect a file)",
              file=sys.stderr)
        return 1
    if not os.path.exists(args.export):
        print(f"FATAL: {args.export} not found", file=sys.stderr)
        return 1

    os.makedirs(args.out_dir, exist_ok=True)
    os.makedirs(args.temp_dir, exist_ok=True)
    os.makedirs(RESULTS, exist_ok=True)
    con.execute(f"SET memory_limit='{args.memory_limit}'")
    con.execute(f"SET temp_directory='{args.temp_dir}'")

    # --- resolve the file's layout before touching a single data row ----------
    cols = header_of(con, args.dbnsfp)
    print(f"dbNSFP: {args.dbnsfp}")
    print(f"  {len(cols)} columns")

    chr_col, pos_col, why = coordinate_columns(cols, args)
    if not chr_col:
        print(f"\nFATAL: {why}.\n"
              "Refusing to guess. A wrong coordinate pair yields IDs that join "
              "to nothing, which is indistinguishable from a predictor that "
              "simply does not cover the cohort. Run --peek to see the header, "
              "then pass --hg38-chr-col / --hg38-pos-col explicitly.",
              file=sys.stderr)
        return 1
    print(f"  GRCh38 from {chr_col} + {pos_col}\n    ({why})")

    ref_col = resolve(cols, ["ref"])
    alt_col = resolve(cols, ["alt"])
    if not ref_col or not alt_col:
        print("FATAL: no `ref`/`alt` columns in this file", file=sys.stderr)
        return 1

    wanted = None
    if args.only:
        wanted = {s.strip().lower() for s in args.only.split(",")}

    chosen, missing = [], []
    for p in PREDICTORS:
        if wanted and p["name"].lower() not in wanted and p["slug"] not in wanted:
            continue
        col = resolve(cols, p["raw"] if args.raw else p["rank"])
        if not col:
            missing.append(p["name"])
            continue
        how = ({"damaging": p["agg"], "mean": "mean"}[args.aggregate]
               if args.raw else "max")
        chosen.append({**p, "column": col, "how": how,
                       "direction": p["raw_direction"] if args.raw else "high"})

    print(f"\n  {'raw scores' if args.raw else 'rankscores (higher = more damaging)'}")
    for c in chosen:
        print(f"    {c['name']:20s} <- {c['column']}  ({c['direction']})")
    if missing:
        print("  not in this build: " + ", ".join(missing))
    if not chosen:
        print("\nFATAL: none of the known predictor columns are in this file",
              file=sys.stderr)
        return 1

    # --- cohort ---------------------------------------------------------------
    con.execute(f"""
        CREATE TABLE cohort AS
        SELECT DISTINCT variant_id_hg38, arm, molecular_consequence
        FROM read_csv('{args.export}', header=true, all_varchar=true)
    """)
    n_cohort = con.execute("SELECT count(*) FROM cohort").fetchone()[0]
    print(f"\ncohort: {n_cohort:,} variants")

    # --- one pass over dbNSFP, semi-joined to the cohort ----------------------
    # dbNSFP is tens of gigabytes; reading it once per predictor is not an
    # option, so every score column comes out of a single scan.
    sel = ",\n               ".join(
        f"{agg_expr(c['column'], c['how'])} AS {c['slug']}" for c in chosen)
    con.execute(f"""
        CREATE TABLE hits AS
        SELECT 'chr' || replace({q(chr_col)}, 'chr', '') || '_' || {q(pos_col)}
                 || '_' || {q(ref_col)} || '_' || {q(alt_col)} || '_hg38'
                 AS variant_id_hg38,
               {sel}
        FROM read_csv('{args.dbnsfp}', delim='\t', header=true,
                      all_varchar=true, nullstr='.')
        WHERE {q(chr_col)} IS NOT NULL AND {q(pos_col)} IS NOT NULL
          AND {q(ref_col)} IS NOT NULL AND {q(alt_col)} IS NOT NULL
    """)
    n_rows = con.execute("SELECT count(*) FROM hits").fetchone()[0]
    n_join = con.execute("""
        SELECT count(*) FROM hits h SEMI JOIN cohort c
        USING (variant_id_hg38)
    """).fetchone()[0]
    print(f"dbNSFP rows read: {n_rows:,}")
    print(f"joined to cohort: {n_join:,}")

    # The same guard 14_overlap_test.py applies, for the same reason: zero
    # overlap here means a broken key far more often than it means a predictor
    # with no coverage, and the two must not be reported the same way.
    if n_join == 0:
        sample_db = [r[0] for r in con.execute(
            "SELECT variant_id_hg38 FROM hits LIMIT 3").fetchall()]
        sample_co = [r[0] for r in con.execute(
            "SELECT variant_id_hg38 FROM cohort LIMIT 3").fetchall()]
        print("\nFATAL: not one dbNSFP variant matched the cohort.\n"
              "That is a key mismatch, not an absence of coverage — the cohort "
              "is drawn from ClinVar GRCh38 and dbNSFP covers essentially every "
              "possible missense change, so a correct join cannot be empty.\n"
              f"  built from dbNSFP : {sample_db}\n"
              f"  expected by cohort: {sample_co}\n"
              "Compare the chromosome naming, the coordinate base, and the "
              "assembly before rerunning.", file=sys.stderr)
        return 1

    # --- write one file per predictor ----------------------------------------
    report, empty = [], []
    for c in chosen:
        out = os.path.join(args.out_dir, f"{c['slug']}.csv")
        n, lo, med, hi = con.execute(f"""
            SELECT count(*), min({c['slug']}), median({c['slug']}), max({c['slug']})
            FROM hits h JOIN cohort co USING (variant_id_hg38)
            WHERE h.{c['slug']} IS NOT NULL
        """).fetchone()
        # A column that exists but holds nothing for this cohort is not a score
        # file with no rows — it is a predictor with no coverage here, and
        # writing an empty file would let it enter the evaluation as if it had.
        if n == 0:
            print(f"\n{c['name']}\n  column {c['column']} is present but empty "
                  f"across the cohort — no file written")
            empty.append({"predictor": c["name"], "column": c["column"]})
            continue
        con.execute(f"""
            COPY (SELECT h.variant_id_hg38, h.{c['slug']} AS score
                  FROM hits h JOIN cohort co USING (variant_id_hg38)
                  WHERE h.{c['slug']} IS NOT NULL
                  ORDER BY h.variant_id_hg38)
            TO '{out}' (FORMAT csv, HEADER)
        """)
        arms = dict(con.execute(f"""
            SELECT co.arm, count(*) FROM hits h JOIN cohort co
            USING (variant_id_hg38) WHERE h.{c['slug']} IS NOT NULL
            GROUP BY 1
        """).fetchall())
        pct = 100.0 * n / n_cohort if n_cohort else 0.0
        print(f"\n{c['name']}")
        print(f"  {out}: {n:,} scored ({pct:.1f}% of cohort)")
        print(f"  range {lo:.4g} .. {hi:.4g}, median {med:.4g}")
        for a, k in sorted(arms.items()):
            print(f"    {a}: {k:,}")
        report.append({"predictor": c["name"], "column": c["column"],
                       "file": out, "direction": c["direction"],
                       "scored": n, "coverage_pct": round(pct, 2),
                       "min": lo, "median": med, "max": hi,
                       "by_arm": arms, "note": c["note"]})

    if not report:
        print("\nFATAL: every resolved column was empty across the cohort",
              file=sys.stderr)
        return 1

    # --- the exact invocation for the evaluator ------------------------------
    specs = [f'--scores "{r["predictor"]}:{r["file"]}:variant_id_hg38:score:'
             f'{r["direction"]}"' for r in report]
    print("\nfeed these to 15_evaluate.py:\n")
    print("python3 scripts/15_evaluate.py \\\n  " + " \\\n  ".join(specs))

    L = ["# dbNSFP conversion\n"]
    L.append(f"Source: `{args.dbnsfp}` — {len(cols)} columns, {n_rows:,} rows "
             f"read, {n_join:,} joined to the {n_cohort:,}-variant cohort.\n")
    L.append(f"GRCh38 coordinates taken from `{chr_col}` + `{pos_col}`: {why}.\n")
    if args.raw:
        L.append("Raw scores, collapsed across transcripts by "
                 f"`{args.aggregate}`. Each predictor's direction is declared "
                 "from its own publication and passed to the evaluator "
                 "explicitly, because inferring it would invert an AUC "
                 "silently.\n")
    else:
        L.append("dbNSFP rankscores rather than raw scores. They are monotone "
                 "transforms of the raw values, so every rank-based metric this "
                 "benchmark reports is unchanged, and they are all oriented the "
                 "same way — which removes the one mistake that would flip a "
                 "result without any visible symptom.\n")
    L.append("| predictor | column | scored | coverage | range | direction |")
    L.append("|---|---|---|---|---|---|")
    for r in report:
        L.append(f"| {r['predictor']} | `{r['column']}` | {r['scored']:,} "
                 f"| {r['coverage_pct']:.1f}% | {r['min']:.4g} … {r['max']:.4g} "
                 f"| {r['direction']} |")
    L.append("")
    if missing:
        L.append("Not present in this dbNSFP build: "
                 + ", ".join(f"**{m}**" for m in missing)
                 + ". Absent is recorded as absent; nothing is substituted.\n")
    if empty:
        L.append("Present but empty across the cohort: "
                 + ", ".join(f"**{e['predictor']}** (`{e['column']}`)"
                             for e in empty)
                 + ". No file was written for these, so they cannot enter the "
                 "evaluation as a predictor that scored nothing.\n")
    L.append("## Notes per predictor\n")
    for r in report:
        L.append(f"- **{r['predictor']}** — {r['note']}")
    L.append("")

    with open(os.path.join(RESULTS, "dbnsfp_conversion.md"), "w") as fh:
        fh.write("\n".join(L))
    with open(os.path.join(RESULTS, "_dbnsfp_conversion.json"), "w") as fh:
        json.dump({"source": args.dbnsfp, "columns": len(cols),
                   "chr_col": chr_col, "pos_col": pos_col, "layout": why,
                   "mode": "raw" if args.raw else "rankscore",
                   "aggregate": args.aggregate if args.raw else None,
                   "rows_read": n_rows, "joined": n_join, "cohort": n_cohort,
                   "missing": missing, "empty": empty,
                   "predictors": report}, fh, indent=2)
    print(f"\nwrote {os.path.join(RESULTS, 'dbnsfp_conversion.md')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
