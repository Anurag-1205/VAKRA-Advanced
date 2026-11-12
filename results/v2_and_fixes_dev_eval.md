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
| + V7 tools-first rule (`--tools-first`, Caps 2–3 only, Nov 12; see Finding 6) | – | **0.633 (76)** | 0.486 (17) | – |
| + V8 case and multi-hop hints (`--tool-hints`, Caps 2–3 only, Nov 12; see Finding 7) | – | **0.650 (78)** | 0.486 (17) | – |
| **Final run** (#15): all of the above + V3 `--repair-tool-calls`, all tasks in one run (Nov 12; see below) | **0.500 (30)** | **0.625 (75)** | **0.543 (19)** | **0.583 (35)** |
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
- + V5 + V7, Caps 2–3: `20261112-1144-v2hybridfixrtv5v7-groq-dev-eval-cap23`
- + V5 + V7 + V8, Caps 2–3: `20261112-1632-v2hybridfixrtv5v7v8-groq-dev-eval-cap23`
- **Final run** (`scripts/run_final.sh`): `20261112-1833-v2hybridfixv3rtv5shv6v7v8-groq-dev-eval-cap234` (Caps 2–4)
  and `20261112-1833-v2hybridfixv3rtv5shv6v7v8-maxit25-groq-dev-eval-cap1` (Cap 1)
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

## Finding 6: V7, a tools-first rule for Caps 2–3 (2026-11-12)

In the V5 run, 18 of 120 Cap 2 items and 10 of 35 Cap 3 items were answered without any tool
call, none correctly (`diagnostics.py`, flag "no tool call"). The model decided that no tool fits
("I'm not seeing a built-in query that directly reports…") and often asked the user to clarify
(13 of the 28), though the benchmark has no user. Upstream gives the agent no system message on
Caps 2–3.

`--tools-first` (V7, Caps 2–3 only) adds one system message to every agent LLM call
(`TOOLS_FIRST_RULE` in `run_baseline.py`): try the tools before answering, related tools too;
never ask the user back, take the most reasonable reading; say the answer is not available only
when the tool results do not contain it. It is passed as LangGraph's `prompt`, so it is not added
to the history and the recorded trajectory is unchanged.

Live run (Caps 2–3, the V5 setup plus `--tools-first`), item by item against the V5 run:

| | Cap 2 | Cap 3 |
|---|---:|---:|
| Score | 0.583 (70) → **0.633 (76)** | 0.486 (17) → 0.486 (17) |
| Items won / lost | +9 / −3 | +3 / −3 |
| V5's no-tool-call items now correct | 4 of 18 | 3 of 10 |
| Items with no tool call | 18 → 2 | 10 → 1 |
| Answers that ask the user back | 8 → 0 | 5 → 0 |

- **The rule does what it says:** the model now calls tools on almost every item and never asks
  the user back. 7 of the 15 wins are items that had no tool call before.
- **Most no-tool-call items still fail** (14 of 18 in Cap 2, 7 of 10 in Cap 3): the model calls
  tools now but not the gold ones (flag "gold tool never called"). The rule removes a refusal; it
  does not find the right tool.
- **The losses look mostly like the usual churn:** all 3 Cap 2 losses made exactly the same tool
  calls as in the V5 run and lost only on the judges (two authors lists now "not grounded", one
  student_loan count now judged wrong). A Cap 3 football item added one call and is now "right
  answer, not grounded". Two Cap 3 hockey items, judged right before, called other tools and now
  say the data is not available; the rule's "say it is not available" clause may play a part.
- **Cap 2's +6 is within its ±0.09 half-width** (about ±11 items), so the gain on its own is not
  significant; the evidence is the targeted pattern above. Cap 3 is flat.
- **Macro over Caps 1–4 with V5, short history, V6 and V7: 0.551** (Cap 1 from the V5 run, Cap 4
  from the V6 run). Recommended for the final run.

## Finding 7: V8, hints on case-sensitive values and multi-hop questions (2026-11-12)

The error analysis of the V7 run ([error_analysis.md](error_analysis.md)) found two patterns a
prompt could reach. In 5 Cap 2–3 items, the agent called the right tool with the right value in
another case (`'steamship'`, gold `'STEAMSHIP'`): the data is case-sensitive, the lookup returned 0
or nothing, and the agent reported that. In 7 of 12 Cap 3 wrong-tool failures, the chain stopped
after the first hop.

`--tool-hints` (V8, with `--tools-first`) adds two sentences to V7's rule (`TOOL_HINTS` in
`run_baseline.py`): if a lookup returns nothing, an empty list or 0, call it again with the value
in other capitalizations (ALL CAPS, all lowercase); if the question has several parts, keep calling
tools until every part is answered, passing earlier results on.

Live run (Caps 2–3, the V7 setup plus `--tool-hints`), item by item against the V7 run:

| | Cap 2 | Cap 3 |
|---|---:|---:|
| Score | 0.633 (76) → **0.650 (78)** | 0.486 (17) → 0.486 (17) |
| Items won / lost | +5 / −3 | +5 / −5 |
| V7's wrong-case items now correct | 0 of 4 | 1 of 1 |
| V7's hop-2 breaks now correct | – | 2 of 7 |
| Tool calls | 192 → 206 | 127 → 127 |

