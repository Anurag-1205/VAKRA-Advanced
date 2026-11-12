#!/usr/bin/env bash
# Final run (#15): the full system on dev-eval, all four tasks, then official scoring.
#
#   Caps 2-4: every flag of the final configuration (V2, schema fix, V3, tool refresh, V5,
#             short history, V6, V7, V8; each patch only acts on the tasks it applies to).
#   Cap 1:    the same flags plus --max-iterations 25, a cost guard (upstream sets no limit).
#
# The two runs go one after the other, so one machine's memory and the API rate limit are
# shared by one run at a time. About 70 minutes and $1.50 on Groq's paid tier (Nov 2026).
#
# Usage (from the repo root, containers 1-4 running, API_KEY in .env):
#   scripts/run_final.sh                  # new run ids, stamped with the current time
#   STAMP=20261113-0900 scripts/run_final.sh   # resume both runs of an interrupted final run
# If your shell is not in the docker group yet: sg docker -c scripts/run_final.sh
set -euo pipefail
cd "$(dirname "$0")/.."
PY=${PY:-.venv/bin/python}
STAMP=${STAMP:-$(date +%Y%m%d-%H%M)}
VARIANT=v2hybridfixv3rtv5shv6v7v8   # the id run_baseline.py would build from these flags
FLAGS=(--split dev-eval --retriever hybrid --top-k-tools 128 --fix-tool-schema --repair-tool-calls
       --refresh-tools --evidence-answer --short-history --policy-guard --tools-first --tool-hints
       --llm-max-retries 8)
RUN_234=$STAMP-$VARIANT-groq-dev-eval-cap234
RUN_1=$STAMP-$VARIANT-maxit25-groq-dev-eval-cap1

echo "=== $(date +%T) Caps 2-4: $RUN_234"
"$PY" scripts/run_baseline.py "${FLAGS[@]}" --caps 2 3 4 --run-id "$RUN_234"
echo "=== $(date +%T) Cap 1: $RUN_1"
"$PY" scripts/run_baseline.py "${FLAGS[@]}" --caps 1 --max-iterations 25 --run-id "$RUN_1"

for run in "$RUN_234" "$RUN_1"; do
  echo "=== $(date +%T) scoring $run"
  "$PY" scripts/evaluate.py --run-id "$run"
  "$PY" scripts/failure_breakdown.py --run-id "$run"
done
echo "=== $(date +%T) done: $RUN_234 $RUN_1"
