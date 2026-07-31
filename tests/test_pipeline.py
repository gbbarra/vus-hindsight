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
    "by_consequence": {"missense": 3, "nonsense": 1, "frameshift": 1, "splice": 1},
    "vus_to_plp_missense_2star_plus": 3,
}


def main():
    subprocess.run([sys.executable, os.path.join(HERE, "make_fixture.py")],
                   check=True, cwd=ROOT)
    workdir = tempfile.mkdtemp(prefix="vus_test_")
    os.makedirs(os.path.join(workdir, "results"), exist_ok=True)

    env = dict(os.environ, PYTHONPATH=os.path.join(ROOT, "scripts"))
    subprocess.run(
        [sys.executable, os.path.join(ROOT, "scripts", "04_transitions.py"),
         "--baseline", os.path.join(HERE, "fixtures", "baseline_fixture.txt.gz"),
         "--current", os.path.join(HERE, "fixtures", "current_fixture.txt.gz"),
         "--label", "FIXTURE"],
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
    check("tsv rows written", meta["tsv_rows_written"], EXPECTED["vus_to_plp"])

    if failures:
        print("\nFAILURES:")
        for f in failures:
            print("  " + f)
        return 1
    print("\nAll fixture assertions passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
