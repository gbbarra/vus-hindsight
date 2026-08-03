#!/usr/bin/env python3
"""Assert the analysis logic against the synthetic fixture.

Run:  python3 tests/test_pipeline.py
This validates code paths only. It says nothing about ClinVar itself.
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

EXPECTED = {
    "baseline_vus": 11,
    "baseline_vus_excluded_no_criteria": 1,
    "transitions": {"P/LP": 6, "B/LB": 1, "Still VUS": 1,
                    "Conflicting": 1, "Retired/absent": 1, "Other": 1},
    "vus_to_plp": 6,
    "vus_to_plp_distinct_genes": 5,
    # Consequence now comes from the VCF MC field, so VID 2 counts as frameshift
    # (its MC term) rather than nonsense (its HGVS), and VID 10 — absent from the
    # VCF — lands in not_in_vcf rather than missense.
    "by_consequence": {"missense": 2, "frameshift": 2, "splice": 1, "not_in_vcf": 1},
    "vus_to_plp_missense_2star_plus": 2,
    "vus_to_plp_not_in_vcf": 1,
    "concordance": {"matched": 5, "agree": 4},
}


def main():
    subprocess.run([sys.executable, os.path.join(HERE, "make_fixture.py")],
                   check=True, cwd=ROOT)
    workdir = tempfile.mkdtemp(prefix="vus_test_")
    os.makedirs(os.path.join(workdir, "results"), exist_ok=True)

    env = dict(os.environ, PYTHONPATH=os.path.join(ROOT, "scripts"))
    cons_map = os.path.join(workdir, "consequence_map.parquet")
    subprocess.run(
        [sys.executable, os.path.join(ROOT, "scripts", "03b_extract_mc.py"),
         os.path.join(HERE, "fixtures", "clinvar_fixture.vcf.gz"),
         "--out", cons_map],
        check=True, cwd=workdir, env=env)
    subprocess.run(
        [sys.executable, os.path.join(ROOT, "scripts", "04_transitions.py"),
         "--baseline", os.path.join(HERE, "fixtures", "baseline_fixture.txt.gz"),
         "--current", os.path.join(HERE, "fixtures", "current_fixture.txt.gz"),
         "--label", "FIXTURE", "--consequence-map", cons_map],
        check=True, cwd=workdir, env=env)

    meta = json.load(open(os.path.join(workdir, "results", "_counts_FIXTURE.json")))
    failures = []

    def check(name, got, want):
        if got != want:
            failures.append(f"{name}: got {got!r}, want {want!r}")
        else:
            print(f"  OK  {name} = {got}")

    check("baseline_vus", meta["baseline_vus"], EXPECTED["baseline_vus"])
    check("baseline_vus_excluded_no_criteria",
          meta["baseline_vus_excluded_no_criteria"],
          EXPECTED["baseline_vus_excluded_no_criteria"])
    check("dedupe collapsed duplicate VariationID",
          meta["baseline"]["rows_grch38"] - meta["baseline"]["rows_deduped"], 1)
    check("GRCh37 rows filtered out",
          meta["baseline"]["rows_total"] - meta["baseline"]["rows_grch38"], 1)
    check("baseline classification column",
          meta["baseline"]["classification_column"], "ClinicalSignificance")
    check("current classification column",
          meta["current"]["classification_column"], "GermlineClassification")

    got_tr = {t["current_bucket"]: t["n"] for t in meta["transitions"]}
    check("transition table", got_tr, EXPECTED["transitions"])
    check("vus_to_plp", meta["vus_to_plp"], EXPECTED["vus_to_plp"])
    check("distinct genes", meta["vus_to_plp_distinct_genes"],
          EXPECTED["vus_to_plp_distinct_genes"])
    got_cons = {c["consequence"]: c["n"] for c in meta["vus_to_plp_by_consequence"]}
    check("by consequence", got_cons, EXPECTED["by_consequence"])
    check("missense AND >=2 star", meta["vus_to_plp_missense_2star_plus"],
          EXPECTED["vus_to_plp_missense_2star_plus"])
    check("not_in_vcf reported separately", meta["vus_to_plp_not_in_vcf"],
          EXPECTED["vus_to_plp_not_in_vcf"])
    conc = meta["consequence_concordance"]
    check("HGVS cross-check matched", conc["matched"],
          EXPECTED["concordance"]["matched"])
    check("HGVS cross-check agreements", conc["agree"],
          EXPECTED["concordance"]["agree"])
    check("tsv rows written", meta["tsv_rows_written"], EXPECTED["vus_to_plp"])
    # The benign arm is the negative class; without it nothing can measure
    # discrimination. The fixture has exactly one VUS -> B/LB variant.
    check("benign arm exported", meta["tsv_benign_rows_written"],
          EXPECTED["transitions"]["B/LB"])
    benign = open(os.path.join(workdir, "results",
                               "reclassified_benign.tsv")).read().splitlines()
    check("benign tsv has header + rows", len(benign),
          1 + EXPECTED["transitions"]["B/LB"])
    check("both arms share a schema",
          benign[0],
          open(os.path.join(workdir, "results",
                            "reclassified_pathogenic.tsv")).readline().rstrip("\n"))

    # Report assembly must survive the real shape of the counts JSON, otherwise a
    # bug here would only surface after a multi-GB download.
    with open(os.path.join(workdir, "results", "_manifest.tsv"), "w") as fh:
        fh.write("role\tfilename\turl\tbytes\tlast_modified\tmd5\n")
        fh.write("current\tvariant_summary.txt.gz\thttps://example/vs.gz\t123456\t"
                 "Tue, 28 Jul 2026 04:38:51 GMT\tdeadbeefcafe\n")
    subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "06_report.py")],
                   check=True, cwd=workdir, env=env)
    md = open(os.path.join(workdir, "results", "transitions.md")).read()
    for needle in ["VUS → P/LP", "Hard stratum", "not_in_vcf", "MC",
                   "Exact inputs", "deadbeefcafe", "28 Jul 2026"]:
        check(f"transitions.md mentions {needle!r}", needle in md, True)

    # Fixed-cohort survival: the cohort must match the transition analysis's
    # baseline cohort exactly, since both derive it from the same snapshot.
    cohort_pq = os.path.join(workdir, "cohort.parquet")
    subprocess.run(
        [sys.executable, os.path.join(ROOT, "scripts", "07_survival.py"),
         "--baseline", os.path.join(HERE, "fixtures", "baseline_fixture.txt.gz"),
         "--baseline-label", "2021-06", "--out-cohort", cohort_pq],
        check=True, cwd=workdir, env=env)
    subprocess.run(
        [sys.executable, os.path.join(ROOT, "scripts", "07_survival.py"),
         "--cohort", cohort_pq, "--baseline-label", "2021-06",
         "--endpoint", os.path.join(HERE, "fixtures", "current_fixture.txt.gz"),
         "--endpoint-label", "2022-12", "--consequence-map", cons_map],
        check=True, cwd=workdir, env=env)
    surv = json.load(open(os.path.join(workdir, "results", "_survival.json")))
    check("survival: one point recorded", len(surv), 1)
    pt = surv[0]
    check("survival: cohort matches transition baseline", pt["cohort_size"],
          EXPECTED["baseline_vus"])
    check("survival: months elapsed computed from labels", pt["months_elapsed"], 18)
    check("survival: P/LP agrees with the transition analysis", pt["p_lp"],
          EXPECTED["vus_to_plp"])
    check("survival: hard stratum agrees", pt["hard_stratum"],
          EXPECTED["vus_to_plp_missense_2star_plus"])

    subprocess.run([sys.executable,
                    os.path.join(ROOT, "scripts", "08_survival_report.py")],
                   check=True, cwd=workdir, env=env)
    sm = open(os.path.join(workdir, "results", "survival.md")).read()
    for needle in ["survival_curve.svg", "Month 0 is definitional", "hard stratum"]:
        check(f"survival.md mentions {needle!r}", needle in sm, True)
    svg = open(os.path.join(workdir, "results", "survival_curve.svg")).read()
    check("survival chart is a valid-looking svg",
          svg.startswith("<svg") and svg.rstrip().endswith("</svg>"), True)

    # Frozen-date reconstruction: each fixture variant pins one aggregation rule.
    recon_pq = os.path.join(workdir, "recon.parquet")
    subprocess.run(
        [sys.executable, os.path.join(ROOT, "scripts", "09_reconstruct.py"),
         "--submissions", os.path.join(HERE, "fixtures", "submission_fixture.txt.gz"),
         "--as-of", "2021-06-03", "--out", recon_pq],
        check=True, cwd=workdir, env=env)
    import duckdb
    got = {r[0]: (r[1], r[2]) for r in duckdb.connect().execute(
        f"SELECT variation_id, classification, stars FROM read_parquet('{recon_pq}')"
    ).fetchall()}
    expected_recon = {
        100: ("Pathogenic", 2),                                    # two submitters agree
        101: ("Conflicting classifications of pathogenicity", 1),  # P vs VUS
        102: ("Uncertain significance", 1),                        # single submitter
        103: ("Pathogenic", 3),                                    # expert panel overrides
        104: ("Pathogenic", 0),          # 0-star variants still carry a classification
        105: ("Pathogenic/Likely pathogenic", 2),                  # P+LP is not a conflict
        108: ("Benign/Likely benign", 2),                          # B+LB is not a conflict
        109: ("Pathogenic", 1),                                    # same submitter twice
        110: ("Likely pathogenic", 4),                             # guideline outranks panel
    }
    for vid, want in expected_recon.items():
        check(f"reconstruction VID {vid}", got.get(vid), want)
    check("post-cutoff submission excluded", 106 in got, False)
    check("non-contributing submission excluded", 107 in got, False)
    check("undated submission excluded", 111 in got, False)

    # Contamination audit: tiers and leakage brackets, against a synthetic
    # registry so the assertions do not depend on anyone's literature search.
    surv_path = os.path.join(workdir, "results", "_survival.json")
    with open(surv_path, "w") as fh:
        json.dump([{"months_elapsed": 18, "p_lp": 1058},
                   {"months_elapsed": 36, "p_lp": 2987},
                   {"months_elapsed": 61, "p_lp": 4735}], fh)
    reg_path = os.path.join(workdir, "predictors_test.yaml")
    with open(reg_path, "w") as fh:
        fh.write("""
