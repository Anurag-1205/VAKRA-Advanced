# Error analysis (#13) on the final run (2026-11-12)

Runs: the final run (#15, [v2_and_fixes_dev_eval.md](v2_and_fixes_dev_eval.md), "Final run"):

- Cap 1: `20261112-1833-v2hybridfixv3rtv5shv6v7v8-maxit25-groq-dev-eval-cap1`
- Caps 2–4: `20261112-1833-v2hybridfixv3rtv5shv6v7v8-groq-dev-eval-cap234`

116 of 275 items fail (30 / 45 / 16 / 25 in Caps 1–4). Two passes: an automatic category for every
failed item, then a hand-read root cause for a sample of 76 (20 per task, all 16 for Cap 3).

## Method

`scripts/error_analysis.py` gives each failed item one category. The first split is the
evaluator's own exact-match verdict: were all the gold tool responses among the agent's? If yes,
the tool part was right and the answer failed. If no, the tool part failed, and the reason comes
from comparing the agent's calls with the gold calls (`scripts/diagnostics.py`, which also reads
the run log for tool results). Categories, in the order they are checked:

| Category | Rule |
|---|---|
| Agent crash | the item ended with an agent error |
| Right answer, not grounded | the correctness judge passed, the groundedness judge did not |
| Right tool results, answer not grounded | every gold tool response present; groundedness failed |
| Right tool results, wrong answer | every gold tool response present; correctness failed |
| Missing results: no tool call | answered without calling a tool |
| Missing results: different tool | some gold tool was never called |
| Missing results: argument differs only in case/spaces | the gold call up to case and spaces |
| Missing results: other argument value | every gold tool called, some never with the gold arguments |

For Cap 1, "different tool" is a weak signal: Cap 1 has many equivalent tool paths (for example
`compute_data_max` and a filter instead of `sort_data_descending` and `truncate`).

