#!/usr/bin/env python3
"""Export the benchmark cohort as a flat CSV for external contamination analysis.

Two populations, distinguished by `arm`:

  vus_to_plp   variants that were VUS with criteria at the baseline and are
               P/LP at the final endpoint, each carrying the horizon at which
               that label FIRST appeared. The horizon is the contamination-
               relevant field: it says when a predictor could earliest have
               been told the answer.
  still_vus    the missense controls — VUS at baseline, still VUS at the final
               endpoint. Negative controls for the same join.

The arm is restricted to the baseline cohort rather than the union across
baselines, because a variant drawn from a different baseline has no horizon on
this timeline and so cannot contribute to a contamination analysis.

Usage:
  12_export_for_join.py --baseline F:2021-06 \
      --endpoint F1:2022-12:18 --endpoint F2:2024-06:36 --endpoint F3:2026-07:61 \
      --consequence-map data/consequence_map.parquet \
      --out data/exports/vus_hindsight_for_am_join.csv
"""
import argparse
import hashlib
import json
import os
import sys

import duckdb
from snapshot import load_snapshot

COLUMNS = ["variant_id_hg38", "variation_id", "chrom", "pos_hg38", "ref", "alt",
           "gene_symbol", "molecular_consequence", "review_status", "gold_stars",
           "classification_2021", "classification_current", "date_last_evaluated",
           "horizon_months", "stratum", "arm"]

