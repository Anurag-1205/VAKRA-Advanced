# Why right answers fail the groundedness check (2026-11-10)

Offline, no LLM calls. Input: the V2 + both fixes runs on `dev-eval`
(`20261109-2356-v2hybridfixrt-maxit25-groq-dev-eval-cap1` for Cap 1,
`20261109-2356-v2hybridfixrt-groq-dev-eval` for Caps 2–4; scores in
[v2_and_fixes_dev_eval.md](v2_and_fixes_dev_eval.md)).

`python scripts/ungrounded_items.py --run-id <run>` lists the **35 items** (10 / 11 / 3 / 11 in
Caps 1–4, 12.7% of all 275) that had the right answer or the right tool responses and lost the
point only on groundedness. Each was read by hand and given one cause.

## How upstream judges groundedness

From `third_party/vakra/evaluator/` (judge.py, scorer.py, mcp_tools.py):

- The evaluator replays the agent's tool calls (the last 20) and gives the judge a "document" of
  **the query plus the tool responses**. The judge **does not see the tool calls or their
  arguments**.
- The answer must be "entirely grounded" in that document. **"partial"** (needs non-trivial
  common-sense knowledge) **and "unsure" both score 0**, the same as "no".
- Cap 1 tools return a data handle plus a peek of the **first 3 values** of each column, not the
  full table.

## Causes

| Cause | Cap 1 | Cap 2 | Cap 3 | Cap 4 | Total |
|---|---:|---:|---:|---:|---:|
| **A. Adds facts not in the tool output** (units, interpretations, world knowledge, "only"/"as of") | 3 | 6 | 1 | 3 | **13** |
| **B. The filter lives in the call's arguments**, which the judge cannot see | 5 | 1 | 1 | 5 | **12** |
| C. A real mistake the correctness judge let through | 2 | 2 | – | – | 4 |
| D. Gave up or answered with no tool evidence | – | 1 | 1 | – | 2 |
| E. Claims built across many calls that the document does not support | – | 1 | – | 1 | 2 |
| F. Long list cut off mid-answer | – | – | – | 2 | 2 |
| **Total** | **10** | **11** | **3** | **11** | **35** |

**A. Adds facts not in the tool output (13).** The data is right, but the model adds something:

- units the tool never returned ("200 **cc**", "25 **°F**");
- interpretations (weather codes `RA DZ SN` expanded to "rain, drizzle, snow");
- world knowledge ("Russia is the largest country", "Brunei", "the Ford Torino is American",
  "Tokyo, Delhi, Shanghai…" where the dataset's top city is Mumbai, the 1922 Stanley Cup
  finalists);
