# VAKRA-Advanced: Project Plan

Team: **Anurag Kaushal, Aayush Pandey, Piyush Agarwal**. Plan v0.1, written 2026-10-26.
Technical details are in [SPEC.md](SPEC.md).

## 1. Objectives

| # | Objective | Measured by |
|---|---|---|
| O1 | Reproduce the official baseline locally (all 4 capabilities, dev split) | Upstream evaluator score on `dev-heldout` |
| O2 | Beat the baseline on Caps 2 and 3 with IR-driven tool retrieval and a stateful executor | Official score; tool Recall@k |
| O3 | Extend to Cap 4: document retrieval plus a policy guard in code | Official score; policy-violation rate |
| O4 | Bring Cap 1 to a competitive level (schema grounding, retrieved few-shot) | Official score; argument-error rate |
| O5 | Course deliverables: baseline vs. improved comparison, ablations, failure analysis, report | Results table + error taxonomy |
| O6 | Optional: submit to SemEval-2027 Task 11 and write the system paper | Submission accepted; paper submitted |

**Scope rule:** O1 and O2 are the minimum deliverable. O3 is the target. O4 is a stretch goal
unless timing allows. O6 depends on the decisions in [§6](#6-open-decisions).

## 2. Workstreams and owners

Owners are a proposal; swap freely. Each workstream has one owner and one reviewer, and every PR
needs a review from someone other than its author.

| Workstream | Owner | Reviewer | Covers |
|---|---|---|---|
| **A. Agent core and infrastructure** | Anurag Kaushal | Aayush Pandey | Own runner on top of upstream MCP client; executor (validation, repair, step budget); state store; trace logging; configs; Cap 1 strategy |
| **B. Tool retrieval and selection** | Aayush Pandey | Piyush Agarwal | Tool indexing (BM25, dense, hybrid, rerank, doc expansion); retrieval metrics; planner / plan-then-act; Caps 2 and 3 |
| **C. Multi-source, policy and evaluation** | Piyush Agarwal | Anurag Kaushal | Splits; evaluation harness and diagnostics; document retrieval; policy guard and abstention; Cap 4; error taxonomy |
| **Shared** | All | — | Answer synthesizer, experiment runs, report writing |

## 3. Timeline

Weeks start on Mondays. The course deadlines are not yet in this plan and must be added
([§6](#6-open-decisions)). SemEval dates are from the task site; exact days are still TBA.

### Phase 0: Setup and baseline (2026-10-26 → 2026-11-08)

**Week 0 (Oct 26 – Nov 1)**

- [x] Everyone: join the mailing list.
- [ ] One person: submit the team registration form <https://forms.gle/2MLpxaU1kcD1SbCm7>.
  *(Deferred by Anurag; not submitted yet.)*
- [ ] Request access to the **public benchmark test set** `ibm-research/VAKRA-GatedTest`. This is
  *not* the SemEval evaluation data, which comes through the registration form. Two steps:
  1. Click "request access" on its Hugging Face page.
  2. Open an issue on IBM/vakra with the template "VAKRA-GatedTest Access Request".
  This gives us inputs for the test domains that train does not cover.
  *(Both steps done 2026-10-26; approval **pending**. Do not download until approved.)*
- [ ] Request PolicyJudge access: a plain issue on IBM/vakra asking for `policy_judge.py`, for
  local Cap 4 scoring.
- [x] Decide the LLM provider for Phase 0 ([§6](#6-open-decisions)); get API keys, including a
  judge endpoint for `gpt-oss-120b`. *(2026-10-27: Groq free tier for judge + primary agent;
  Gemini key available as a separate experiment series.)*
- [ ] **A:** create the git repo; add upstream at `third_party/vakra` pinned to `00dc68f`; run
  `make download`, `make build`, `docker compose up -d`, `make validate` on at least one
  machine. Confirm ≥ 8 GB RAM for Docker and 35 GB of disk.
- [ ] Everyone: run the upstream smoke test on one domain per capability. Browse the tools in
  `tools_explorer`.

**Week 1 (Nov 2 – Nov 8)**

- [ ] **C:** write `scripts/make_splits.py` and commit the `smoke`, `dev-seen`, `dev-heldout`
  and `train-rest` uuid lists.
- [ ] **C:** set up the evaluation wrapper `scripts/evaluate.py` around upstream
  `evaluator/evaluator.py`; make it run end to end on `smoke`.
- [ ] **All:** data exploration notebook. Cover tool counts per domain, hop distribution, policy
  types and unanswerable rate in Cap 4. Answer the open questions in SPEC §11.
- [ ] **A:** **V0 baseline.** Run the upstream `LangGraphReActAgent` on `dev-heldout` for all
  4 caps with the chosen model, then score it.

**Phase 0 deliverable:** environment reproducible on at least 2 machines; V0 scores for all
4 capabilities; splits committed.

### Phase 1: Core agent for Caps 2 and 3 (2026-11-09 → 2026-11-29)

**Weeks 2–3 (Nov 9 – Nov 22)**

- [ ] **A:** own runner plus `AgentInterface` implementation that produces identical output
  format (`validate_output.py` passes); trace logging (`traces.jsonl`); executor with schema
  validation and repair.
- [ ] **B:** tool-retrieval module (BM25, dense, hybrid RRF). Measure offline Recall@k and MRR
  on Cap 2 and Cap 3 gold tools; pick k.
- [ ] **C:** `diagnostics.py` (tool and argument match, scoring path, efficiency) on top of
  traces.

**Week 4 (Nov 23 – Nov 29)**

- [ ] **B:** reranker and doc expansion; plan-then-act planner for Cap 3.
- [ ] **A:** state store with typed entity and ID slots, used for multi-hop argument filling.
- [ ] **All:** V1–V3 runs (see [§4](#4-experiment-matrix)).

**Phase 1 deliverable:** our agent beats V0 on Caps 2 and 3 (`dev-heldout`); first results
table; **midpoint report material**.

### Phase 2: Caps 4 and 1, reliability (2026-11-30 → 2026-12-20)

**Weeks 5–6 (Nov 30 – Dec 13)**

- [ ] **C:** policy parser and guard; abstention path; retriever routing (primary vs.
  distractor collections); context-aware query rewriting; Cap 4 runs.
- [ ] **A:** Cap 1. Use the full peek in the prompt, fuzzy column and handle grounding in the
  executor, and retrieved few-shot from `train-rest`.
- [ ] **B:** answer synthesizer (shared). Tune the tool-retrieval k against cost.

**Week 7 (Dec 14 – Dec 20)**

- [ ] **All:** V4–V6 runs; ablations; error taxonomy over ≥ 50 failed items per capability.

**Phase 2 deliverable:** full system across the capabilities in scope; ablation table; error
analysis.

### Phase 3: Hardening, report and submission (2026-12-21 → 2027-02)

- **Dec 21 – Jan 3:** buffer and holidays.
  - Fix the top failure categories.
  - Cut cost per item.
  - Freeze the system config.
  - Dry-run the full test pipeline (`--resume` support, validation).
- **January 2027 (official evaluation window):**
  - Run on the gated test split.
  - Run `validate_output.py --all`.
  - Submit per the organizers' format.
  - Archive every artifact in `runs/`.
- **Course final report:** date TBD.
- **February 2027:**
  - SemEval system paper, following <https://semeval.github.io/paper-requirements.html>.
  - Notification follows in March 2027, camera-ready in April 2027.

## 4. Experiment matrix

Each variant adds **one** change to the one before it. All are scored on `dev-heldout` with the
same LLM.

| ID | Variant | Caps | Hypothesis |
|---|---|---|---|
| V0 | Upstream `LangGraphReActAgent`, MiniLM top-128 shortlist | 1–4 | Reference |
| V1 | Own runner + agent, same behaviour as V0 | 1–4 | Parity check: must match V0 within noise |
| V2 | + hybrid tool retrieval (BM25 + dense, RRF), small k | 2–4 | Higher gold-tool recall at small k → better selection, fewer tokens |
| V3 | + schema validation, argument normalization, error repair | 1–4 | Fewer invalid or erroring calls |
| V4 | + plan-then-act with state-store slots | 3, 4 | Better at ≥ 2 hops |
| V5 | + evidence-only answer synthesizer | 1–4 | Fewer groundedness and correctness failures when the calls are right |
| V6 | + policy guard, abstention, retriever routing | 4 | Fewer policy violations; credit on unanswerable items |
| V7 | + Cap 1 column grounding + retrieved few-shot | 1 | Fewer argument-name errors |

**Ablations for the report:**

- Retriever type (BM25 / dense / hybrid / + rerank) × k ∈ {5, 10, 20, 50}.
- With vs. without document expansion.
- ReAct vs. plan-then-act, bucketed by hop count.
- Prompt-only policy vs. guard in code.
- Optionally, a second LLM to show the improvements are not tied to one model.

## 5. Risks and mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| LLM API cost. A full test run is ~5.2k dialogues × several LLM calls each, plus judge calls | High | High | Budget first; iterate on `smoke` / `dev`; cache LLM responses by prompt hash; use an open-weights model via a cheap or free endpoint for development |
| Laptop hardware (35 GB disk, 8 GB Docker RAM) | Medium | High | One shared machine as the "env host"; check the university server / cloud VM options in Week 0 |
| Test domains unseen in train | High | Medium | `dev-heldout` split by domain; avoid domain-specific hand rules |
| Permitted resources and submission format only published late | Medium | Medium | Keep the provider swappable; avoid dependencies on proprietary-only features |
| PolicyJudge stays private | Medium | Low | Own rule-based policy checker for diagnostics; request access early |
| Upstream repo changes mid-project | Medium | Medium | Pin the commit; bump only deliberately and re-run V1 parity |
| Evaluator LLM judge is noisy | Medium | Low | Fixed judge model; report CIs; inspect disagreements by hand |
| Holiday period clashes with the January evaluation window | Medium | Medium | Freeze the config by 2027-01-03; dry-run the full pipeline before then |

## 6. Open decisions

These must be settled in Week 0. Record each decision and its date here.

1. **Agent LLM and budget:** API models (which, how much $), open weights via Groq / Together,
   or local Ollama / vLLM on a GPU (which hardware)?
2. **Course deadlines:** midterm and final report dates, and grading criteria. They may move
   Phase 2 earlier.
3. **Official SemEval submission:** yes or no? If yes, which subtasks? The FAQ allows any subset.
4. **Fine-tuning:** allowed and wanted? For example, fine-tuning a small tool-retriever
   bi-encoder or cross-encoder on train (query → gold tool) pairs is cheap and fits the IR
   course well.
5. **Compute host:** where do the containers and data live, and who has access?

## 7. Working agreements

- **Weekly sync** (30 min): each owner reports results against the experiment matrix and their
  blockers.
- **Git:**
  - `main` is always runnable.
  - Use feature branches with PR review.
  - Never commit `data/`, `runs/` or `.env`.
- **Experiments:** every reported number links to a `run_id` with its config. No number goes into
  the report without one.
- **Decision log:** decisions go in [§6](#6-open-decisions) or in SPEC with a date, so nobody
  re-argues them.

## 8. Final deliverables checklist

- [ ] Reproducible code: setup instructions, configs, scripts (README).
- [ ] Baseline (V0) and best variant for each capability in scope.
- [ ] Results table: official metric plus diagnostics, baseline vs. variants.
- [ ] Ablation tables ([§4](#4-experiment-matrix)).
- [ ] Error taxonomy with representative success and failure traces.
- [ ] Course report (design, method, results, limitations).
- [ ] (Optional) SemEval submission files and system paper.
