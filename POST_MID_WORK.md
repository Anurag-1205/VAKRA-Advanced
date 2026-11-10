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
| 4 | Tue Nov 10 | **V1: our own runner and agent.** Same output format as IBM's, trace logging, includes the schema fix. | Anurag | 1 | Scores within noise of V0 (with the fix) |
| 5 | Tue Nov 10 | ✅ **Rerun V2 on top of the schema fix**; choose the shortlist size | Aayush | 1, 2 | Size chosen, run scored |
| 6 | Tue Nov 10 | ✅ **Retriever ablations**: retriever type × shortlist size (offline, no cost) | Aayush | – | Table in `results/tool_recall.md` |
| 7 | Tue Nov 10 | **Shorten long answers in the Task 4 dialogue history** (17% of dialogues don't fit the context today) | Piyush | – | No "context too long" errors on `dev-eval` Task 4 |
| 8 | Wed Nov 11 | **V3: tool-call checking**: validate each call against its schema and repair bad arguments | Anurag | 4 | Run scored |
| 9 | Wed Nov 11 | ✅ *(negative result)* **V4: retrieve tools again at each hop** for Task 3, using the previous tool result. Fallback if V1 is late: a second retrieval round inside the shortlist only. | Aayush | 4 (or fallback) | Task 3 run scored |
| 10 | Wed Nov 11 | **V6: policy guard**: refuse on purpose when the dialogue's policy forbids the needed tool | Piyush | 7 | Task 4 run scored |
| 11 | Wed Nov 11 | **Diagnostics script** over V1's traces | Piyush | 4 | Runs on any V1+ run |
| 12 | Tue–Wed | **V5: write the answer only from tool evidence** (13% of items fail only the groundedness check). Offline test: +10 of 25 on Tasks 2–4 ([results](results/groundedness_dev_eval.md)); patch ready as `--evidence-answer` | Aayush | – | Run scored |
| 13 | Thu Nov 12 | **Error analysis**: about 20 failed items per task, with example traces | Piyush | 11 | Section drafted |
| 14 | Thu–Fri | **Report sections drafted:** method and system *(Anurag)*, tool retrieval and Tasks 2–3 *(Aayush)*, Task 4 and error analysis *(Piyush)* | All | – | Draft in `report/` |
| 15 | Fri Nov 13 | **Final runs**: the best configuration on all tasks | Aayush (runs), all | 1–12 | All final runs scored |
| 16 | **Fri Nov 13** | **Code freeze** (end of day) | All | 15 | – |
| 17 | Sat Nov 14 | **Final report**: results table, ablation table, error analysis, limitations | All | 15 | Report complete |
| 18 | Sat Nov 14 | **Reproducibility check**: every number in the report links to its run id; README steps work | Aayush + Anurag | 17 | Checked |
| 19 | **Sun Nov 15** | **Submit** | Anurag | 17, 18 | Submitted |

**Status 2026-11-10:** ✅ = done. Results for #1, #2, #3 and #5 are in
[results/v2_and_fixes_dev_eval.md](results/v2_and_fixes_dev_eval.md); #6 in
[results/tool_recall.md](results/tool_recall.md) (retrieval is solved at k = 128); #9 (V4) checked offline there too: no gain even with gold
evidence, so no live patch or paid run;
V5 (#12) offline test and full run in [results/groundedness_dev_eval.md](results/groundedness_dev_eval.md) (macro 0.453 → 0.492). Also done, not planned: a
fix for upstream's stale Cap 1 tool list (`--refresh-tools`, Aayush), without which Task 1 could not
be scored. Open question for the team: whether #4 (V1) is still needed, since the run-time patches
in `scripts/run_baseline.py` already carry both fixes and V2.

## The same tasks, by person

### Anurag: agent core

1. Fix the tool-schema bug (#1). **Mon Nov 9**
2. V1: own runner and agent (#4). Tue Nov 10
3. V3: tool-call checking and repair (#8). Wed Nov 11
4. Report: method and system sections (#14). Thu–Fri
5. Final report, reproducibility check, submission (#17–19). Sat–Sun

### Aayush: tool retrieval, Tasks 2–3, running everything

1. V2: hybrid tool shortlist (#2). **Mon Nov 9**
2. Task 1 baseline (#3). Mon Nov 9
3. Rerun V2 on top of the fix; choose the shortlist size (#5). Tue Nov 10
4. Retriever ablations (#6). Tue Nov 10
5. V4: per-hop tool retrieval for Task 3 (#9). Wed Nov 11
6. V5: evidence-only answers (#12), alone since Nov 10. Tue–Wed
7. Report: tool retrieval and Tasks 2–3 sections (#14). Thu–Fri
8. Final runs for all variants (#15). Fri Nov 13
9. Final report and reproducibility check (#17–18). Sat Nov 14

### Piyush: Task 4 and analysis

1. Shorten long answers in the Task 4 history (#7). Tue Nov 10
2. V6: policy guard and deliberate refusals (#10). Wed Nov 11
3. Diagnostics script over the traces (#11). Wed Nov 11
4. Error analysis (#13). Thu Nov 12
5. Report: Task 4 and error-analysis sections (#14). Thu–Fri
6. Final report (#17). Sat Nov 14

## Risks

- **Anurag's tasks are the critical path.** Tasks 5, 8, 9, 11 and 12 build on the schema fix or
  V1. If V1 is not ready by Tue night, apply the fixes as run-time patches on IBM's agent (as V2
  does) and score every variant that way.
- **Small samples.** Task 3 has 35 items (±0.16) and Task 4 has 60 (±0.12). A variant has to gain
  several items before it counts as an improvement. The report says so rather than claiming
  small gains.
- **The official test set is still pending.** Every score is on held-out training domains; the
  report states this as a limitation.
- **Budget.** About $2 per variant. The plan above needs about 8–10 runs, roughly $15–20.