predictors:
  - {name: BeforeBaseline, training_cutoff: '2019-01', verified: true, label_exposure: training_labels}
  - {name: AtBaseline,     training_cutoff: '2021-06', verified: true, label_exposure: training_labels}
  - {name: MidWindow,      training_cutoff: '2023-06', verified: true, label_exposure: training_labels}
  - {name: LateWindow,     training_cutoff: '2025-06', verified: true, label_exposure: training_labels}
  - {name: PastEndpoint,   training_cutoff: '2026-07', verified: true, label_exposure: training_labels}
  - {name: Unsourced,      training_cutoff: '2019-01', verified: false, label_exposure: training_labels}
  - {name: NoCutoff,       training_cutoff: null,      verified: true, label_exposure: training_labels}
  - {name: LabelFreeRecent, training_cutoff: null,     verified: false, label_exposure: none}
  - {name: Measured,       training_cutoff: null,      verified: false, label_exposure: evaluation_only,
     measured_overlap: {vus_to_plp: '531 / 2883', control_still_vus: '1 / 25000'}}
""")
    subprocess.run(
        [sys.executable, os.path.join(ROOT, "scripts", "11_contamination_audit.py"),
         "--registry", reg_path, "--baseline", "2021-06", "--survival", surv_path],
        check=True, cwd=workdir, env=env)
    aud = {r["predictor"]: r for r in json.load(
        open(os.path.join(workdir, "results", "_contamination_audit.json")))["predictors"]}
    check("audit: cutoff before baseline is CLEAN",
          aud["BeforeBaseline"]["date_tier"], "CLEAN")
    check("audit: cutoff at baseline is CLEAN", aud["AtBaseline"]["date_tier"], "CLEAN")
    check("audit: cutoff inside window is PARTIAL", aud["MidWindow"]["date_tier"], "PARTIAL")
    check("audit: cutoff past endpoint is CONTAMINATED",
          aud["PastEndpoint"]["date_tier"], "CONTAMINATED")
    # An unsourced cutoff must never be credited as clean.
    check("audit: unsourced cutoff is UNVERIFIED", aud["Unsourced"]["date_tier"],
          "UNVERIFIED")
    check("audit: missing cutoff is UNVERIFIED", aud["NoCutoff"]["date_tier"], "UNVERIFIED")
    # Leakage is bracketed by measured points, never interpolated.
    check("audit: mid-window leakage bracket",
          (aud["MidWindow"]["leak_low"], aud["MidWindow"]["leak_high"]), (1058, 2987))
    check("audit: late-window leakage bracket",
          (aud["LateWindow"]["leak_low"], aud["LateWindow"]["leak_high"]), (2987, 4735))
    check("audit: clean tools leak nothing", aud["AtBaseline"]["leak_high"], 0)
    # A model with no clinical labels cannot memorise reclassifications, so an
    # unknown date must not condemn it — that is the second axis doing its job.
    check("audit: label-free survives an unknown date",
          aud["LabelFreeRecent"]["verdict"], "LABEL-FREE")
    # A measurement outranks any date reasoning.
    check("audit: measured overlap outranks dates",
          aud["Measured"]["verdict"], "MEASURED LEAK")
    check("audit: direct label exposure is flagged as such",
          aud["MidWindow"]["verdict"], "DIRECT / PARTIAL")

    # Join export: exact column list and order, the variant_id format, the arm
    # split, and that a horizon is attached to every reclassified row.
    export_csv = os.path.join(workdir, "exports", "join.csv")
    subprocess.run(
        [sys.executable, os.path.join(ROOT, "scripts", "12_export_for_join.py"),
         "--baseline", os.path.join(HERE, "fixtures", "baseline_fixture.txt.gz")
         + ":2021-06",
         "--endpoint", os.path.join(HERE, "fixtures", "current_fixture.txt.gz")
         + ":2026-07:61",
         "--consequence-map", cons_map, "--out", export_csv],
        check=True, cwd=workdir, env=env)
    import csv as _csv
    with open(export_csv) as fh:
        exp_rows = list(_csv.DictReader(fh))
        fh.seek(0)
        header = fh.readline().strip().split(",")
    check("export: exact column list and order", header,
          ["variant_id_hg38", "variation_id", "chrom", "pos_hg38", "ref", "alt",
           "gene_symbol", "molecular_consequence", "review_status", "gold_stars",
           "classification_2021", "classification_current",
           "date_last_evaluated", "horizon_months", "stratum", "arm"])
    by_arm = {}
    for r in exp_rows:
        by_arm.setdefault(r["arm"], []).append(r)
    check("export: vus_to_plp arm size", len(by_arm.get("vus_to_plp", [])),
          EXPECTED["vus_to_plp"])
    # Only VID 4 stays VUS, and it is intron by MC, so the missense-only
    # control is empty for this fixture.
    check("export: still_vus arm is missense-only", len(by_arm.get("still_vus", [])), 0)
    one = by_arm["vus_to_plp"][0]
    check("export: variant_id_hg38 format",
          one["variant_id_hg38"] ==
          f"chr{one['chrom']}_{one['pos_hg38']}_{one['ref']}_{one['alt']}_hg38",
          True)
    check("export: variant_id starts with chr",
          all(r["variant_id_hg38"].startswith("chr") for r in exp_rows), True)
    check("export: every reclassified row has a horizon",
          all(r["horizon_months"] == "61" for r in by_arm["vus_to_plp"]), True)
    check("export: date_last_evaluated is ISO",
          all(r["date_last_evaluated"] == "2020-01-01" for r in exp_rows), True)
    check("export: gold_stars is an integer 0-4",
          all(r["gold_stars"].isdigit() and 0 <= int(r["gold_stars"]) <= 4
              for r in exp_rows), True)
    check("export: primary stratum is missense and >=2 stars",
          sorted(r["stratum"] for r in by_arm["vus_to_plp"]),
          sorted(["primary" if (r["molecular_consequence"] == "missense"
                                and int(r["gold_stars"]) >= 2) else "other"
                  for r in by_arm["vus_to_plp"]]))

    if failures:
        print("\nFAILURES:")
        for f in failures:
            print("  " + f)
        return 1
    print("\nAll fixture assertions passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
