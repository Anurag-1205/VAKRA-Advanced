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
| + V5 evidence-only answer (`--evidence-answer`, Nov 10; see [groundedness_dev_eval.md](groundedness_dev_eval.md)) | 0.583 (35) | 0.583 (70) | 0.486 (17) | 0.317 (19)\* |
| + short history (`--short-history`, Cap 4 only, Nov 10; see Finding 4) | – | – | – | **0.433 (26)\*** |
| + V6 policy guard (`--policy-guard`, Cap 4 only, Nov 11; see Finding 5) | – | – | – | **0.500 (30)** |
| 95% half-width | ±0.13 | ±0.09 | ±0.17 | ±0.12 |

\* Cap 4 includes dialogues credited after an agent crash (unanswerable gold, no tool call): 3 for
V0, 1 for the new run. Without them both score **18/60 = 0.300**. The short-history run also has 1 (25/60 = 0.417 without it). The V6 run has none: that dialogue's gold refusal is now credited because the guard refused on purpose.

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
- + V5 + short history, Cap 4: `20261110-2302-v2hybridfixrtv5sh-groq-dev-eval-cap4`
- + V5 + short history + V6, Cap 4: `20261111-1610-v2hybridfixrtv5shv6-groq-dev-eval-cap4`
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

## Finding 4: long gold answers in the Cap 4 history (#7)

Upstream (`BenchmarkItem.from_dict` in `benchmark/runner_helpers.py`) puts every earlier turn's
gold answer into the dialogue history as `str(answer)`, however long. In 10 of the 60 `dev-eval`
dialogues (5 authors, 5 menu) an earlier answer is a whole table: 1.3M to 9.4M characters, up to
258k rows. The first LLM call is rejected ("Please reduce the length of the messages") before
any tool is called. This was the 16.7% "context too long" row below.

`--short-history` (`scripts/short_history.py`) keeps each earlier answer over 2,000 characters
to its first rows plus a note: "... (61223 rows in total; only the first 75 are shown)". The
agent can still call tools for the rest, and the evaluator never reads the history. Checked
offline through upstream's own `from_dict` (`python scripts/short_history.py --run-id <run>`):

