#!/usr/bin/env bash
# Build the flat join export for external contamination analysis.
#
# Fetches the baseline and the three endpoints that define the survival
# horizons, plus the dated VCF for molecular consequence, and writes
# data/exports/vus_hindsight_for_am_join.csv with a README recording the exact
# inputs and their md5s.
set -euo pipefail
cd "$(dirname "$0")/.."

DATA="${DATA_DIR:-data}"
export DATA_DIR="$DATA"
OUT="${EXPORT_OUT:-data/exports/vus_hindsight_for_am_join.csv}"
BASELINE_MONTH="${BASELINE_MONTH:-2021-06}"
# label:months for each endpoint, ascending.
ENDPOINT_SPEC="${ENDPOINT_SPEC:-2022-12:18 2024-06:36 2026-07:61}"
export VCF_DATE="${VCF_DATE:-20260728}"

mkdir -p "$DATA" results "$(dirname "$OUT")"
echo "### export for external join"
python3 -c "import duckdb; print('duckdb', duckdb.__version__)"
df -h . | tail -1

rm -f results/_manifest.tsv
[[ -s "$DATA/listing_tab_delimited.txt" ]] || scripts/01_list_clinvar_ftp.sh "$DATA" >/dev/null

echo; echo "### molecular consequence from the dated VCF"
VCF=$(scripts/02_fetch_snapshot.sh vcf | tail -1)
PYTHONPATH=scripts python3 scripts/03b_extract_mc.py "$VCF" \
    --out "$DATA/consequence_map.parquet"
rm -f "$VCF" "$VCF.md5"
df -h . | tail -1

echo; echo "### baseline $BASELINE_MONTH"
BASE=$(scripts/02_fetch_snapshot.sh archive "$BASELINE_MONTH" | tail -1)

EP_ARGS=()
for SPEC in $ENDPOINT_SPEC; do
  MONTH="${SPEC%%:*}"; MONTHS="${SPEC##*:}"
  echo; echo "### endpoint $MONTH (+$MONTHS months)"
  EP=$(scripts/02_fetch_snapshot.sh archive "$MONTH" | tail -1)
  EP_ARGS+=(--endpoint "$EP:$MONTH:$MONTHS")
done

echo; echo "### building the export"
PYTHONPATH=scripts python3 scripts/12_export_for_join.py \
    --baseline "$BASE:$BASELINE_MONTH" \
    "${EP_ARGS[@]}" \
    --consequence-map "$DATA/consequence_map.parquet" \
    --out "$OUT"

# Raw snapshots go; the export and its README stay.
rm -f "$DATA"/variant_summary_*.txt.gz "$DATA"/variant_summary_*.txt.gz.md5
rm -f "$DATA/consequence_map.parquet"
rm -rf "$DATA/duckdb_tmp"

echo; echo "### produced"
ls -lh "$(dirname "$OUT")"
SZ=$(stat -c%s "$OUT")
echo "$OUT: $SZ bytes"
if (( SZ > 50 * 1024 * 1024 )); then
  gzip -f "$OUT"
  echo "exceeded 50 MB -> gzipped to $OUT.gz"
fi
df -h . | tail -1
