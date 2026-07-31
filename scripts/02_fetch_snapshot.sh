#!/usr/bin/env bash
# Fetch one ClinVar snapshot by EXACT filename, resolved from the live listing.
#
# Usage:
#   02_fetch_snapshot.sh current                 # newest variant_summary.txt.gz
#   02_fetch_snapshot.sh archive 2021-06         # archived baseline for that month
#
# Refuses to invent a filename: if the requested month is not present in the
# archive listing, it prints the available months and exits non-zero.
set -euo pipefail

BASE="https://ftp.ncbi.nlm.nih.gov/pub/clinvar/tab_delimited"
MODE="${1:?usage: 02_fetch_snapshot.sh current|archive [YYYY-MM]}"
MONTH="${2:-}"
DATA="${DATA_DIR:-data}"
mkdir -p "$DATA"

[[ -s "$DATA/listing_tab_delimited.txt" ]] || scripts/01_list_clinvar_ftp.sh "$DATA" >/dev/null

if [[ "$MODE" == "current" ]]; then
  URL="$BASE/variant_summary.txt.gz"
  NAME="variant_summary.txt.gz"
  grep -q 'variant_summary\.txt\.gz' "$DATA/listing_tab_delimited.txt" \
    || { echo "FATAL: variant_summary.txt.gz not in live listing" >&2; exit 1; }
else
  [[ -n "$MONTH" ]] || { echo "FATAL: archive mode needs YYYY-MM" >&2; exit 1; }
  NAME=$(grep -o 'variant_summary[^"[:space:]]*\.txt\.gz' "$DATA/listing_archive.txt" \
         | sort -u | grep -- "$MONTH" | head -1 || true)
  if [[ -z "$NAME" ]]; then
    echo "FATAL: no archived variant_summary matching '$MONTH'." >&2
    echo "Available archived snapshots:" >&2
    grep -o 'variant_summary[^"[:space:]]*\.txt\.gz' "$DATA/listing_archive.txt" | sort -u >&2
    exit 1
  fi
  URL="$BASE/archive/$NAME"
fi

echo "Resolved filename from listing: $NAME"
echo "URL: $URL"

# Report remote size before committing disk to it.
SIZE=$(curl -sSI --max-time 120 -L "$URL" | awk 'BEGIN{IGNORECASE=1}/^content-length:/{v=$2}END{gsub("\r","",v);print v}')
if [[ -n "${SIZE:-}" ]]; then
  echo "Remote size: $SIZE bytes ($(awk -v b="$SIZE" 'BEGIN{printf "%.2f", b/1073741824}') GiB)"
fi
echo "Free disk before download:"; df -h "$DATA" | tail -1

curl -sSfL --max-time 3600 --retry 4 --retry-delay 2 --retry-all-errors \
     -o "$DATA/$NAME" "$URL"

# Integrity: the file must be a complete, valid gzip stream.
if ! gzip -t "$DATA/$NAME"; then
  echo "FATAL: downloaded file failed gzip integrity check: $DATA/$NAME" >&2
  exit 1
fi

echo "Downloaded OK: $DATA/$NAME ($(stat -c%s "$DATA/$NAME") bytes)"
echo "$DATA/$NAME"
