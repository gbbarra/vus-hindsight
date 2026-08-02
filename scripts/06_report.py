#!/usr/bin/env python3
"""Assemble results/transitions.md from the per-baseline JSON count files.

Reads every results/_counts_*.json written by 04_transitions.py and renders one
markdown report. Every number in the output comes from those files; this script
computes no estimates and has no fallback values.
"""
import glob
import json
import os
from datetime import date

RESULTS = "results"


def table(headers, rows):
    out = ["| " + " | ".join(headers) + " |",
           "|" + "|".join("---" for _ in headers) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(c) for c in r) + " |")
    return "\n".join(out)


def main():
    paths = sorted(glob.glob(os.path.join(RESULTS, "_counts_*.json")))
    if not paths:
        raise SystemExit("no results/_counts_*.json found — run 04_transitions.py first")
    metas = [json.load(open(p)) for p in paths]

    L = []
    L.append("# ClinVar VUS reclassification — measured transitions\n")
    L.append(f"Generated {date.today().isoformat()} from ClinVar `variant_summary` "
             "snapshots. Every count below is produced by `scripts/04_transitions.py` "
             "and reproducible with `scripts/run_all.sh`.\n")

    L.append("## Snapshots\n")
    rows = []
    for m in metas:
        rows.append([m["label"], f"`{m['baseline_file']}`",
                     f"{m['baseline']['rows_deduped']:,}",
                     m["baseline"]["classification_column"],
                     m["baseline"]["review_column"]])
    rows.append(["current", f"`{metas[0]['current_file']}`",
                 f"{metas[0]['current']['rows_deduped']:,}",
                 metas[0]["current"]["classification_column"],
                 metas[0]["current"]["review_column"]])
    L.append(table(["snapshot", "file", "GRCh38 variants (deduped)",
                    "classification column", "review column"], rows))
    L.append("")

    vcf_stats_path = os.path.join(RESULTS, "_vcf_mc_stats.json")
    if os.path.exists(vcf_stats_path):
        v = json.load(open(vcf_stats_path))
        L.append(f"Molecular consequence is read from the `MC` (Sequence Ontology) "
                 f"field of the ClinVar GRCh38 VCF `{v['vcf_file']}` — "
                 f"{v['variation_ids']:,} VariationIDs, of which "
                 f"{v['with_mc_field']:,} carry an `MC` term. It is not inferred "
                 f"from HGVS.\n")
    else:
        L.append("Molecular consequence source: ClinVar VCF `MC` field "
                 "(VCF stats file absent).\n")

    for m in metas:
        lab = m["label"]
        L.append(f"## Baseline {lab} → current\n")
        L.append(f"Baseline VUS cohort (criteria provided): **{m['baseline_vus']:,}** "
                 f"variants. Excluded {m['baseline_vus_excluded_no_criteria']:,} VUS "
                 "with review status *no assertion criteria provided*.\n")
        L.append(table(["current classification", "n", "% of baseline VUS"],
                       [[t["current_bucket"], f"{t['n']:,}", f"{t['pct']:.2f}%"]
                        for t in m["transitions"]]))
        L.append("")
        L.append(f"### VUS → P/LP arm ({lab})\n")
        L.append(f"**{m['vus_to_plp']:,}** variants moved from Uncertain significance "
                 f"to Pathogenic/Likely pathogenic, across "
                 f"**{m['vus_to_plp_distinct_genes']:,}** distinct genes.\n")
        L.append("By molecular consequence (ClinVar VCF `MC` field):\n")
        L.append(table(["consequence", "n"],
                       [[c["consequence"], f"{c['n']:,}"]
                        for c in m["vus_to_plp_by_consequence"]]))
        L.append("")
        if m.get("vus_to_plp_not_in_vcf"):
            L.append(f"`not_in_vcf` = {m['vus_to_plp_not_in_vcf']:,} variants have no "
                     "record in the GRCh38 VCF (typically no precise genomic "
                     "placement). They are reported as their own row rather than "
                     "folded into `other`.\n")
        conc = m.get("consequence_concordance") or {}
        if conc.get("matched"):
            L.append(f"*Diagnostic:* an independent derivation of consequence from "
                     f"HGVS agrees with the `MC` term for "
                     f"{conc['agree']:,}/{conc['matched']:,} "
                     f"({conc['pct']:.2f}%) of these variants. The published "
                     f"breakdown above uses `MC` alone.\n")
        L.append("By current review status:\n")
        L.append(table(["review status", "stars", "n"],
                       [[r["review_status"], r["stars"], f"{r['n']:,}"]
                        for r in m["vus_to_plp_by_review"]]))
        L.append("")
        L.append(f"**Hard stratum** — missense AND review status at least "
                 f"*criteria provided, multiple submitters* (≥2 stars): "
                 f"**{m['vus_to_plp_missense_2star_plus']:,}** variants across "
                 f"{m['vus_to_plp_missense_2star_plus_genes']:,} genes.\n")

    # Exact inputs. `variant_summary.txt.gz` and `clinvar.vcf.gz` are rolling
    # filenames, so the release stamp and md5 are what make these counts
    # re-derivable rather than merely re-runnable.
    manifest = os.path.join(RESULTS, "_manifest.tsv")
    if os.path.exists(manifest):
        with open(manifest) as fh:
            rows = [ln.rstrip("\n").split("\t") for ln in fh if ln.strip()]
        if len(rows) > 1:
            L.append("## Exact inputs\n")
            L.append("`variant_summary.txt.gz` and `clinvar.vcf.gz` are rolling "
                     "filenames — the same URL serves a different release each "
                     "month. To reproduce these exact counts, match the release "
                     "stamp and md5 below; a newer release will legitimately give "
                     "different numbers.\n")
            L.append(table(["role", "file", "bytes", "release (Last-Modified)", "md5"],
                           [[r[0], f"`{r[1]}`", f"{int(r[3]):,}" if r[3].isdigit() else r[3],
                             r[4], f"`{r[5]}`"] for r in rows[1:]]))
            L.append("")

    L.append("## Reproduce\n")
    L.append("```bash\nscripts/run_all.sh\n```\n")
    L.append("Per-variant records: `results/reclassified_pathogenic.tsv` "
             "(VUS → P/LP) and `results/reclassified_benign.tsv` (VUS → B/LB), "
             "identical schema. The benign arm supplies the negatives — "
             "discrimination cannot be measured from the pathogenic arm alone — "
             "so concatenating the two gives a labelled evaluation set.\n")

    out = os.path.join(RESULTS, "transitions.md")
    with open(out, "w") as fh:
        fh.write("\n".join(L))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
