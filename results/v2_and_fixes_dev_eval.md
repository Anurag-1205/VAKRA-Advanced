# V2 and the two runner fixes on dev-eval (2026-11-09/10)

Same setup as [baseline_dev_eval.md](baseline_dev_eval.md): `gpt-oss-120b` on Groq's paid tier,
temperature 0, official evaluator and judge, `--llm-max-retries 8`, Aayush's machine. Everything is
patched in at run time by `scripts/run_baseline.py`; upstream's code is unmodified.

| Flag | What it does | Owner |
|---|---|---|
| `--retriever hybrid` | **V2:** BM25 + MiniLM fusion (RRF) for the tool shortlist ([retrieval.py](../scripts/retrieval.py)) | Aayush |
| `--fix-tool-schema` | **Schema fix:** zero-parameter tools get an empty schema instead of LangChain's inferred `args`/`config`/`kwargs`, which Groq rejected (HTTP 400) | Anurag |
| `--refresh-tools` | **Tool refresh:** re-lists tools after Cap 1's per-item universe switch (see below) | Aayush |

## Scores

| Variant | Cap 1 (n = 60) | Cap 2 (n = 120) | Cap 3 (n = 35) | Cap 4 (n = 60) |
|---|---:|---:|---:|---:|
| V0, upstream as is | 0 of the first 7 (run stopped; bug below)† | 0.408 (49) | 0.343 (12) | 0.350 (21)\* |
| V0 + tool refresh | 0.483 (29) | – | – | – |
| V2 hybrid, 128 tools | – | 0.450 (54) | 0.371 (13) | – |
| V2 hybrid, 50 tools | – | 0.425 (51) | 0.286 (10) | – |
| **V2 hybrid, 128 tools + schema fix + tool refresh** | **0.450 (27)** | **0.558 (67)** | **0.486 (17)** | **0.317 (19)\*** |
| 95% half-width | ±0.13 | ±0.09 | ±0.17 | ±0.12 |

\* Cap 4 includes dialogues credited after an agent crash (unanswerable gold, no tool call): 3 for
V0, 1 for the new run. Without them both score **18/60 = 0.300**.

† Unmodified upstream V0 on Cap 1 was stopped to save cost once the stale-tool-list bug was clear.
With a 25-iteration cap, all 7 items it completed hit the limit without an answer
(`20261109-2309-v0-maxit25-groq-dev-eval-cap1-ABORTED-TOOLSET`). It is kept as its own row, separate
from "V0 + tool refresh", so the official baseline stays upstream's unmodified runner.

Macro average over Caps 1–4 for the last row: **0.453**.

Run ids:

- V0 + tool refresh, Cap 1 (max 25 iterations): `20261109-2325-v0rt-maxit25-groq-dev-eval-cap1`
- V2 hybrid 128 / 50, Caps 2–3: `20261109-2225-v2hybrid-groq-dev-eval`, `20261109-2225-v2hybridk50-groq-dev-eval`
- V2 + both fixes, Caps 2–4: `20261109-2356-v2hybridfixrt-groq-dev-eval`
- V2 + both fixes, Cap 1 (max 25 iterations): `20261109-2356-v2hybridfixrt-maxit25-groq-dev-eval-cap1`
- V0 rows: see [baseline_dev_eval.md](baseline_dev_eval.md).

Cap 1 runs use `--max-iterations 25` as a cost guard (upstream sets no limit). It never decided an
item with the tool refresh on: 0 recursion-limit stops in the V0 + refresh run, 2 in the last run.

## Finding 1: the schema fix recovers most of the items the bug killed

Comparing V2 (128 tools) with and without the fix, item by item:

| | Items the bug killed before | Correct after the fix | All other items |
|---|---:|---:|---|
| Cap 2 | 25 | **18** | 54 → 49 correct (+2 / −7) |
| Cap 3 | 3 | **3** | 13 → 14 correct (+4 / −3) |

- After the fix, no run shows a single `config` or `args` rejection (checked with Anurag's
  rejection script).
- Agent errors from Groq's tool-call validation fall from 22.5% (V0) to 1.7% of Cap 2 items, and
  from 17.1% to 5.7% of Cap 3 items. What remains are real model mistakes (a missing `min_year` or
  `ftr`, wrong types). V3 (argument checking and repair) targets those.
- Anurag's offline scan agrees: 152 Cap 4 tools were broken before the fix and 0 after.

## Finding 2: upstream's runner gives Cap 1 agents a stale tool list

