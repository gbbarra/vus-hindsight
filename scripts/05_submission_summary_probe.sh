#!/usr/bin/env bash
# Probe submission_summary.txt.gz BEFORE downloading it.
#
# Question this answers: does submission_summary carry per-submission dates that
# would let us reconstruct the evidence available at a frozen past date?
#
# Reports the remote size first and refuses to download past a threshold
# (default 2 GB) without an explicit --confirm, per the analysis protocol.
set -euo pipefail

BASE="https://ftp.ncbi.nlm.nih.gov/pub/clinvar/tab_delimited"
NAME="submission_summary.txt.gz"
DATA="${DATA_DIR:-data}"
LIMIT_BYTES=$((2 * 1024 * 1024 * 1024))
CONFIRM="${1:-}"
mkdir -p "$DATA"

echo "=== HEAD $BASE/$NAME ==="
HEADERS=$(curl -sSI --max-time 120 -L "$BASE/$NAME")
echo "$HEADERS"
SIZE=$(echo "$HEADERS" | awk 'BEGIN{IGNORECASE=1}/^content-length:/{v=$2}END{gsub("\r","",v);print v}')

if [[ -z "${SIZE:-}" ]]; then
  echo "FATAL: server did not report Content-Length; cannot size-check." >&2
  exit 1
fi
printf 'Remote size: %s bytes (%.2f GiB)\n' "$SIZE" "$(awk -v b="$SIZE" 'BEGIN{print b/1073741824}')"

if (( SIZE > LIMIT_BYTES )) && [[ "$CONFIRM" != "--confirm" ]]; then
  echo
  echo "STOP: submission_summary.txt.gz exceeds the 2 GB threshold."
  echo "Re-run with --confirm to download anyway."
  exit 3
fi

curl -sSfL --max-time 3600 --retry 4 --retry-delay 2 --retry-all-errors \
     -o "$DATA/$NAME" "$BASE/$NAME"
gzip -t "$DATA/$NAME"

echo
echo "=== header + first 3 data rows ==="
zcat "$DATA/$NAME" | head -20 | sed -e 's/^/  /'

echo
echo "=== date-bearing columns ==="
# The header is the last commented line before data begins.
zcat "$DATA/$NAME" | grep -m1 '^#Variation\|^#VariationID' | tr '\t' '\n' | nl \
  | grep -i 'date\|submitted\|evaluated' || \
  echo "  (no column name matched date/submitted/evaluated — inspect header above)"
