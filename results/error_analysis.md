# Error analysis (#13), preliminary (2026-11-12)

**Status:** groundwork on the latest run of each task. Re-run on the final run (#15) on Nov 13 and
replace the numbers and examples (commands at the end). The final run adds V3, which should remove
2 of the crashes below.

Runs (the best configuration so far for each task):

- Cap 1: `20261110-1559-v2hybridfixrtv5-maxit25-groq-dev-eval-cap1` (V2 + fixes + V5)
- Caps 2–3: `20261112-1144-v2hybridfixrtv5v7-groq-dev-eval-cap23` (+ V5 + V7)
- Cap 4: `20261111-1610-v2hybridfixrtv5shv6-groq-dev-eval-cap4` (+ V5 + short history + V6)

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

For Cap 1, "different tool" is a weak signal: Cap 1 has many equivalent tool paths, and 26 of its 35
correct items also skip some gold tool.

## Where the failed items go

| Category | Cap 1 | Cap 2 | Cap 3 | Cap 4 |
|---|---:|---:|---:|---:|
| Agent crash | 4 (16%) | 1 (2%) | 1 (6%) | 2 (7%) |
| Right answer, not grounded | 3 (12%) | 0 | 2 (11%) | 2 (7%) |
| Right tool results, answer not grounded | 1 (4%) | 9 (20%) | 1 (6%) | 6 (20%) |
| Missing results: no tool call | 0 | 1 (2%) | 0 | 1 (3%) |
| Missing results: different tool | 10 (40%) | **23 (52%)** | **12 (67%)** | **14 (47%)** |
| Missing results: argument differs only in case/spaces | 0 | 4 (9%) | 1 (6%) | 0 |
| Missing results: other argument value | 7 (28%) | 6 (14%) | 1 (6%) | 5 (17%) |
| **Failed / items** | **25 / 60** | **44 / 120** | **18 / 35** | **30 / 60** |

No failed item falls in "right tool results, wrong answer": once the agent has every gold result,
it fails only on the groundedness judge.

## Main patterns

**1. Choosing the tool is now the main failure (47–67% of failures in Caps 2–4).** Retrieval is
not the cause: with 128 tools the gold tool is in the shortlist for almost every item
([tool_recall.md](tool_recall.md)). The model picks a wrong tool from the list. The pattern differs
by task:

- **Cap 2, a plausible neighbour:** in all 23 items, none of the gold tools is called. Examples:
  "How many shoutouts are there in the regular season of 1977?" → `get_sum_sho_by_year` instead
  of `get_count_combined_shutouts_by_year_and_role`; "players who won an award in 1983, how many
  play goalie?" → `get_distinct_birth_cities_players_awarded_year` instead of
  `get_count_players_by_position_and_year`. Some gold choices are hard to infer from tool names
  alone: "the car with the best crash protection" → `get_heaviest_car_details`.
- **Cap 3, the chain breaks at the second hop:** in 7 of 12, the first gold call is made and the
  second is not. E.g. "percentage of cars that belong to the origin country of Chevrolet Malibu":
  `get_country_by_car_name` is right, then the agent stops instead of calling
  `get_percentage_produced_in_usa`. 5 of the 12 end with "the information is not available".
- **Cap 4, decomposing or retrieving instead of one composite tool:** in 11 of 14, none of the
  gold tools is called. 7 call document retrievers (`query_*`) where the gold uses a data tool, and
  several split one composite gold tool into many simple calls (e.g. 6 calls to
  `get_paper_conference` instead of one `get_paper_author_conference`). Repeated identical calls
  appear in 5 Cap 4 failures.

**2. Argument values in the wrong case (5 items in Caps 2–3).** The right tool with the right value
in another case: `venue='steamship'` (gold `'STEAMSHIP'`), `sponsor='Republican House'` (gold
`'REPUBLICAN HOUSE'`), `school='OCC'` (gold `'occ'`). The data is case-sensitive, the tool returns
0 or nothing, and the agent reports "0" or "not found". The model cannot know the stored case from
the query alone. V8 (`--tool-hints`, Finding 7 in [v2_and_fixes_dev_eval.md](v2_and_fixes_dev_eval.md))
tells the agent to retry such a lookup in other capitalizations: it fixed the Cap 3 item and two
cars items whose chain had stopped at hop 1 for the same reason, but none of the 4 Cap 2 items. A
retry in the tool layer, not left to the model, is future work.

**3. Groundedness is still 21% of failures (24 of 117)**, even with V5. In Cap 2, 5 of the 9 "right
tool results, not grounded" answers restate conditions from the query (a year, an affiliation,
"the heaviest") that the judge cannot verify, because the filter is in the tool's arguments, not in
its output. This is cause B in [groundedness_dev_eval.md](groundedness_dev_eval.md), and it limits
every system. The other 4 add or change something: a unit ("3.66 *months*"), an inference from a
null value, "the data does not include this" when the result holds the count (9), and a count that
contradicts the result. In Cap 4, one is a judge failure ("Judge Error empty output").

**4. Crashes are few (8 of 117).** Cap 1: one tool response too large (HTTP 413), one tool call
that is not valid JSON, one missing a required argument, one recursion limit. Cap 3: one missing
argument. Cap 4: one HTTP 413 (hockey) and one "context too long" on a 106-character history that
fails in every run. V3 (`--repair-tool-calls`) targets the two Groq rejections (invalid JSON and
missing argument).

**5. Answering without a tool call is almost gone** (2 items in Caps 2–4), after V7 (Caps 2–3) and
V6 (Cap 4). Before V7 it was 28 of 155 Cap 2–3 items, none correct
([v2_and_fixes_dev_eval.md](v2_and_fixes_dev_eval.md), Finding 6).

## For the final version (Nov 13–14)

```
python scripts/error_analysis.py --run-id <final run> --sample 20 --out runs/<final run>/error_sample.md
```

- Replace the table and the counts above.
- Annotate the sample: about 20 failed items per task (all 18 for Cap 3), proportional to the
  categories, with query, gold and agent calls, tool results, both answers and the judge's
  explanation. Write one root cause per item on its last line, and pick the report's examples
  from it. The sample holds benchmark items, so it stays under `runs/` (gitignored).
- Check whether V3 removed the two Groq rejections.

A sample of today's runs (77 items) is in `runs/error-analysis-20261112/sample.md` for a first look.
