#!/usr/bin/env bash
# Fixed-cohort survival curve: freeze one VUS cohort, follow it through several
# later snapshots.
#
# Called from run_all.sh while the current snapshot and the consequence map are
# still on disk, so only the extra endpoints need downloading.
#
#   run_survival.sh <current_snapshot> <consequence_map.parquet>
set -euo pipefail
cd "$(dirname "$0")/.."

CURRENT="${1:?usage: run_survival.sh <current_snapshot> <consequence_map>}"
CONSMAP="${2:?usage: run_survival.sh <current_snapshot> <consequence_map>}"
DATA="${DATA_DIR:-data}"
export DATA_DIR="$DATA"

COHORT_MONTH="${SURVIVAL_BASELINE:-2021-06}"
ENDPOINTS="${SURVIVAL_ENDPOINTS:-2022-12 2024-06}"

echo "### fixed-cohort survival: baseline $COHORT_MONTH, endpoints $ENDPOINTS + current"

# The cohort is built once and reused; the raw snapshot goes away immediately.
BASE=$(scripts/02_fetch_snapshot.sh archive "$COHORT_MONTH" | tail -1)
PYTHONPATH=scripts python3 scripts/07_survival.py \
    --baseline "$BASE" --baseline-label "$COHORT_MONTH" \
    --out-cohort "$DATA/cohort.parquet"
rm -f "$BASE" "$BASE.md5"
df -h . | tail -1

for MONTH in $ENDPOINTS; do
  echo; echo "--- endpoint $MONTH ---"
  EP=$(scripts/02_fetch_snapshot.sh archive "$MONTH" | tail -1)
  PYTHONPATH=scripts python3 scripts/07_survival.py \
      --cohort "$DATA/cohort.parquet" --baseline-label "$COHORT_MONTH" \
      --endpoint "$EP" --endpoint-label "$MONTH" \
      --consequence-map "$CONSMAP"
  rm -f "$EP" "$EP.md5"
  df -h . | tail -1
done

# The current snapshot is still on disk from the main pipeline. Its label comes
# from the release stamp recorded in the manifest, so the x-axis reflects the
# real release date rather than the day the job happened to run.
CUR_LABEL=$(awk -F'\t' '$1=="current"{print $5}' results/_manifest.tsv \
            | tail -1 \
            | python3 -c "
import sys, datetime
raw = sys.stdin.read().strip()
try:
    print(datetime.datetime.strptime(raw[:25].strip(), '%a, %d %b %Y %H:%M:%S').strftime('%Y-%m'))
except Exception:
    print('')
")
if [[ -z "$CUR_LABEL" ]]; then
  echo "FATAL: could not derive the current snapshot's release month from" >&2
  echo "results/_manifest.tsv — refusing to guess a date for the x-axis." >&2
  exit 1
fi
echo; echo "--- endpoint current ($CUR_LABEL) ---"
PYTHONPATH=scripts python3 scripts/07_survival.py \
    --cohort "$DATA/cohort.parquet" --baseline-label "$COHORT_MONTH" \
    --endpoint "$CURRENT" --endpoint-label "$CUR_LABEL" \
    --consequence-map "$CONSMAP"

echo; echo "### rendering survival report"
PYTHONPATH=scripts python3 scripts/08_survival_report.py
rm -f "$DATA/cohort.parquet"