The sample is drawn per task in proportion to the categories, with a fixed seed. Each item was
read in full (query, gold and agent calls, tool results, both answers, the judge's explanation)
and given one root cause. The annotated sample is in
`runs/20261112-1833-v2hybridfixv3rtv5shv6v7v8-groq-dev-eval-cap234/error_sample.md` (gitignored:
it holds benchmark items).

## Where the failed items go (all 116)

| Category | Cap 1 | Cap 2 | Cap 3 | Cap 4 |
|---|---:|---:|---:|---:|
| Agent crash | 4 (13%) | 1 (2%) | 1 (6%) | 1 (4%) |
| Right answer, not grounded | 6 (20%) | 2 (4%) | 2 (12%) | 1 (4%) |
| Right tool results, answer not grounded | 1 (3%) | 10 (22%) | 0 | 2 (8%) |
| Missing results: no tool call | 1 (3%) | 1 (2%) | 0 | 2 (8%) |
| Missing results: different tool | 13 (43%) | **21 (47%)** | **11 (69%)** | **14 (56%)** |
| Missing results: argument differs only in case/spaces | 0 | 3 (7%) | 0 | 0 |
| Missing results: other argument value | 5 (17%) | 7 (16%) | 2 (12%) | 5 (20%) |
| **Failed / items** | **30 / 60** | **45 / 120** | **16 / 35** | **25 / 60** |

No failed item falls in "right tool results, wrong answer". Against the preliminary analysis on
the earlier runs: crashes 8 → 7, no tool call 2 → 3 in Caps 2–4, case-only arguments 5 → 3 in
Caps 2–3; "different tool" is still the largest category in every task.

## Root causes in the sample (76 items)

| Root cause | Cap 1 | Cap 2 | Cap 3 | Cap 4 | All |
|---|---:|---:|---:|---:|---:|
| **Agent: tool use** | | | | | **36** |
| Wrong tool or wrong decomposition | 1 | 6 | 5 | 3 | 15 |
| Wrong argument value (case, format, flag meaning, threshold) | 0 | 4 | 2 | 3 | 9 |
| Gave up or stopped the chain with the evidence half-gathered | 1 | 0 | 2 | 2 | 5 |
| No tool call | 1 | 1 | 0 | 2 | 4 |
| Searched documents instead of the data tool (Cap 4) | 0 | 0 | 0 | 3 | 3 |
| **Agent: the answer** | | | | | **10** |
| Rendering: list truncated or deduplicated, a name where the gold has a code | 5 | 0 | 0 | 1 | 6 |
| Adds or contradicts (a unit, outside knowledge, misreads the result) | 1 | 1 | 1 | 1 | 4 |
| **Agent crash** (request or context too large, one rejected call) | 3 | 1 | 1 | 1 | **6** |
| **Not clearly the agent's fault** | | | | | **24** |
| Gold questionable or question ambiguous; the agent's answer is defensible | 3 | 5 | 4 | 3 | 15 |
| Judge error or evaluator limit; the answer is supported by the tools | 5 | 2 | 1 | 1 | 9 |
| **Sampled** | **20** | **20** | **16** | **20** | **76** |

Against the automatic categories: of the 38 sampled "different tool" items, 16 are a genuinely
wrong tool (13, plus 3 Cap 4 document searches), 5 stop the chain early, 13 have a questionable
gold, and 4 are other causes. Of the 15 sampled groundedness failures, 7 are judge errors and 4 are
answers that really add something.

## Main patterns

**1. Choosing the tool is the main agent failure, but a third of "different tool" is the gold.**
The automatic count puts 47–69% of failures in Caps 2–4 under "different tool". Retrieval is not
the cause: with 128 tools the gold tool is in the shortlist for almost every item
([tool_recall.md](tool_recall.md)). Reading the items:

- **A plausible neighbour (Cap 2).** "How many shoutouts are there in the regular season of
  1977?" → `get_sum_sho_by_year(1977)` returns 0 and the agent answers 0; the gold is
  `get_count_combined_shutouts_by_year_and_role(1977, "R")` = 2. Others: the "disabled" variant of
  a percentage tool, "top organisation by enlisted males" for "highest male percentage".
- **Splitting a composite tool (Caps 2 and 4).** The agent rebuilds a composite gold tool from
  simple ones (ids plus prices; author info, journal name and short name in 3 calls) and loses
  either the gold response or the answer.
- **Wrong first hop (Cap 3).** For `roypa01` the agent asks for goals or games played instead of
  the player's team and gives up; one item calls a tool from another domain 28 times (HTTP 500 every time).
- **Document search instead of data (Cap 4).** 3 dialogues search the documents 6–18 times with
  near-identical queries and never try the data tool.

**2. A third of "different tool" failures have a questionable gold (13 of 38 sampled; 15 of 76
over all categories).** The agent's answer is defensible and the gold is odd:

- The gold chain's second call ignores the first. "Among the authors of the paper published in
  2003 by [an affiliation], how many are affiliated with Cairo Microsoft Innovation Lab?": the agent
  finds the paper, asks for its Cairo authors and gets none (0); the gold's second call asks about
  "University of Tokyo" (1). In two Cap 3 cars items the gold's second call drops the 1975 condition the first call
  found.
- The gold argument contradicts the question: `get_city_count_by_name("PHL")` = 0 for "How many
  cities are in the Philippines?" (the agent lists 136); position `"D"` (defence) for "which goalie
  had the most play minutes" (the agent passes `"G"`); a tool named `unemployed_…` for "employed".
- The gold answers a different quantity: match counts (2588) for "how many teams"; an absolute
  difference (44) for "how many more … in percentage"; 25 rows for "how many times was the Ford
  Maverick introduced" (the agent counts 5 model years).

These cannot be fixed by the agent; they cap every system's score. We have not removed them from
the scores, and the sample is too small to correct the totals with.

**3. Argument values (9 of 76).** Case (`'steamship'`, gold `'STEAMSHIP'`), format
(`'peace corps'` for `'peace_corps'`, a division code `'SC1'` for its name), swapped `year1`/`year2`,
"more than 5" passed as 6, and boolean flags whose meaning is unclear from the tool name
(`get_count_unemployed_bankruptcy_no_payment(bool_value='pos')` counts students who *have* a
payment due). V8's case retry worked where the agent used it: a Cap 3 item retried `"Ford Torino"`
as `"ford torino"` and found the country, but then stopped before the second hop (pattern 4).

**4. Giving up (5 of 76, plus the refusals inside other causes).** "The information is not
available" after one hop, or with the needed value in hand: one Cap 4 item has the gold count (36)
and still says it cannot be determined; another has all heights in feet and inches and declines to
convert to centimetres. V7 removed most answers with no tool call (3 left in Caps 2–4), but not
early stops after a call.

**5. Groundedness is 21% of failures (24 of 116), and about half of it is the judge.** In the
sample, 7 of 15 are judge errors: the judge sees a data handle's first 3 values and calls a
4-record count unsupported, claims names are missing from a list copied verbatim, or returns
"Judge Error empty output" on a long table. The other half are real: an added unit ("mph²"), a
fact from world knowledge instead of a skipped hop ("Brunei", "England"), and one answer of 0 when
the tool returned 95.

**6. Task 1 failures are mostly about the final answer.** 5 of 20 sampled Cap 1 failures render
the answer differently from the gold (a name where the gold has a country code, a deduplicated
list where the gold keeps duplicates, 3 ids from a data handle's preview instead of the list) and
5 are judge errors. Cap 1 tools return data handles with only the first 3 values,
which also hides values from the agent.

**7. Crashes are few (7 of 116).** Cap 1: 2 tool responses too large for Groq (HTTP 413), 1
context length, 1 recursion limit. Cap 2: 1 context length. Cap 3: 1 rejected call that V3's retry
repeated (`full_time_result` for `ftr`). Cap 4: the student_loan dialogue that is too long in every
run. Rejected calls fell from 5 in the earlier runs to 1 (V3).

## Commands

```
python scripts/error_analysis.py --cap-run 1=<cap1 run> --cap-run 2=<cap234 run> \
  --cap-run 3=<cap234 run> --cap-run 4=<cap234 run> --sample 20 --out runs/<cap234 run>/error_sample.md
```

The labels were written into the sample's "Root cause" lines by hand reading; the counts above
come from those lines.
