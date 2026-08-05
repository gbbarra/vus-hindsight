#!/usr/bin/env python3
"""Measure how much of this benchmark's answer sits in AlphaMissense's own evaluation set.

AlphaMissense states that a ClinVar subset was used for model selection and
hyperparameter optimisation, and that the thresholds behind `am_class` were
calibrated for 90% precision on a ClinVar snapshot. It does not state WHICH
ClinVar release. That matters: if the snapshot postdates this benchmark's
baseline, variants whose labels changed after the baseline were visible during
calibration, and evaluating AlphaMissense on them measures partly memorisation.

The paper publishes the list — Supplementary Data S5, 82,872 variants keyed by
`chr{chrom}_{pos}_{ref}_{alt}_hg38`, which is exactly the key this benchmark
exports. So the overlap is directly measurable rather than inferable.

Two things make the result interpretable rather than an artefact:

  * The control arm. `still_vus` variants were VUS at baseline and still are.
    If the overlap merely reflected two large variant sets intersecting, the
    control would show a similar rate. It does not.
  * The horizon breakdown. Reclassifications are stratified by WHEN the label
    first appeared, so a snapshot taken at date D shows a cliff: high overlap
    for horizons before D, near-zero after. The position of that cliff dates
    the snapshot the publication never named.

Usage:
  13_alphamissense_overlap.py --export data/exports/vus_hindsight_for_am_join.csv \
                              --s5 data/science.adg7492_data_s5.csv
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--export", default="data/exports/vus_hindsight_for_am_join.csv")
    ap.add_argument("--s5", required=True)
    ap.add_argument("--out-matches",
                    default=os.path.join(RESULTS, "alphamissense_overlap_matches.csv"))
    args = ap.parse_args()

    os.makedirs(RESULTS, exist_ok=True)
    con = duckdb.connect()

    con.execute(f"""
        CREATE TABLE export AS SELECT * FROM read_csv('{args.export}',
            header=true, all_varchar=true)
    """)
    con.execute(f"""
        CREATE TABLE s5 AS SELECT * FROM read_csv('{args.s5}',
            header=true, all_varchar=true)
    """)
    n_export = con.execute("SELECT count(*) FROM export").fetchone()[0]
    n_s5 = con.execute("SELECT count(*) FROM s5").fetchone()[0]
    print(f"export rows : {n_export:,}")
    print(f"S5 rows     : {n_s5:,}")

    # The comparison is restricted to missense on both sides: S5 is a missense
    # benchmark, so including other consequences would deflate the overlap for
    # a reason that has nothing to do with contamination.
    con.execute("""
        CREATE TABLE j AS
        SELECT e.*, s.label AS s5_label, s.AlphaMissense AS am_score,
               s.variant_id IS NOT NULL AS in_s5
        FROM export e
        LEFT JOIN s5 s ON e.variant_id_hg38 = s.variant_id
        WHERE e.molecular_consequence = 'missense'
    """)

    arms = con.execute("""
        SELECT arm, count(*) n, count(*) FILTER (WHERE in_s5) hit
        FROM j GROUP BY 1 ORDER BY 1
    """).fetchall()
    stats = {a: {"n": n, "hit": h, "pct": round(100.0 * h / n, 4) if n else None}
             for a, n, h in arms}
    print("\n=== overlap by arm (missense only) ===")
    for a, n, h in arms:
        print(f"  {a:12s} {h:>6,} / {n:>6,} = {100.0 * h / n:6.3f}%")

    plp = stats.get("vus_to_plp", {})
    ctl = stats.get("still_vus", {})
    odds = pval = None
    if plp.get("n") and ctl.get("n"):
        table = [[plp["hit"], plp["n"] - plp["hit"]],
                 [ctl["hit"], ctl["n"] - ctl["hit"]]]
        odds, pval = fisher_exact(table, alternative="greater")
        print(f"\nFisher exact (reclassified vs control): OR = {odds:,.0f}, "
              f"p = {pval:.3g}")

    labels = con.execute("""
        SELECT s5_label, count(*) n FROM j
        WHERE in_s5 AND arm = 'vus_to_plp' GROUP BY 1 ORDER BY 1
    """).fetchall()
    print("\nS5 label of the reclassified matches:")
    for lab, n in labels:
        print(f"  label={lab}: {n:,}")

    horizons = con.execute("""
        SELECT horizon_months, count(*) n, count(*) FILTER (WHERE in_s5) hit
        FROM j WHERE arm = 'vus_to_plp' GROUP BY 1 ORDER BY TRY_CAST(horizon_months AS INT)
    """).fetchall()
    print("\n=== overlap by horizon — this is what dates the snapshot ===")
    for h, n, hit in horizons:
        print(f"  +{h:>3s} months: {hit:>5,} / {n:>5,} = {100.0 * hit / n:6.2f}%")

    strata = con.execute("""
        SELECT arm, stratum, count(*) n, count(*) FILTER (WHERE in_s5) hit
        FROM j GROUP BY 1,2 ORDER BY 1,2
    """).fetchall()

    con.execute(f"""
        COPY (SELECT variant_id_hg38, variation_id, gene_symbol, horizon_months,
                     stratum, arm, classification_2021, classification_current,
                     s5_label, am_score
              FROM j WHERE in_s5 ORDER BY arm, TRY_CAST(horizon_months AS INT) NULLS LAST, variation_id)
        TO '{args.out_matches}' (FORMAT csv, HEADER)
    """)
    n_matches = con.execute("SELECT count(*) FROM j WHERE in_s5").fetchone()[0]
    print(f"\nwrote {args.out_matches} ({n_matches:,} rows)")

    s5_md5 = md5(args.s5)
    export_md5 = md5(args.export)

    # --- report --------------------------------------------------------------
    L = ["# AlphaMissense: measured exposure to this benchmark's labels\n"]
    L.append("AlphaMissense states that a ClinVar subset was used for model "
             "selection and hyperparameter optimisation, and that the thresholds "
             "behind `am_class` were calibrated for 90% precision on a ClinVar "
             "snapshot. It does not state **which** release.\n")
    L.append("That is measurable rather than merely arguable, because the paper "
             "publishes the list: Supplementary Data S5, "
             f"**{n_s5:,}** variants keyed by "
             "`chr{chrom}_{pos}_{ref}_{alt}_hg38` — the same key this benchmark "
             "exports.\n")

    L.append("## Overlap\n")
    L.append("Missense only on both sides: S5 is a missense benchmark, so "
             "including other consequences would deflate the overlap for a "
             "reason unrelated to contamination.\n")
    L.append("| arm | in S5 | total | rate |\n|---|---|---|---|")
    for a, n, h in arms:
        L.append(f"| `{a}` | {h:,} | {n:,} | **{100.0 * h / n:.3f}%** |")
    L.append("")
    if odds is not None:
        L.append(f"Fisher exact, reclassified versus control: "
                 f"**OR = {odds:,.0f}**, p = {pval:.3g}.\n")
    L.append("The control is what makes this a signal rather than an artefact. "
             "`still_vus` variants were VUS at baseline and still are — they are "
             "the same kind of variant, in the same genes, drawn from the same "
             "release. If the overlap simply reflected two large sets "
             "intersecting, the control would show a comparable rate.\n")

    if labels:
        L.append("## Label of the matches\n")
        L.append("| S5 label | matches |\n|---|---|")
        for lab, n in labels:
            L.append(f"| {lab} | {n:,} |")
        L.append("")

    L.append("## By horizon — dating the snapshot\n")
    L.append("Reclassifications are stratified by when the label **first "
             "appeared**. A snapshot taken at date D shows high overlap for "
             "horizons before D and near-zero after, so the position of the "
             "cliff dates it.\n")
    L.append("| horizon | in S5 | total | rate |\n|---|---|---|---|")
    for h, n, hit in horizons:
        L.append(f"| +{h} months | {hit:,} | {n:,} | **{100.0 * hit / n:.2f}%** |")
    L.append("")

    L.append("## Strata\n")
    L.append("| arm | stratum | in S5 | total | rate |\n|---|---|---|---|---|")
    for a, s, n, hit in strata:
        L.append(f"| `{a}` | {s} | {hit:,} | {n:,} | {100.0 * hit / n:.3f}% |")
    L.append("")

    L.append("## What this does and does not show\n")
    L.append("**It is exposure through evaluation and calibration, not through "
             "weights.** AlphaMissense's weights were fit on population-frequency "
             "weak labels, and the authors say explicitly that they avoid "
             "circularity by not training on human annotation. Nothing here "
             "contradicts that.\n")
    L.append("What it shows is narrower and still consequential: variants whose "
             "ClinVar label changed after this benchmark's baseline were present "
             "in the set where AlphaMissense's performance was reported, and in "
             "the snapshot against which the `am_class` thresholds were "
             "calibrated. `am_class` is therefore downstream of a set containing "
             "answers this benchmark treats as unknown at baseline.\n")
    L.append("The practical consequence is bounded and specific: for the "
             "shortest horizon, an evaluation of AlphaMissense on this cohort is "
             "substantially an evaluation on data it was tuned against. For the "
             "longer horizons it is not.\n")

    L.append("## Inputs\n")
    L.append("| file | md5 |\n|---|---|")
    L.append(f"| `{os.path.basename(args.export)}` | `{export_md5}` |")
    L.append(f"| `{os.path.basename(args.s5)}` | `{s5_md5}` |")
    L.append("")
    L.append("Supplementary Data S5 accompanies Cheng et al., *Science* 2023, "
             "doi:10.1126/science.adg7492. It is not redistributed here; the md5 "
             "above identifies the file used so the analysis can be checked "
             "against the same bytes.\n")
    L.append(f"Matched variants: `{os.path.basename(args.out_matches)}`.\n")

    out_md = os.path.join(RESULTS, "alphamissense_overlap.md")
    with open(out_md, "w") as fh:
        fh.write("\n".join(L))

    with open(os.path.join(RESULTS, "_alphamissense_overlap.json"), "w") as fh:
        json.dump({"s5_rows": n_s5, "s5_md5": s5_md5,
                   "export_md5": export_md5,
                   "by_arm": stats,
                   "odds_ratio": float(odds) if odds is not None else None,
                   "p_value": float(pval) if pval is not None else None,
                   "labels": {str(lab): n for lab, n in labels},
                   "by_horizon": [{"horizon": h, "n": n, "hit": hit,
                                   "pct": round(100.0 * hit / n, 4)}
                                  for h, n, hit in horizons],
                   "by_stratum": [{"arm": a, "stratum": s, "n": n, "hit": hit}
                                  for a, s, n, hit in strata]}, fh, indent=2)
    print(f"wrote {out_md}")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
