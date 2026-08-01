#!/usr/bin/env bash
# List the ClinVar tab_delimited directory and its archive/ subdirectory.
#
# We NEVER hardcode snapshot filenames. This script prints the authoritative
# listing so that 02_fetch_snapshot.sh can resolve exact names from it.
# Output is saved to data/listing_*.txt for the fetch step to consume.
set -euo pipefail

ROOT="https://ftp.ncbi.nlm.nih.gov/pub/clinvar"
BASE="$ROOT/tab_delimited"
VCF_BASE="$ROOT/vcf_GRCh38"
OUT="${1:-data}"
mkdir -p "$OUT"

fetch_listing () {
  local url="$1" dest="$2"
  echo "=== LISTING: $url ==="
  if ! curl -sSfL --max-time 300 --retry 3 --retry-delay 2 "$url/" -o "$dest.html"; then
    echo "FATAL: could not list $url" >&2
    echo "If this is a 403 from the agent proxy, ftp.ncbi.nlm.nih.gov is not on" >&2
    echo "the session's egress allowlist. Stop and fix the network policy." >&2
    exit 1
  fi
  # Extract href targets and their listed size/date columns.
  sed -e 's/<[^>]*>/\t/g' "$dest.html" \
    | tr -s '\t' '\t' | sed -e 's/^\t*//' -e '/^$/d' > "$dest"
  cat "$dest"
  echo
}

fetch_listing "$BASE"         "$OUT/listing_tab_delimited.txt"
fetch_listing "$BASE/archive" "$OUT/listing_archive.txt"
fetch_listing "$VCF_BASE"     "$OUT/listing_vcf_grch38.txt"

echo "=== candidate variant_summary files (current) ==="
grep -o 'variant_summary[^"[:space:]]*\.txt\.gz' "$OUT/listing_tab_delimited.txt" | sort -u || true
echo "=== candidate variant_summary files (archive, loose) ==="
grep -o 'variant_summary[^"[:space:]]*\.txt\.gz' "$OUT/listing_archive.txt" | sort -u || true
# ClinVar keeps only ~18 months loose in archive/; older snapshots live in
# per-year subdirectories, which 02_fetch_snapshot.sh lists on demand.
echo "=== archive/ year subdirectories (older snapshots live here) ==="
grep -oE '\b(19|20)[0-9]{2}/' "$OUT/listing_archive.txt" | sort -u || true
echo "=== submission_summary files ==="
grep -o 'submission_summary[^"[:space:]]*\.txt\.gz' "$OUT/listing_tab_delimited.txt" | sort -u || true
echo "=== GRCh38 VCF files (source of molecular consequence via MC) ==="
grep -o 'clinvar[^"[:space:]]*\.vcf\.gz' "$OUT/listing_vcf_grch38.txt" | sort -u || true