- 30 of the 60 dialogues are shortened; the largest history goes from about 2.3M tokens to 1.6k.
- Queries, turn ids, policy instructions and message order are unchanged.
- In the follow-up turns of these dialogues the earlier list is not needed (for example, "List
  down the name of dishes from menus created in April", then "What is the highest price of the
  dish 'Clear green turtle'?").

Live run (Cap 4 only, the V5 setup plus `--short-history`), compared item by item with the V5
run:

| Dialogues | n | Correct before | Correct after | Won / lost |
|---|---:|---:|---:|---|
| Failed before: history too long | 10 | 0 | **6** | +6 / −0 |
| Shortened, fit before (≤ 73k tokens of history) | 20 | 10 | 11 | +3 / −2 |
| Not shortened | 30 | 9 | 9 | +2 / −2 |
| **Total** | **60** | **19** | **26** | |

- **0 "context too long" errors** (10 before). The 2 agent errors left are a tool response too
  large for Groq (HTTP 413, a single-turn hockey dialogue; in every run so far) and one tool call
  Groq rejected for a bad parameter.
- **+7 dialogues (0.317 → 0.433)**: +6 are the recovered dialogues; the other 50 are +1 net,
  i.e. noise. Shortening a history that already fit neither helps nor hurts.
- **Macro over Caps 1–4 with V5 and short history: 0.521** (Caps 1–3 from the V5 run; the patch
  changes only multi-turn histories, so it does not affect them).

## Finding 5: following Cap 4's tool policies (V6, #10)

Each Cap 4 dialogue may carry a tool policy in `additional_instructions`. Upstream only states it
to the model as a system message, and **for single-turn dialogues not at all** (in
`LangGraphReActAgent.run` the policy is added only when the input is a message list). In the V5
run the agent followed none of them: 10 failed dialogues called a data tool where only document
retrievers were allowed, and 3 called a retriever where retrievers were forbidden
(`scripts/diagnostics.py`).

Every policy in the 898 training dialogues is one of 4 templates over 12 topics. Document
retrievers are the `query_*` tools. The gold answer is "I can not answer." **exactly** when only
retrievers are allowed and the policy applies: always for the global form (65 / 65), and for the
topic form when the topic is the domain's (68 / 68; 0 of the 79 others). Upstream's scorer gives
full credit to such a refusal when no tool is called.

`--policy-guard` (`scripts/policy_guard.py`):

| Policy | Action |
|---|---|
| Only retrievers, applies | answer "I can not answer." with no tool call |
| No retrievers, applies | the agent runs without the `query_*` tools |
| Anything else | unchanged |

A topic policy applies when it names the domain's topic. Known domains are looked up in
`splits/cap4_domain_topics.json`, built from the gold of `train-rest` and `dev-seen` only, so no
held-out (dev-eval) domain is in it. Other domains, including all of dev-eval's, get their topic
from the agent's LLM, once per domain, from the domain's name and tool names. That call is right
for 25 of the 29 labelled training domains (`policy_guard.py --check`). It disagrees with the
benchmark on 4: book_publishing_company, music_tracker and talkingdata, plus world (Finance
instead of Geography). The world disagreement changes no dev-eval decision.

Live run (Cap 4 only, the short-history setup plus `--policy-guard`), item by item against the
short-history run:

| Dialogues | n | Correct before | Correct after | Won / lost |
|---|---:|---:|---:|---|
| Guard refused (all 11 gold refusals, nothing else) | 11 | 5 | **11** | +6 / −0 |
| Run without retrievers | 5 | – | – | +1 / −0 |
| Unchanged | 44 | – | – | +1 / −4 |
| **Total** | **60** | **26** | **30** | |

- **The guard refused exactly the 11 dialogues whose gold is a refusal**, as the offline
  simulation predicted. 5 of them were already credited, through a crash, a lenient judge or an
  answer with no tool call. They now score by design.
- **The other changes are noise:** all 4 losses are on dialogues the guard did not touch (3 have no
  policy).
- **One "context too long" error is back.** It is a student_loan dialogue with a 106-character
  history that failed the same way in the V5 run; it is not caused by the history.
- **Macro over Caps 1–4 with V5, short history and V6: 0.538** (Caps 1–3 from the V5 run).
- **On the official test set the guard matters more:** IBM's internal policy judge (not shipped;
  `evaluator/scorer.py` loads it if present) scores a turn 0 when the policy is broken, and the
  guard prevents both kinds of violation.

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
- ~~**Cap 4 context length** (17%)~~: fixed by `--short-history` (#7, Finding 4).
- ~~**Cap 4 refusals**~~: V6 refuses all 11 unanswerable dialogues on purpose (#10, Finding 5).
- **Remaining tool-call rejections** (2–6%): V3 (#8).

## Notes

- **Judge:** the same 2 Cap 1 items get "Judge Error {e}." in both Cap 1 runs; their gold answers
  are very long lists. This is upstream's judge failing on size (the `{e}` is an upstream
  formatting bug), not an authentication problem. No 401 occurred in any run. The 27 HTTP 429s
  during the fixed run were absorbed by retries; no item failed on one.
- **Cost:** **$3.25** for all of these runs (Groq dashboard), including the two stopped Cap 1
  runs and the 7-item Cap 1 check. The project total is now **$5.25** ($2.00 for the baselines in
  [baseline_dev_eval.md](baseline_dev_eval.md)).
- **Cost since (Nov 12, Groq dashboard): project total $7.71.** The $2.46 after the note above
  covers the V5 offline test, the full V5 run (Caps 1–4), the short-history and V6 Cap 4 runs and
  the V6 topic check (`policy_guard.py --check`); the dashboard does not split it by run.
