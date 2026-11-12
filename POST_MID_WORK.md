# Post-midterm work (2026-11-09 → 2026-11-15)

Everything left after the midterm, in the order it should be done, with an owner for each task.
Background on each item: [PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md) and [PLAN.md](PLAN.md).

## Key dates

| Date | Milestone |
|---|---|
| Mon Nov 9 | Post-midterm work starts |
| **Fri Nov 13, end of day** | **Code freeze.** No new features after this. A bug fix that changes a reported number is still allowed, and the affected run is redone. |
| Sat Nov 14 | Report written; reproducibility check |
| **Sun Nov 15** | **Final submission** |

The freeze is our own milestone, not a course rule. It was moved from Nov 12 to Nov 13 on Nov 9.

Ground rules:

- Every variant is scored on `dev-eval` with the same model (`gpt-oss-120b`), the official
  judge, and compared with V0. About $2 and under an hour per variant on Tasks 2–4.
- All paid runs go through Aayush's machine and Groq key. Send Aayush the branch and the command.
- Each owner drafts their own report section while building, not after the freeze.

## All tasks, in order

| # | Day | Task | Owner | Depends on | Done when |
|---:|---|---|---|---|---|
| 1 | Mon Nov 9 | ✅ **Fix the tool-schema bug.** Tools with no parameters get a required internal `config` field, so Groq rejects correct calls. | Anurag | – | No "missing argument" rejections on `smoke` |
| 2 | Mon Nov 9 | ✅ **V2: hybrid tool shortlist** (BM25 + MiniLM fusion), swapped into IBM's agent at run time. Run on `dev-eval` Tasks 2–3 with 128 and 50 tools. | Aayush | – | Both runs scored |
| 3 | Mon Nov 9 | ✅ **Task 1 baseline**: V0 once on `dev-eval` Task 1 (needed the tool-refresh fix below) | Aayush | – | Score in `results/` |
| 4 | Tue Nov 10 | ❌ *(dropped Nov 10)* **V1: our own runner and agent.** Not needed: the run-time patches in `scripts/run_baseline.py` already carry every fix, and a parity run would cost a paid run we can't spare. Traces come from IBM's output files and run logs. | Anurag | 1 | – |
| 5 | Tue Nov 10 | ✅ **Rerun V2 on top of the schema fix**; choose the shortlist size | Aayush | 1, 2 | Size chosen, run scored |
| 6 | Tue Nov 10 | ✅ **Retriever ablations**: retriever type × shortlist size (offline, no cost) | Aayush | – | Table in `results/tool_recall.md` |
| 7 | Tue Nov 10 | ✅ **Shorten long answers in the Task 4 dialogue history** (17% of dialogues don't fit the context today). Cause: 10 dialogues (authors, menu) carry earlier answers of 0.3–9.4M characters. Patch ready as `--short-history` (first rows + total, ≤ 2,000 characters per answer); checked offline: largest history 2.3M → 1.6k tokens. Live: 0 context errors, Task 4 0.317 → 0.433 ([results](results/v2_and_fixes_dev_eval.md), Finding 4) | Aayush (from Piyush, Nov 10) | – | No "context too long" errors on `dev-eval` Task 4 |
| 8 | Wed Nov 11 | ✅ **V3: tool-call repair**, as one more run-time patch: when Groq rejects a tool call (HTTP 400, tool-call validation), show the model the error and let it retry once. Small on purpose: after the schema fix only 1.7% (Task 2) and 5.7% (Task 3) of items are still lost to rejected calls. Patch ready as `--repair-tool-calls` (`scripts/tool_call_repair.py`), at the LLM call so it composes with V5 and V6; checked offline with `--self-test` (fake LLM on a LangGraph agent: retried once, note kept out of the history, other 400s untouched). Today 6 items of the V5 runs end this way (2 Task 1, 1 Task 2, 2 Task 3, 1 Task 4); `tool_call_repair.py --run-id <run>` lists them for any run | Aayush (from Anurag, Nov 12) | 1 | Checked offline (no rejected call ends an item); scored in the final run (#15) |
| 9 | Wed Nov 11 | ✅ *(negative result)* **V4: retrieve tools again at each hop** for Task 3, using the previous tool result. Checked offline instead ([results](results/tool_recall.md)): even with the gold previous result, per-hop retrieval changes at most 1 of 35 items, so no live patch and no paid run. | Aayush | – | Offline check in `results/tool_recall.md` |
| 10 | Wed Nov 11 | ✅ **V6: policy guard**: refuse on purpose when the dialogue's policy forbids the needed tool. Patch ready as `--policy-guard` (`scripts/policy_guard.py`): in all 898 training dialogues the gold refuses exactly when only document retrievers are allowed and the policy applies. Offline on `dev-eval`: refuses exactly the 11 gold refusals (6 fail today), no other dialogue. Live: same 11, Task 4 0.433 → 0.500 ([results](results/v2_and_fixes_dev_eval.md), Finding 5) | Aayush (from Piyush, Nov 11) | 7 | Task 4 run scored |
| 11 | Wed Nov 11 | ✅ **Diagnostics script** over the trajectories in IBM's output files and run logs: `scripts/diagnostics.py --run-id <run> [--show N] [--jsonl F]` (11 flags per item, failed vs correct table, example traces). First finding: answering without any tool call (often asking the user back) is in 18 of 50 Task 2 and 10 of 18 Task 3 failures of the V5 run, and in no correct item | Aayush (from Piyush, Nov 11) | – | Runs on any run folder |
| 12 | Tue–Wed | ✅ **V5: write the answer only from tool evidence** (13% of items fail only the groundedness check). Offline test: +10 of 25 on Tasks 2–4 ([results](results/groundedness_dev_eval.md)); patch ready as `--evidence-answer`. Live on all 4 tasks: macro 0.453 → 0.492 (Task 1 0.450 → 0.583, Task 2 0.558 → 0.583, Tasks 3–4 unchanged); each rewrite is logged to `v5_drafts.jsonl` since Nov 10 | Aayush | – | Run scored |
| 12b | Thu Nov 12 | ✅ **V7: tools-first rule** (Tasks 2–3, not planned): a system message to try the tools before answering and never ask the user back, for the biggest failure pattern #11 found (28 items answered with no tool call, none correct). Patch `--tools-first`. Live: Task 2 0.583 → 0.633, Task 3 unchanged; no-tool-call items 28 → 3, ask-backs 13 → 0 ([results](results/v2_and_fixes_dev_eval.md), Finding 6) | Aayush | 11 | Tasks 2–3 scored |
| 13 | Thu Nov 12 | **Error analysis**: about 20 failed items per task, with example traces | Piyush | 11 | Section drafted |
| 14 | Thu–Fri | **Report sections drafted:** method and system *(Anurag)*, tool retrieval and Tasks 2–3 *(Aayush)*, Task 4 and error analysis *(Piyush)* | All | – | Draft in `report/` |
| 15 | Fri Nov 13 | **Final runs**: the best configuration on all tasks | Aayush (runs), all | 1–12 | All final runs scored |
| 16 | **Fri Nov 13** | **Code freeze** (end of day) | All | 15 | – |
| 17 | Sat Nov 14 | **Final report**: results table, ablation table, error analysis, limitations | All | 15 | Report complete |
| 18 | Sat Nov 14 | **Reproducibility check**: every number in the report links to its run id; README steps work | Aayush + Anurag | 17 | Checked |
| 19 | **Sun Nov 15** | **Submit** | Anurag | 17, 18 | Submitted |

**Status 2026-11-12:** ✅ = done. Results for #1, #2, #3 and #5 are in
[results/v2_and_fixes_dev_eval.md](results/v2_and_fixes_dev_eval.md); #6 in
[results/tool_recall.md](results/tool_recall.md) (retrieval is solved at k = 128); #9 (V4) checked offline there too: no gain even with gold
evidence, so no live patch or paid run;
V5 (#12) offline test and full run in [results/groundedness_dev_eval.md](results/groundedness_dev_eval.md) (macro 0.453 → 0.492). #7 (short Task 4 history, Aayush) recovers 6 of the 10 dialogues that did not fit: Task 4 0.317 → 0.433, macro 0.521. #10 (V6 policy guard, Aayush) refuses exactly the 11 gold refusals: Task 4 0.433 → 0.500, macro 0.538. #11 diagnostics script done (Aayush). #8 (V3 tool-call repair, Aayush) patch ready as `--repair-tool-calls`, checked offline; scored in #15. #12b (V7 tools-first rule, Aayush): Task 2 0.583 → 0.633, macro 0.551. Also done, not planned: a
fix for upstream's stale Cap 1 tool list (`--refresh-tools`, Aayush), without which Task 1 could not
be scored.

**Decided 2026-11-10 (whole team):** #4 (V1) is dropped. Every variant is a run-time patch in
`scripts/run_baseline.py` (retry, `--retriever`, `--fix-tool-schema`, `--refresh-tools`,
`--short-history`, `--evidence-answer`), so IBM's code stays unchanged. V3 (#8) becomes one more
patch (`--repair-tool-calls`, with `--policy-guard` added since), and the diagnostics (#11) read IBM's output files and run logs.

## The same tasks, by person

### Anurag: agent core

1. ✅ Fix the tool-schema bug (#1), `--fix-tool-schema`. Mon Nov 9
2. ❌ V1: own runner and agent (#4), dropped Nov 10
3. ~~V3: tool-call repair (#8)~~, taken over by Aayush on Nov 12
4. Report: method and system sections (#14). Thu–Fri
5. Final report, reproducibility check, submission (#17–19). Sat–Sun

### Aayush: tool retrieval, Tasks 2–3, running everything

1. V2: hybrid tool shortlist (#2). **Mon Nov 9**
2. Task 1 baseline (#3). Mon Nov 9
3. Rerun V2 on top of the fix; choose the shortlist size (#5). Tue Nov 10
4. Retriever ablations (#6). Tue Nov 10
5. V4: per-hop tool retrieval for Task 3 (#9). Wed Nov 11
6. V5: evidence-only answers (#12), alone since Nov 10. Tue–Wed
7. Shorten long answers in the Task 4 history (#7), taken over from Piyush on Nov 10. Tue
8. V6: policy guard and deliberate refusals (#10), taken over from Piyush on Nov 11. Wed
9. Diagnostics script over IBM's output files and run logs (#11), taken over from Piyush on Nov 11. Wed
10. V3: tool-call repair (#8), taken over from Anurag on Nov 12. Thu
    V7: tools-first rule for Tasks 2–3 (#12b), added Nov 12. Thu
11. Report: tool retrieval and Tasks 2–3 sections (#14). Thu–Fri
12. Final runs for all variants (#15). Fri Nov 13
13. Final report and reproducibility check (#17–18). Sat Nov 14

### Piyush: Task 4 and analysis

1. Error analysis (#13). Thu Nov 12
2. Report: Task 4 and error-analysis sections (#14). Thu–Fri
3. Final report (#17). Sat Nov 14

## Risks

- **No own agent (V1).** Every variant is a run-time patch on IBM's agent, so changes that need
  control over the agent loop are out of scope. The report states this as a design choice.
- **Small samples.** Task 3 has 35 items (±0.16) and Task 4 has 60 (±0.12). A variant has to gain
  several items before it counts as an improvement. The report says so rather than claiming
  small gains.
- **The official test set is still pending.** Every score is on held-out training domains; the
  report states this as a limitation.
- **Budget.** About $2 per variant. The plan above needs about 8–10 runs, roughly $15–20.
  Spent so far (Groq dashboard, Nov 12): **$7.71** for every run since Oct 29, judge included.
