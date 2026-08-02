#!/usr/bin/env bash
# End-to-end pipeline. Processes ONE baseline at a time and deletes each raw
# snapshot immediately after use, so peak disk stays near (current + 1 baseline).
#
#   scripts/run_all.sh                  # default baselines: 2021-06, 2022-12
#   BASELINES="2021-06 2022-12" scripts/run_all.sh
set -euo pipefail
cd "$(dirname "$0")/.."

BASELINES="${BASELINES:-2021-06 2022-12}"
DATA="${DATA_DIR:-data}"
export DATA_DIR="$DATA"
mkdir -p "$DATA" results

echo "### free disk before start"; df -h . | tail -1
python3 -c "import duckdb; print('duckdb', duckdb.__version__)"

# Fresh run: the TSV is appended to per baseline, so clear stale output.
rm -f results/reclassified_pathogenic.tsv results/reclassified_pathogenic.tsv.gz \
      results/reclassified_benign.tsv results/reclassified_benign.tsv.gz \
      results/_counts_*.json results/_vcf_mc_stats.json results/_submission_dates.json \
      results/_manifest.tsv results/_survival*.json results/survival.md \
      results/*.svg

echo; echo "### step 1: list FTP directory (authoritative filenames)"
scripts/01_list_clinvar_ftp.sh "$DATA"

echo; echo "### step 2: fetch the endpoint snapshot"
# CURRENT_MONTH pins the endpoint to an archived release instead of the rolling
# variant_summary.txt.gz. That is what makes a past result reproducible: the
# rolling file serves a different release every month, so without pinning you
# cannot regenerate an earlier set of counts.
if [[ -n "${CURRENT_MONTH:-}" ]]; then
  echo "endpoint pinned to archived release $CURRENT_MONTH"
  CURRENT=$(scripts/02_fetch_snapshot.sh archive "$CURRENT_MONTH" | tail -1)
  export CURRENT_LABEL="$CURRENT_MONTH"
else
  CURRENT=$(scripts/02_fetch_snapshot.sh current | tail -1)
fi
echo "endpoint snapshot: $CURRENT"

echo; echo "### step 3: header of current snapshot"
PYTHONPATH=scripts python3 scripts/03_headers.py "$CURRENT"

echo; echo "### step 3b: molecular consequence from the ClinVar VCF MC field"
VCF=$(scripts/02_fetch_snapshot.sh vcf | tail -1)
echo "VCF: $VCF"
PYTHONPATH=scripts python3 scripts/03b_extract_mc.py "$VCF" \
    --out "$DATA/consequence_map.parquet"
echo "deleting raw VCF (the parquet map is all we need downstream): $VCF"
rm -f "$VCF" "$VCF.md5"
df -h . | tail -1

for MONTH in $BASELINES; do
  echo; echo "############ baseline $MONTH ############"
  BASE=$(scripts/02_fetch_snapshot.sh archive "$MONTH" | tail -1)
  echo "baseline snapshot: $BASE"
  PYTHONPATH=scripts python3 scripts/03_headers.py "$BASE"
  PYTHONPATH=scripts python3 scripts/04_transitions.py \
      --baseline "$BASE" --current "$CURRENT" --label "$MONTH" \
      --consequence-map "$DATA/consequence_map.parquet"
  echo "deleting raw baseline snapshot to reclaim disk: $BASE"
  rm -f "$BASE"
  df -h . | tail -1
done

echo; echo "### step 7: submission_summary date-coverage probe"
# Stops at the 2 GB threshold unless SUBMISSION_CONFIRM=1 is set.
PROBE_ARGS=()
[[ "${SUBMISSION_CONFIRM:-0}" == "1" ]] && PROBE_ARGS+=(--confirm)
scripts/05_submission_summary_probe.sh "${PROBE_ARGS[@]}" \
  || echo "(probe exited non-zero — see message above)"

echo; echo "### assembling report"
PYTHONPATH=scripts python3 scripts/06_report.py

# Fixed-cohort survival curve. Runs while the current snapshot and consequence
# map are still on disk, so it only downloads the extra endpoints.
if [[ "${SURVIVAL:-1}" == "1" ]]; then
  echo; scripts/run_survival.sh "$CURRENT" "$DATA/consequence_map.parquet"
fi

echo; echo "### cleaning up current snapshot"
rm -f "$CURRENT"
rm -rf "$DATA/duckdb_tmp"

# gzip the per-variant table if it exceeds 50 MB
for F in results/reclassified_pathogenic.tsv results/reclassified_benign.tsv; do
  [[ -f "$F" ]] || continue
  SZ=$(stat -c%s "$F")
  echo "$(basename "$F"): $SZ bytes"
  if (( SZ > 50 * 1024 * 1024 )); then
    gzip -f "$F"
    echo "exceeded 50 MB -> gzipped to $F.gz"
  fi
done

echo; echo "### free disk at end"; df -h . | tail -1
echo "DONE. See results/transitions.md"