- **The case hint works when the model follows it literally.** All 3 targeted Cap 3 wins are cars
  items: the first lookup with `"Chevrolet Malibu"` or `"Ford Torino"` returned nothing, the agent
  retried in lowercase (the stored form), got the country and finished the chain. In the
  V7 run the same items stopped there. So the 2 "hop-2 breaks" fixed were really case failures
  at hop 1.
- **In Cap 2 it fixed none of the 4 wrong-case items.** Twice the agent took the 0 at face value
  ("steamship", "OCC"); twice it retried with other spellings in the same case ("Republican house",
  "Pacific Mail Steamship Co.", 8 calls) but never ALL CAPS.
- **The multi-hop sentence shows no separate effect:** the other 5 hop-2 breaks still fail.
- **The other changes look like churn:** in Cap 2, 4 of the 5 wins already had every gold tool
  result in V7 and flipped only on the groundedness judge (2 with the same calls, 2 with one call
  more or different); one win picked the gold tool. Of the 3 losses, 2 kept every gold result and
  failed groundedness, and one passed 6 for "more than 5". In Cap 3, the other 2 wins were "not grounded"
  failures in V7 and changed one argument; of the 5 losses, 2 are "right answer, not grounded" and
  3 picked a different tool for one hop (two football items, one world item), none with a case
  problem. Those 3 may be churn or the multi-hop sentence; one run cannot tell.
- **Both differences are well within noise** (Cap 2 ±0.09, about ±11 items). The evidence is the 3
  targeted wins; there is no clear sign of harm on the other items, and Cap 4 is not affected.
- **Macro over Caps 1–4 with V5, short history, V6, V7 and V8: 0.555.** Recommended for the final
  run, as a small, low-risk change.

## Final run (#15, 2026-11-12)

`scripts/run_final.sh` at commit `4431acb`: every flag of the final configuration (V2, schema
fix, V3, tool refresh, V5, short history, V6, V7, V8), Caps 2–4 in one run and Cap 1 with
`--max-iterations 25`, 18:33–19:41. The laptop slept for 2 minutes during Cap 1 (19:12–19:14);
the run paused and resumed with no connection errors.

| | Cap 1 | Cap 2 | Cap 3 | Cap 4 | Macro |
|---|---:|---:|---:|---:|---:|
| V0, official baseline | stopped | 0.408 (49) | 0.343 (12) | 0.350 (21)\* | – |
| Best earlier run per task | 0.583 (35) | 0.650 (78) | 0.486 (17) | 0.500 (30) | 0.555 |
| **Final run** | **0.500 (30)** | **0.625 (75)** | **0.543 (19)** | **0.583 (35)** | **0.563** |
| Won / lost vs the earlier run | +2 / −7 | +3 / −6 | +5 / −3 | +6 / −1 | |
| 95% half-width | ±0.13 | ±0.09 | ±0.17 | ±0.12 | |

\* 0.300 without the 3 dialogues credited after a crash. The final Cap 4 run has 11 deliberate
refusals (all 11 gold refusals) and no crash credit.

Earlier runs compared: Cap 1 the V5 run, Caps 2–3 the V8 run, Cap 4 the V6 run. In every task the
only new flag that acts on it is V3 (the other new flags apply to other tasks).

- **Every change against the earlier runs is within noise**, as expected when the configuration
  barely changed. Most flips are on the judges: in Cap 2, 5 of the 6 losses kept every gold tool
  response and failed only groundedness; in Cap 4, 4 of the 6 wins were "not grounded" before.
  Cap 1's −5 is 2 groundedness flips with the same calls, 1 more "not grounded", 3 different
  tool paths that ended wrong, and 1 tool response too large for Groq (HTTP 413).
- **V3 (tool-call repair) fired 4 times:** Groq rejected a call (a missing required argument, or a
  tool not in the list) and the retry produced a valid call 3 times; once the model repeated the
  mistake (`full_time_result` for `ftr`). Agent crashes from rejected calls: 1 in this run (Cap 3),
  against 1 in Cap 2 and 2 in Cap 3 in the V8 run.
- **Agent crashes in total: 7 of 275 items** (Cap 1: 2 HTTP 413, 1 context length, 1 recursion
  limit; Cap 2: 1 context length; Cap 3: 1 rejected call; Cap 4: 1 context length, the same
  student_loan dialogue as in every run).
- **Against the official baseline:** Cap 2 0.408 → 0.625, Cap 3 0.343 → 0.543, Cap 4 0.350 →
  0.583 (0.300 → 0.583 without crash credit), and Cap 1 from unscorable to 0.500. The Cap 2 and
  Cap 4 gains are larger than the 95% half-widths; Cap 3's (+7 items) is just above its ±0.17.

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
- **Remaining tool-call rejections** (2–6%): V3 (#8), patch ready as `--repair-tool-calls`; scored in the final run.
- ~~**Answers with no tool call** (Caps 2–3)~~: V7 makes the agent try the tools (Finding 6).
- **Argument values in the wrong case** (5 Cap 2–3 items): V8 fixes the Cap 3 ones (Finding 7); the
  Cap 2 ones need a retry that does not rely on the model, e.g. in the tool layer.

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
- **Cost, later on Nov 12 (Groq dashboard): project total $9.36.** The $1.65 since the note above
  covers the V7 and V8 check runs on Caps 2–3 (about $0.80 each, judge included).
- **Cost of the final run (Nov 12, Groq dashboard): project total $10.82.** The final run
  (Caps 1–4, judge included) cost $1.46.
