#!/usr/bin/env bash
# Fetch one ClinVar snapshot by EXACT filename, resolved from the live listing.
#
# Usage:
#   02_fetch_snapshot.sh current                 # newest variant_summary.txt.gz
#   02_fetch_snapshot.sh archive 2021-06         # archived baseline for that month
#   02_fetch_snapshot.sh vcf                     # GRCh38 clinvar.vcf.gz (MC field)
#
# Refuses to invent a filename: if the requested month is not present in the
# archive listing, it prints the available months and exits non-zero.
set -euo pipefail

ROOT="https://ftp.ncbi.nlm.nih.gov/pub/clinvar"
BASE="$ROOT/tab_delimited"
VCF_BASE="$ROOT/vcf_GRCh38"
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
elif [[ "$MODE" == "vcf" ]]; then
  # Prefer the DATED clinvar_YYYYMMDD.vcf.gz over the rolling clinvar.vcf.gz.
  # NCBI overwrites the rolling name in place, so a run pinned to it cannot be
  # reproduced once superseded — the same defect the endpoint snapshot had.
  # The dated copy sits beside it and keeps its bytes. VCF_DATE pins an exact
  # one; otherwise the newest dated file in the listing is used.
  ALL_VCF=$(grep -oE 'clinvar_[0-9]{8}\.vcf\.gz' "$DATA/listing_vcf_grch38.txt" \
            | sort -u || true)
  if [[ -n "${VCF_DATE:-}" ]]; then
    NAME=$(printf '%s\n' "$ALL_VCF" | grep -x "clinvar_${VCF_DATE}\.vcf\.gz" | head -1 || true)
    if [[ -z "$NAME" ]]; then
      echo "FATAL: no clinvar_${VCF_DATE}.vcf.gz in the vcf_GRCh38 listing." >&2
      echo "Dated VCFs available at this path:" >&2
      printf '%s\n' "$ALL_VCF" >&2
      echo "Older releases are filed under vcf_GRCh38/archive_2.0/<YEAR>/." >&2
      exit 1
    fi
  else
    NAME=$(printf '%s\n' "$ALL_VCF" | sort | tail -1)
  fi
  if [[ -z "$NAME" ]]; then
    echo "FATAL: no dated clinvar_YYYYMMDD.vcf.gz found in the vcf_GRCh38" >&2
    echo "listing. Refusing to fall back to the rolling clinvar.vcf.gz, which" >&2
    echo "cannot be reproduced once NCBI overwrites it. Inspect the listing:" >&2
    grep -o 'clinvar[^"[:space:]]*\.vcf\.gz' "$DATA/listing_vcf_grch38.txt" | sort -u >&2
    exit 1
  fi
  URL="$VCF_BASE/$NAME"
else
  [[ -n "$MONTH" ]] || { echo "FATAL: archive mode needs YYYY-MM" >&2; exit 1; }
  YEAR="${MONTH%%-*}"

  # ClinVar keeps roughly the last 18 months loose in archive/ and files
  # everything older under archive/<YEAR>/. Look in the flat listing first,
  # then in the year subdirectory. Both are read from the live listing.
  # Prefer an exact variant_summary_<MONTH>.txt.gz; fall back to a substring
  # match so an older naming convention still resolves. The candidate list is
  # materialised first — piping into `grep A || grep B` would let the first
  # grep swallow stdin, leaving the fallback nothing to read.
  pick_name () {  # $1 = listing file
    local listing="$1" all exact
    all=$(grep -o 'variant_summary[^"[:space:]]*\.txt\.gz' "$listing" | sort -u || true)
    if [[ -z "$all" ]]; then
      return 0
    fi
    exact=$(printf '%s\n' "$all" | grep -x "variant_summary_${MONTH}\.txt\.gz" || true)
    if [[ -n "$exact" ]]; then
      printf '%s\n' "$exact" | head -1
      return 0
    fi
    printf '%s\n' "$all" | grep -- "$MONTH" | head -1 || true
  }

  NAME=$(pick_name "$DATA/listing_archive.txt")
  if [[ -n "$NAME" ]]; then
    URL="$BASE/archive/$NAME"
  else
    YEAR_LISTING="$DATA/listing_archive_$YEAR.txt"
    if [[ ! -s "$YEAR_LISTING" ]]; then
      echo "'$MONTH' is not in the flat archive listing; reading archive/$YEAR/ ..."
      if ! curl -sSfL --max-time 300 --retry 3 --retry-delay 2 \
             "$BASE/archive/$YEAR/" -o "$YEAR_LISTING.html"; then
        echo "FATAL: no archived variant_summary matching '$MONTH', and" >&2
        echo "archive/$YEAR/ could not be listed (does that year exist?)." >&2
        echo "Months available loose in archive/:" >&2
        grep -o 'variant_summary[^"[:space:]]*\.txt\.gz' \
             "$DATA/listing_archive.txt" | sort -u >&2
        exit 1
      fi
      sed -e 's/<[^>]*>/\t/g' "$YEAR_LISTING.html" \
        | tr -s '\t' '\t' | sed -e 's/^\t*//' -e '/^$/d' > "$YEAR_LISTING"
    fi
    NAME=$(pick_name "$YEAR_LISTING")
    if [[ -z "$NAME" ]]; then
      echo "FATAL: no variant_summary matching '$MONTH' in archive/$YEAR/." >&2
      echo "Available in archive/$YEAR/:" >&2
      grep -o 'variant_summary[^"[:space:]]*\.txt\.gz' "$YEAR_LISTING" | sort -u >&2
      exit 1
    fi
    URL="$BASE/archive/$YEAR/$NAME"
  fi
