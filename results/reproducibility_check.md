# Reproducibility check (#18), 2026-11-14

What was checked, without new paid API calls: does every number in the report come from a run or
a script in this repo, does the code at HEAD match the code that produced the final run, and do
the README steps work from a fresh clone.

## 1. Code at HEAD is the code of the final run

- Both final runs record `git_sha 4431acb` (clean tree) and `upstream_sha 00dc68f`.
- `git diff 4431acb HEAD -- scripts/ third_party constraints.txt splits/` changes only a comment in
  `scripts/run_final.sh` (the time and cost estimate).
- The submodule `third_party/vakra` is pinned at `00dc68f`.
- `scripts/run_final.sh` passes the same flags that both runs' `config.json` record: retriever
  hybrid, k = 128, all nine change flags on, `--llm-max-retries 8`, and `--max-iterations 25` for
  Cap 1 only.

## 2. Every score in the report recomputed from per-item results

For each cell of the report's ablation table (Table 2), the score was recomputed as the mean of
the per-item scores in `runs/<run>/eval/<capability>.json`. For each run the check also confirmed
that the scored items are exactly the committed `splits/dev-eval.json` uuids and that
`config.json` has the flags the row claims.

| Row | Run | T1 | T2 | T3 | T4 |
|---|---|---:|---:|---:|---:|
| V0 | `20261029-1738-v0-groq-dev-eval`, `20261029-1925-v0-groq-dev-eval` (T4) | – | .408 | .343 | .350 |
| + tool refresh | `20261109-2325-v0rt-maxit25-groq-dev-eval-cap1` | .483 | | | |
| V2 hybrid | `20261109-2225-v2hybrid-groq-dev-eval` | | .450 | .371 | |
| + schema fix, refresh | `20261109-2356-v2hybridfixrt-groq-dev-eval` (+ `-maxit25-…-cap1`) | .450 | .558 | .486 | .317 |
| + V5 | `20261110-1559-v2hybridfixrtv5-groq-dev-eval` (+ `-maxit25-…-cap1`) | .583 | .583 | .486 | .317 |
| + short history | `20261110-2302-v2hybridfixrtv5sh-groq-dev-eval-cap4` | | | | .433 |
| + V6 | `20261111-1610-v2hybridfixrtv5shv6-groq-dev-eval-cap4` | | | | .500 |
| + V7 | `20261112-1144-v2hybridfixrtv5v7-groq-dev-eval-cap23` | | .633 | .486 | |
| + V8 | `20261112-1632-v2hybridfixrtv5v7v8-groq-dev-eval-cap23` | | .650 | .486 | |
| **Final** | `20261112-1833-v2hybridfixv3rtv5shv6v7v8-groq-dev-eval-cap234` (+ `-maxit25-…-cap1`) | .500 | .625 | .543 | .583 |

**All 24 cells match the report, and the final macro is 0.5628 (0.563).** Every run scored
exactly the dev-eval items (60 / 120 / 35 / 60).

Caveat: five runs record a `-dirty` commit: the Nov 9 runs (V2, + tool refresh, and both
+ fixes runs) and the V8 run. They ran while the patch they test was not yet committed. The code
of each patch is in the history, but those runs cannot be tied to one exact commit. The final run
(and V0, V5, short history, V6, V7) can.

## 3. Offline numbers re-run (no LLM calls)

| Check | Command | Result |
|---|---|---|
| Splits | `python scripts/make_splits.py --check` | `splits OK` |
| V6 domain topics | `python scripts/policy_guard.py --write-topics` | rebuilt file identical to the committed one |
| Retrieval recall (report Table 1, V2) | `python scripts/tool_recall.py --split dev-eval --caps 2 3` | identical to [tool_recall.md](tool_recall.md): R@32 0.925 / 0.958 (T2, MiniLM / hybrid), 0.714 / 0.800 (T3); R@128 0.992 for all on T2 (one gold tool is not in the catalog), 0.943 / 1.000 on T3 |
| V4 per-hop upper bound | `python scripts/hop_recall.py --split dev-eval` | identical to [tool_recall.md](tool_recall.md) |

The recall re-run found one error in the 2-page report: it said R@128 is full "for all
retrievers", but MiniLM (the baseline's retriever) reaches 0.943 on Task 3. Corrected to "full
(baseline 94.3% on Task 3)".

## 4. The other numbers in the report

Each remaining number was traced to its source: the Phase 1 rejection rate (22.5%) to
[baseline_dev_eval.md](baseline_dev_eval.md); schema fix (18 of 25, 3 of 3), stale tool list (48 of
60; 600 of 2,085), long histories (10 dialogues, 9.4M characters, +6), V3 (3 of 4; 5 → 1), V7
(28 → 3, 13 → 0), V8 (3 Task 3 items, 0 of 4 in Task 2) and the final-run comparison (−5/−3/+2/+5,
7 of 275 crashes) to [v2_and_fixes_dev_eval.md](v2_and_fixes_dev_eval.md); V5 (10 of 25, 35
controls) to [groundedness_dev_eval.md](groundedness_dev_eval.md); V6 (65/65, 68/68, 0/79, 11
refusals) to `scripts/policy_guard.py` and Finding 5; the error analysis (116 failures, 76 read,
13 of 38, 15 of 76, 7 of 15) to [error_analysis.md](error_analysis.md); the cost ($10.82) to the
Groq dashboard, recorded in [POST_MID_WORK.md](../POST_MID_WORK.md).

One gap fixed: the "+ V5" row's run ids were missing from the run list in
[v2_and_fixes_dev_eval.md](v2_and_fixes_dev_eval.md) (they were only in
[groundedness_dev_eval.md](groundedness_dev_eval.md)); now listed.

## 5. README steps from a fresh clone

A fresh `git clone --recurse-submodules https://github.com/Anurag-1205/VAKRA-Advanced.git`
(HEAD `5afcfc8`, submodule `00dc68f`) into an empty directory, then README step 2 exactly as written
in a new venv: CPU torch, `pip install -c constraints.txt -e "third_party/vakra[init]" -r
third_party/vakra/requirements_benchmark.txt`, `pip install ijson`. Result: installs cleanly
(torch 2.15.0+cpu); `langgraph`, `mcp` and `sentence_transformers` import; `scripts/run_baseline.py
--help` runs.

With that fresh clone and venv (data, runs and tool catalogs linked from this machine instead of
re-downloading ~6 GB):

| Check | Result |
|---|---|
| `make_splits.py --check` | `splits OK` |
| Table 2 recomputed from `runs/` (section 2's script) | 24 of 24 cells match; macro 0.5628 |
| `failure_breakdown.py` on the final run | same counts as in [v2_and_fixes_dev_eval.md](v2_and_fixes_dev_eval.md) |
| `tool_recall.py --split dev-eval --caps 2 3` | identical to section 3 |

## Not re-run

- **New agent runs and the judges** (README steps 3, 6, 7): they cost Groq money and their results
  vary by about 10% of items between identical runs, so a re-run would not reproduce the exact
  scores anyway; the per-item outputs of every reported run are kept under `runs/`.
- **Data download and image build** (steps 4–5): already done on this machine with the same
  commands; the containers used for the recall re-run are the ones built by them.