- unrequested framing ("ages **as of 2024-11-09**", "the **longest** absence", "these are **the
  only** papers");
- city life expectancy taken from the country's value: the data's design, but the judge rules it
  "partial".

**B. The filter lives in the call's arguments (12).** For example,
`get_distinct_car_names_by_country(country="USA")` returns bare names, and the answer "these are
the US models: …" is correct. But the judge sees only the names and rules the "US" claim
ungrounded. The same happens with sorts ("the **most** games"), year filters, and Cap 1's 3-row
peeks: the judge sees 3 rows with year 2008 and then a list of 4 titles, so it flags the fourth.
This is a limit of the evaluator, not of the agent, and it applies to every system scored with it.

**C. Real mistakes (4):**

- a wrong player when the tool output shows a higher scorer;
- "the sole country" when several tie;
- a percent conversion off by 100×;
- an invented "home losses 30.20%".

**D–F (6).**

- Two answers with no evidence: a guess with 0 tool calls, and an answer that talks about the
  tools instead of answering.
- Two long multi-call chains whose final claims the document does not show.
- Two date lists that stop mid-date ("…2013-10-20\n201") at about 4,600 characters. Upstream has
  no length cap, so the model's output stopped there.

## What this means for V5 (evidence-only answers)

- **A (13 items) is what V5 should target.** It is a final step that rewrites the answer using
  only values present in the tool output: copied verbatim, with no added units, interpretations,
  world facts or "only/sole/as of" claims. If the evidence is missing, it says so (also covers D).
  It costs one extra LLM call per item.
- **B (12 items) should be reported, not gamed.** An answer could pass by not restating the
  filter, but it would be worse for a user. The report should state that the judge cannot see
  tool arguments and that this caps every system's score, ours included. If V5 cites the
  filter it applied ("filtered by country = USA: …"), that is legitimate and may also help here.
  Only a test will tell.
- **C and F (6 items)** are not grounding problems: one is arithmetic, and long lists are better
  handled as a count plus the list.
- **Expected gain:** at most about 13–17 items of 275 (+5–6 points overall). The largest share is
  in Cap 2 (6 of 120). With ~10% run-to-run noise, V5 must be checked on these 35 items, plus a
  control set of currently correct items to confirm nothing breaks, not on totals alone.

## Offline V5 test (2026-11-10)

`python scripts/v5_answer_test.py --run-ids <the two runs above>`:

- **Items:** the 35 items above, plus a control sample of 35 correct items with the same count per
  capability (seed 0).
- **Rewrite:** each item's tool calls were replayed on the local containers, and `gpt-oss-120b`
  rewrote the final answer from that evidence only (`V5_PROMPT` in the script).
- **Scoring:** both the original and the rewritten answers were scored with the official
  evaluator (both judges).
- **Runs:** `20261110-1536-v5test-orig` and `20261110-1536-v5test-v5`.

| Task | Ungrounded: original re-scored | Ungrounded: V5 | Control: original re-scored | Control: V5 |
|---|---:|---:|---:|---:|
| 1 | 5 / 10 | 6 / 10 | 10 / 10 | 10 / 10 |
| 2 | 0 / 11 | **6 / 11** | 10 / 11 | 11 / 11 |
| 3 | 0 / 3 | **1 / 3** | 3 / 3 | 3 / 3 |
| 4 | 0 / 11 | **3 / 11** | 11 / 11 | 10 / 11 |
| **Total** | 5 / 35 | **16 / 35** | 34 / 35 | 34 / 35 |

- **The effect is real on Tasks 2–4: 10 of 25 items recovered**, none of which pass when their
  original answers are simply re-scored. On the control items, one flips each way, so there is no
  net loss.
- **Task 1's groundedness verdicts are mostly noise:** 5 of its 10 "ungrounded" items pass when
  their original answers are re-scored, and V5 adds only 1. Task 1 judge results should not be
  read item by item.
- **Net: about +11 items of 275 (about +4 points macro)**, mostly Task 2.
- **By cause** (V5 scoring only): extra facts 8 / 13, filter only in the arguments 4 / 12,
  others 4 / 10.
- **What to fix before a full run:** rule 6 ("say the information is not available") turned 2
  right answers into refusals that fail the correctness judge (the Ford Torino count; the guessed
  "1924"). It should only apply when the draft has no supporting tool result at all.
- **Cost:** about $0.04 for the rewrites (125k input + 32k output tokens), plus two scoring
  passes over 70 items.

## Full V5 run on dev-eval (2026-11-10)

Same setup as the last row of [v2_and_fixes_dev_eval.md](v2_and_fixes_dev_eval.md), plus
`--evidence-answer` (with the revised rule 6). Runs: `20261110-1559-v2hybridfixrtv5-groq-dev-eval`
(Caps 2–4) and `20261110-1559-v2hybridfixrtv5-maxit25-groq-dev-eval-cap1`.

| | Cap 1 | Cap 2 | Cap 3 | Cap 4 | Macro |
|---|---:|---:|---:|---:|---:|
| V2 + both fixes | 0.450 (27) | 0.558 (67) | 0.486 (17) | 0.317 (19)\* | 0.453 |
| **+ V5** | **0.583 (35)** | **0.583 (70)** | 0.486 (17) | 0.317 (19)\* | **0.492** |
| Items won / lost | +9 / −1 | +8 / −5 | +2 / −2 | +3 / −3 | |
| "Not grounded" items | 10 → 4 | 11 → 7 | 3 → 3 | 11 → 11 | 35 → 25 |

\* Includes 1 dialogue credited after an agent crash; 18/60 = 0.300 without it, in both runs.

- **On Caps 2–4, V5 recovers the items it targets:** 10 of the 25 previously ungrounded items
  are correct, the same 10 / 25 as the offline test.
- **Cap 2's net gain is smaller (+3)** because of the usual churn. Of its 5 losses (and Cap 3's 2):
  - about 2 look caused by V5: a rewrite that redid a percentage calculation ("≈733%"), and
    possibly answers that ask for clarification (the draft is not recorded, so this is unclear);
  - the rest are judge inconsistencies ("months" accepted on Nov 9 and rejected on Nov 10; a date
    the judge invented) or the agent behaving differently (one context-length crash).
- **Cap 1 rose by 8 items (+9 / −1).** 5 of the 9 wins were previously ungrounded. The offline test
  showed Cap 1's groundedness verdicts are mostly noise (5 of 10 pass on a re-score alone), so part
  of this gain is likely noise too. The other 4 wins went from wrong to right.
- **Cap 4 is unchanged.** Its "not grounded" items are mostly long lists filtered by a tool
  argument the judge cannot see (cause B), which V5 does not fix.
- **Macro +0.039 (0.453 → 0.492)**, in line with the offline estimate of about +4 points. Each
  capability's change is within its 95% half-width; the evidence is the item-level pattern above.
- **Next time, record the draft** before the rewrite (in the output file or the run log) so that
  V5-caused changes can be told apart from agent noise. *Done (d7b9f13): every rewrite is now
  appended to `<output>/v5_drafts.jsonl` (query, draft, final answer).*