fi

echo "Resolved filename from listing: $NAME"
echo "URL: $URL"

# Report remote size before committing disk to it, and capture the release
# stamp. `variant_summary.txt.gz` and `clinvar.vcf.gz` are ROLLING filenames —
# the same URL serves different data every release — so Last-Modified plus the
# md5 is what actually pins a published figure to a reproducible input.
HEADERS=$(curl -sSI --max-time 120 -L "$URL")
SIZE=$(echo "$HEADERS" | awk 'BEGIN{IGNORECASE=1}/^content-length:/{v=$2}END{gsub("\r","",v);print v}')
LASTMOD=$(echo "$HEADERS" | awk 'BEGIN{IGNORECASE=1}/^last-modified:/{sub(/^[^:]*: */,"");v=$0}END{gsub("\r","",v);print v}')
if [[ -n "${SIZE:-}" ]]; then
  echo "Remote size: $SIZE bytes ($(awk -v b="$SIZE" 'BEGIN{printf "%.2f", b/1073741824}') GiB)"
fi
[[ -n "${LASTMOD:-}" ]] && echo "Release stamp (Last-Modified): $LASTMOD"
echo "Free disk before download:"; df -h "$DATA" | tail -1

curl -sSfL --max-time 3600 --retry 4 --retry-delay 2 --retry-all-errors \
     -o "$DATA/$NAME" "$URL"

# Integrity: the file must be a complete, valid gzip stream.
if ! gzip -t "$DATA/$NAME"; then
  echo "FATAL: downloaded file failed gzip integrity check: $DATA/$NAME" >&2
  exit 1
fi

# NCBI publishes a .md5 beside most files. Verify when one exists, so the
# provenance of a published figure is checkable rather than assumed.
MD5=""
if curl -sSfL --max-time 120 "$URL.md5" -o "$DATA/$NAME.md5" 2>/dev/null; then
  EXPECTED=$(awk '{print $1}' "$DATA/$NAME.md5")
  ACTUAL=$(md5sum "$DATA/$NAME" | awk '{print $1}')
  if [[ "$EXPECTED" != "$ACTUAL" ]]; then
    echo "FATAL: md5 mismatch for $NAME (expected $EXPECTED, got $ACTUAL)" >&2
    exit 1
  fi
  echo "md5 verified: $ACTUAL"
  MD5="$ACTUAL"
else
  echo "note: no .md5 published for $NAME; relied on gzip integrity check"
  MD5=$(md5sum "$DATA/$NAME" | awk '{print $1}')
fi

# Record exactly which bytes produced this run's numbers. Without this a
# reviewer re-fetching a rolling filename months later cannot tell whether a
# mismatch means a bug or simply a newer ClinVar release.
MANIFEST="${MANIFEST_PATH:-results/_manifest.tsv}"
mkdir -p "$(dirname "$MANIFEST")"
[[ -s "$MANIFEST" ]] || printf 'role\tfilename\turl\tbytes\tlast_modified\tmd5\n' > "$MANIFEST"
printf '%s\t%s\t%s\t%s\t%s\t%s\n' \
  "${MODE}${MONTH:+ $MONTH}" "$NAME" "$URL" \
  "$(stat -c%s "$DATA/$NAME")" "${LASTMOD:-unknown}" "${MD5:-unknown}" >> "$MANIFEST"

echo "Downloaded OK: $DATA/$NAME ($(stat -c%s "$DATA/$NAME") bytes)"
echo "$DATA/$NAME"
