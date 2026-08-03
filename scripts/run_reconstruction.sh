#!/usr/bin/env bash
# Frozen-date reconstruction, validated against a real snapshot.
#
# Rebuilds ClinVar's aggregate classification as of a past date from submission
# dates, then compares it to the archived snapshot for that same date. The
# comparison is the point: it measures how far the reconstruction lands from
# the truth, rather than assuming it lands close.
#
#   run_reconstruction.sh [YYYY-MM]        # default 2021-06
set -euo pipefail
cd "$(dirname "$0")/.."

MONTH="${1:-${RECON_MONTH:-2021-06}}"
DATA="${DATA_DIR:-data}"
export DATA_DIR="$DATA"
mkdir -p "$DATA" results

echo "### frozen-date reconstruction, validated at $MONTH"
python3 -c "import duckdb; print('duckdb', duckdb.__version__)"
df -h . | tail -1

[[ -s "$DATA/listing_tab_delimited.txt" ]] || scripts/01_list_clinvar_ftp.sh "$DATA" >/dev/null

# The archived snapshot for MONTH is the ground truth. Fetch it first so the
# run fails early if the month is unavailable, before spending the big download.
echo; echo "### fetching the real snapshot for $MONTH"
ACTUAL=$(scripts/02_fetch_snapshot.sh archive "$MONTH" | tail -1)

# The cutoff is the snapshot's own release date: submissions evaluated after
# ClinVar built that file cannot have informed it.
AS_OF=$(awk -F'\t' -v m="archive $MONTH" '$1==m{print $5}' results/_manifest.tsv \
        | tail -1 \
        | python3 -c "
import sys, datetime
raw = sys.stdin.read().strip()
try:
    print(datetime.datetime.strptime(raw[:25].strip(), '%a, %d %b %Y %H:%M:%S').strftime('%Y-%m-%d'))
except Exception:
    print('')
")
if [[ -z "$AS_OF" ]]; then
  echo "FATAL: could not read the release date of the $MONTH snapshot from" >&2
  echo "results/_manifest.tsv — refusing to guess the reconstruction cutoff." >&2
  exit 1
fi
echo "cutoff date taken from the snapshot's own release stamp: $AS_OF"

echo; echo "### fetching submission_summary"
SUBS="$DATA/submission_summary.txt.gz"
if [[ ! -s "$SUBS" ]]; then
  BASE="https://ftp.ncbi.nlm.nih.gov/pub/clinvar/tab_delimited"
  SIZE=$(curl -sSI --max-time 120 -L "$BASE/submission_summary.txt.gz" \
         | awk 'BEGIN{IGNORECASE=1}/^content-length:/{v=$2}END{gsub("\r","",v);print v}')
  printf 'remote size: %s bytes (%.2f GiB)\n' "$SIZE" \
    "$(awk -v b="$SIZE" 'BEGIN{print b/1073741824}')"
  curl -sSfL --max-time 3600 --retry 4 --retry-delay 2 --retry-all-errors \
       -o "$SUBS" "$BASE/submission_summary.txt.gz"
  gzip -t "$SUBS"
fi
echo "submission_summary: $(stat -c%s "$SUBS") bytes"

echo; echo "### reconstructing as of $AS_OF"
PYTHONPATH=scripts python3 scripts/09_reconstruct.py \
    --submissions "$SUBS" --as-of "$AS_OF" \
    --out "$DATA/reconstructed_$MONTH.parquet"

echo; echo "### validating against the real $MONTH snapshot"
PYTHONPATH=scripts python3 scripts/10_validate_reconstruction.py \
    --reconstructed "$DATA/reconstructed_$MONTH.parquet" \
    --actual "$ACTUAL" --label "$MONTH"

rm -f "$ACTUAL" "$ACTUAL.md5" "$SUBS" "$DATA/reconstructed_$MONTH.parquet"
rm -rf "$DATA/duckdb_tmp"
echo; echo "### free disk at end"; df -h . | tail -1
echo "DONE. See results/_reconstruction_validation_$MONTH.json"