STILL_VUS_CAP = 200_000
STILL_VUS_SAMPLE = 25_000
SAMPLE_SEED = 20260802


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline", required=True, help="path:label")
    ap.add_argument("--endpoint", action="append", required=True,
                    help="path:label:months, repeatable, ascending")
    ap.add_argument("--consequence-map", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--manifest", default="results/_manifest.tsv")
    ap.add_argument("--memory-limit", default="6GB")
    ap.add_argument("--temp-dir", default="data/duckdb_tmp")
    args = ap.parse_args()

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    os.makedirs(args.temp_dir, exist_ok=True)

    con = duckdb.connect()
    con.execute(f"PRAGMA memory_limit='{args.memory_limit}'")
    con.execute(f"PRAGMA temp_directory='{args.temp_dir}'")

    base_path, base_label = args.baseline.rsplit(":", 1)
    endpoints = []
    for spec in args.endpoint:
        path, label, months = spec.rsplit(":", 2)
        endpoints.append((path, label, int(months)))
    endpoints.sort(key=lambda e: e[2])
    final_path, final_label, final_months = endpoints[-1]

    load_snapshot(con, "base", base_path, f"baseline {base_label}")
    con.execute("""
        CREATE OR REPLACE TABLE cohort AS
        SELECT variation_id, raw_class AS classification_2021
        FROM base WHERE bucket = 'Still VUS' AND stars >= 1
    """)
    n_cohort = con.execute("SELECT count(*) FROM cohort").fetchone()[0]
    print(f"\ncohort at {base_label}: {n_cohort:,}")

    con.execute(f"""
        CREATE OR REPLACE TABLE cons AS
        SELECT * FROM read_parquet('{args.consequence_map}')
    """)

    # Walk the endpoints in order, recording the earliest horizon at which each
    # cohort member was P/LP. Point-in-time state, so a variant that reaches
    # P/LP and is later disputed still records the horizon where it first did.
    con.execute("CREATE OR REPLACE TABLE first_plp (variation_id BIGINT, horizon_months INT)")
    for path, label, months in endpoints:
        alias = f"ep{months}"
        load_snapshot(con, alias, path, f"endpoint {label} (+{months}m)")
        con.execute(f"""
            INSERT INTO first_plp
            SELECT c.variation_id, {months}
            FROM cohort c JOIN {alias} e USING (variation_id)
            WHERE e.bucket = 'P/LP'
              AND c.variation_id NOT IN (SELECT variation_id FROM first_plp)
        """)
        n = con.execute("SELECT count(*) FROM first_plp").fetchone()[0]
        print(f"  cumulative first-P/LP by +{months}m: {n:,}")
        if (path, label, months) != endpoints[-1]:
            con.execute(f"DROP TABLE {alias}")

    final_alias = f"ep{final_months}"

    # Rows are assembled from the FINAL endpoint: coordinates, current
    # classification, review status and evaluation date all describe that
    # release, which is the one the md5 in the README pins.
    con.execute(f"""
        CREATE OR REPLACE TABLE rows_all AS
        WITH j AS (
            SELECT
                c.variation_id,
                c.classification_2021,
                e.gene, e.raw_class AS classification_current,
                e.raw_review AS review_status, e.stars AS gold_stars,
                e.chromosome, e.position_vcf, e.ref_vcf, e.alt_vcf,
                e.last_evaluated, e.bucket,
                coalesce(m.consequence, 'not_in_vcf') AS molecular_consequence,
                f.horizon_months
            FROM cohort c
            JOIN {final_alias} e USING (variation_id)
            LEFT JOIN cons m USING (variation_id)
            LEFT JOIN first_plp f USING (variation_id)
        )
        SELECT
            'chr' || chromosome || '_' || position_vcf || '_' || ref_vcf
                  || '_' || alt_vcf || '_hg38'          AS variant_id_hg38,
            variation_id,
            chromosome                                   AS chrom,
            TRY_CAST(position_vcf AS BIGINT)             AS pos_hg38,
            ref_vcf                                      AS ref,
            alt_vcf                                      AS alt,
            gene                                         AS gene_symbol,
            molecular_consequence,
            review_status,
            gold_stars,
            classification_2021,
            classification_current,
            coalesce(strftime(try_strptime(last_evaluated,
                     ['%b %d, %Y', '%Y-%m-%d']), '%Y-%m-%d'), '')
                                                         AS date_last_evaluated,
            CASE WHEN bucket = 'P/LP' THEN CAST(horizon_months AS VARCHAR)
                 ELSE 'still_vus' END                    AS horizon_months,
            CASE WHEN molecular_consequence = 'missense' AND gold_stars >= 2
                 THEN 'primary' ELSE 'other' END         AS stratum,
            CASE WHEN bucket = 'P/LP' THEN 'vus_to_plp'
                 WHEN bucket = 'Still VUS' THEN 'still_vus' END AS arm
        FROM j
        WHERE bucket IN ('P/LP', 'Still VUS')
          -- A row without complete GRCh38 VCF coordinates cannot be joined on
          -- variant_id_hg38, which is the whole point of this export.
          AND chromosome IS NOT NULL AND chromosome <> ''
          AND position_vcf IS NOT NULL AND position_vcf <> ''
          AND ref_vcf IS NOT NULL AND ref_vcf <> ''
          AND alt_vcf IS NOT NULL AND alt_vcf <> ''
    """)

    n_plp = con.execute(
        "SELECT count(*) FROM rows_all WHERE arm = 'vus_to_plp'").fetchone()[0]
    n_vus_all = con.execute(
        "SELECT count(*) FROM rows_all WHERE arm = 'still_vus'").fetchone()[0]
    n_vus_mis = con.execute("""SELECT count(*) FROM rows_all
        WHERE arm = 'still_vus' AND molecular_consequence = 'missense'""").fetchone()[0]
    print(f"\nvus_to_plp rows (joinable)       : {n_plp:,}")
    print(f"still_vus rows, all consequences  : {n_vus_all:,}")
    print(f"still_vus rows, missense only     : {n_vus_mis:,}")

    sampled = n_vus_mis > STILL_VUS_CAP
    if sampled:
        # Proportional allocation across gold_stars, largest-remainder to land
        # exactly on the target. Ordering is by a hash of the seed and the
        # VariationID, so the draw is reproducible without an RNG.
        strata = con.execute("""
            SELECT gold_stars, count(*) n FROM rows_all
            WHERE arm='still_vus' AND molecular_consequence='missense'
            GROUP BY 1 ORDER BY 1
        """).fetchall()
        total = sum(n for _, n in strata)
        raw = [(s, STILL_VUS_SAMPLE * n / total, n) for s, n in strata]
        alloc = {s: min(int(q), n) for s, q, n in raw}
        rem = STILL_VUS_SAMPLE - sum(alloc.values())
        for s, _q, n in sorted(raw, key=lambda r: -(r[1] - int(r[1]))):
            if rem <= 0:
                break
            if alloc[s] < n:
                alloc[s] += 1
                rem -= 1
        print(f"\nstill_vus missense exceeds {STILL_VUS_CAP:,}; sampling "
              f"{STILL_VUS_SAMPLE:,} stratified by gold_stars (seed {SAMPLE_SEED}):")
        for s, n in strata:
            print(f"  {s}*: {n:,} -> {alloc[s]:,}")
        cases = " ".join(f"WHEN {s} THEN {alloc[s]}" for s, _ in strata)
        con.execute(f"""
            CREATE OR REPLACE TABLE still_sample AS
            SELECT * EXCLUDE (rk) FROM (
                SELECT *, row_number() OVER (
                    PARTITION BY gold_stars
                    ORDER BY hash(CAST(variation_id AS VARCHAR) || '{SAMPLE_SEED}')
                ) AS rk
                FROM rows_all
                WHERE arm='still_vus' AND molecular_consequence='missense')
            WHERE rk <= CASE gold_stars {cases} ELSE 0 END
        """)
        con.execute("""
            CREATE OR REPLACE TABLE final_rows AS
            SELECT * FROM rows_all WHERE arm='vus_to_plp'
            UNION ALL SELECT * FROM still_sample
        """)
    else:
        con.execute("""
            CREATE OR REPLACE TABLE final_rows AS
            SELECT * FROM rows_all WHERE arm='vus_to_plp'
            UNION ALL
            SELECT * FROM rows_all
            WHERE arm='still_vus' AND molecular_consequence='missense'
        """)

    cols = ", ".join(COLUMNS)
    con.execute(f"""
        COPY (SELECT {cols} FROM final_rows
              ORDER BY arm, variation_id)
        TO '{args.out}' (FORMAT csv, HEADER)
    """)
    n_out = con.execute("SELECT count(*) FROM final_rows").fetchone()[0]
    n_out_vus = con.execute(
        "SELECT count(*) FROM final_rows WHERE arm='still_vus'").fetchone()[0]
    print(f"\nwrote {args.out}: {n_out:,} rows "
          f"({n_plp:,} vus_to_plp + {n_out_vus:,} still_vus)")

    by_h = con.execute("""
        SELECT horizon_months, count(*) n FROM final_rows
        WHERE arm='vus_to_plp' GROUP BY 1 ORDER BY 1
    """).fetchall()
    by_s = con.execute("""
        SELECT arm, stratum, count(*) n FROM final_rows GROUP BY 1,2 ORDER BY 1,2
    """).fetchall()
    print("horizons:", {h: n for h, n in by_h})
    print("strata  :", {f"{a}/{s}": n for a, s, n in by_s})

    # --- README, carrying the exact inputs ------------------------------------
    manifest = []
    if os.path.exists(args.manifest):
        with open(args.manifest) as fh:
            manifest = [ln.rstrip("\n").split("\t") for ln in fh if ln.strip()]

    with open(args.out, "rb") as fh:
        # md5 aqui é impressão digital de proveniência, não segurança: ele
        # identifica os bytes exatos que produziram este relatório, para que um
        # revisor confira que está olhando o mesmo arquivo.
        csv_md5 = hashlib.md5(fh.read(), usedforsecurity=False).hexdigest()
    R = [f"# `{os.path.basename(args.out)}`\n"]
    R.append("Flat export of the vus-hindsight cohort for external "
             "contamination analysis — joining predictor scores against "
             "variants whose ClinVar label changed, and against controls whose "
             "label did not.\n")
    R.append("## Exact inputs\n")
    if len(manifest) > 1:
        R.append("| role | file | release (Last-Modified) | md5 |")
        R.append("|---|---|---|---|")
        seen = set()
        for r in manifest[1:]:
            key = (r[0], r[1])
            if key in seen:
                continue
            seen.add(key)
            R.append(f"| {r[0]} | `{r[1]}` | {r[4]} | `{r[5]}` |")
        R.append("")
    R.append("Note that the endpoint is the **archived monthly** "
             "`variant_summary_2026-07.txt.gz` dated 2 July 2026, not the "
             "rolling `variant_summary.txt.gz` that NCBI overwrites in place. "
             "The rolling file cannot be reproduced once superseded, so no "
             "figure here is derived from it.\n")
    R.append(f"CSV md5: `{csv_md5}`\n")

    R.append("## Arms\n")
    R.append("| arm | rows | definition |")
    R.append("|---|---|---|")
    R.append(f"| `vus_to_plp` | {n_plp:,} | VUS with assertion criteria at "
             f"{base_label}, P/LP at {final_label} (+{final_months} months) |")
    R.append(f"| `still_vus` | {n_out_vus:,} | VUS at {base_label}, still VUS at "
             f"{final_label}; **missense only** |")
    R.append("")
    R.append(f"`vus_to_plp` is drawn from the {base_label} cohort alone, not the "
             "union across baselines. A variant from a different baseline has no "
             "horizon on this timeline, and the horizon is the field a "
             "contamination analysis turns on — it says when the label first "
             "appeared, and therefore the earliest a predictor could have been "
             "told the answer.\n")

    R.append("## Columns\n")
    R.append("| column | notes |\n|---|---|")
    R.append("| `variant_id_hg38` | `chr{chrom}_{pos}_{ref}_{alt}_hg38`, GRCh38, "
             "from ClinVar's VCF-normalised coordinates |")
    R.append("| `horizon_months` | 18 / 36 / 61 — the first endpoint at which the "
             "variant was P/LP; `still_vus` in the control arm |")
    R.append("| `stratum` | `primary` = missense **and** ≥2 gold stars; "
             "`other` otherwise |")
    R.append("| `gold_stars` | 0–4 ClinVar review-status ladder |")
    R.append("| `date_last_evaluated` | ISO, empty when ClinVar reports none |")
    R.append("")
    R.append("Rows lacking complete GRCh38 VCF coordinates are dropped: they "
             "cannot be joined on `variant_id_hg38`, which is the point of the "
             "export.\n")

    R.append("## Horizons\n")
    R.append("| horizon (months) | rows |\n|---|---|")
    for h, n in by_h:
        R.append(f"| {h} | {n:,} |")
    R.append("")

    if sampled:
        R.append("## Sampling\n")
        R.append(f"The missense `still_vus` control had **{n_vus_mis:,}** rows, "
                 f"above the {STILL_VUS_CAP:,} threshold, so it was reduced to "
                 f"{STILL_VUS_SAMPLE:,} by **proportional stratified sampling on "
                 f"`gold_stars`**, largest-remainder to land on the target "
                 f"exactly.\n")
        R.append(f"Seed: `{SAMPLE_SEED}`. Selection orders each stratum by "
                 "`hash(VariationID || seed)` and takes the first *n* — "
                 "deterministic, so re-running reproduces the identical draw "
                 "without depending on an RNG implementation.\n")
        R.append("| gold_stars | available | sampled |\n|---|---|---|")
        for s, n in strata:
            R.append(f"| {s} | {n:,} | {alloc[s]:,} |")
        R.append("")
    else:
        R.append("## Sampling\n")
        R.append(f"None. The missense `still_vus` control had {n_vus_mis:,} rows, "
                 f"below the {STILL_VUS_CAP:,} threshold.\n")

    readme = os.path.join(os.path.dirname(args.out), "README.md")
    with open(readme, "w") as fh:
        fh.write("\n".join(R))
    print(f"wrote {readme}")

    with open(os.path.join("results", "_export_join.json"), "w") as fh:
        json.dump({"out": args.out, "csv_md5": csv_md5, "rows": n_out,
                   "vus_to_plp": n_plp, "still_vus": n_out_vus,
                   "still_vus_missense_available": n_vus_mis,
                   "sampled": sampled, "seed": SAMPLE_SEED if sampled else None,
                   "horizons": {str(h): n for h, n in by_h},
                   "strata": {f"{a}/{s}": n for a, s, n in by_s}}, fh, indent=2)
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