- Cap 1's server (`RouterMCPServer`) serves two tool sets and switches when `get_data` loads an
  item's universe:
  - "slot_filling" items get generic tools (`filter_data`, `sort_data`, `aggregate_data`, …);
  - "selection" items get item-specific ones (`select_data_equal_to`, `get_Paper_Titles`, …).
- Upstream's `benchmark_runner.py` lists tools once per domain, before any switch, and never again.
  On items of the other type, every call returns "Unknown tool" and the agent loops until a limit
  (about 120 LLM calls on the first item we saw).
- **48 of our 60 `dev-eval` Cap 1 items are "selection".** In upstream's own test mapping it is
  600 of 2,085 (29%), so upstream's published runner has the same problem on the test set. The
  bug is present at upstream HEAD (`00dc68f`, unchanged since our pin).
- `--refresh-tools` re-lists the tools before each agent run and rebuilds the agent if they
  changed. Checked without LLM calls (both item types, gold chain replayed through the refreshed
  tools), then live: 0 "Unknown tool" calls in all runs since.
- The two aborted Cap 1 runs are kept as `…-ABORTED-LOOP` and `…-ABORTED-TOOLSET`.

## Finding 3: run-to-run noise is about 10% of items, even at temperature 0

Items whose input is identical between two runs still flip:

| Comparison | Items with identical input | Flipped |
|---|---:|---:|
| V0 (Oct 29) vs V2 128 (Nov 9), Caps 2–3, domains with ≤ 128 tools (shortlisting off in both) | 73 | 8 (11%) |
| V0 + refresh vs V2 + both fixes, Cap 1 (≤ 36 tools, so shortlisting is off; no Cap 1 tool hit the schema bug) | 60 | 6 (10%) |

Some of the first comparison may be provider-side change between Oct 29 and Nov 9; the second
pair ran 30 minutes apart.

Consequences:

- **A difference of a few items between two runs is not evidence.** Effects must be checked on
  the items a change can affect, as in Finding 1, not on totals alone.
- **V2 at 128 tools shows no real gain yet.** Its +5 on Cap 2 comes mostly from domains where the
  shortlist is off (+4 net there, +1 net where it differs). Hybrid retrieval's advantage is at
  small k, where its recall gap is (see [tool_recall.md](tool_recall.md)).
- **Cap 1 (0.483 → 0.450) and Cap 4 (0.300 → 0.300 without crash credit) are unchanged** within
  noise; neither fix targets them much.

## Shortlist size

128 tools was chosen over 50 for the fixed run: higher on both Cap 2 (0.450 vs 0.425) and Cap 3
(0.371 vs 0.286). Both differences are within noise, so a 50-tool run on top of the fixes is still
worth doing if cost per call matters.

## Where items are lost now (V2 + both fixes)

`scripts/failure_breakdown.py`:

| Outcome | Cap 1 | Cap 2 | Cap 3 | Cap 4 |
|---|---:|---:|---:|---:|
| Correct | 45.0% | 55.8% | 48.6% | 30.0% |
| Wrong or no answer | 28.3% | 32.5% | 37.1% | 33.3% |
| Right result or answer, not grounded | 16.7% | 9.2% | 8.6% | 18.3% |
| Agent error: context too long / request too large | 3.3% | 0.8% | – | 16.7% |
| Agent error: Groq rejected a tool call (real model mistakes) | 3.3% | 1.7% | 5.7% | – |
| Agent error: hit the 25-iteration limit | 3.3% | – | – | – |
| Credited after a crash | – | – | – | 1.7% |

Next targets, by size:

- **Groundedness failures** (9–18% of items): V5, evidence-only answers. In Cap 1, 10 items have
  the right answer but fail the groundedness judge.
- **Cap 4 context length** (17%): shorten long answers in the dialogue history (Piyush, #7).
- **Cap 4 refusals:** still 0 deliberate refusals on the 11 unanswerable dialogues; policy guard
  (V6, #10).
- **Remaining tool-call rejections** (2–6%): V3 (#8).

## Notes

- **Judge:** the same 2 Cap 1 items get "Judge Error {e}." in both Cap 1 runs; their gold answers
  are very long lists. This is upstream's judge failing on size (the `{e}` is an upstream
  formatting bug), not an authentication problem. No 401 occurred in any run. The 27 HTTP 429s
  during the fixed run were absorbed by retries; no item failed on one.
- **Cost:** **$3.25** for all of these runs (Groq dashboard), including the two stopped Cap 1
  runs and the 7-item Cap 1 check. The project total is now **$5.25** ($2.00 for the baselines in
  [baseline_dev_eval.md](baseline_dev_eval.md)).
