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
      results/_counts_*.json results/_vcf_mc_stats.json

echo; echo "### step 1: list FTP directory (authoritative filenames)"
scripts/01_list_clinvar_ftp.sh "$DATA"

echo; echo "### step 2: fetch current snapshot"
CURRENT=$(scripts/02_fetch_snapshot.sh current | tail -1)
echo "current snapshot: $CURRENT"

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
scripts/05_submission_summary_probe.sh || echo "(probe exited non-zero — see message above)"

echo; echo "### assembling report"
PYTHONPATH=scripts python3 scripts/06_report.py

echo; echo "### cleaning up current snapshot"
rm -f "$CURRENT"
rm -rf "$DATA/duckdb_tmp"

# gzip the per-variant table if it exceeds 50 MB
if [[ -f results/reclassified_pathogenic.tsv ]]; then
  SZ=$(stat -c%s results/reclassified_pathogenic.tsv)
  echo "reclassified_pathogenic.tsv: $SZ bytes"
  if (( SZ > 50 * 1024 * 1024 )); then
    gzip -f results/reclassified_pathogenic.tsv
    echo "exceeded 50 MB -> gzipped to results/reclassified_pathogenic.tsv.gz"
  fi
fi

echo; echo "### free disk at end"; df -h . | tail -1
echo "DONE. See results/transitions.md"
