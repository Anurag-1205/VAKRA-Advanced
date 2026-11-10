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

## A cheap test before the full run

Rewrite the stored answers for these 35 items plus ~35 currently correct ones, replay their tool
calls (free, local containers), and score only the groundedness judge. That is about 140 small
LLM calls, well under $0.10. It measures V5's effect on exactly the affected items, without a
full paid run.
