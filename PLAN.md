# VAKRA-Advanced: Project Plan

Team: **Anurag Kaushal, Aayush Pandey, Piyush Agarwal**. Plan v0.2, revised 2026-10-29 for a
hard deadline of **2026-11-15** for all course deliverables (v0.1 of 2026-10-26 ran to
2026-12-20). Technical details are in [SPEC.md](SPEC.md).

## 1. Objectives

| # | Objective | Measured by |
|---|---|---|
| O1 | Reproduce the official baseline locally (all 4 capabilities, dev split) | Upstream evaluator score on `dev-heldout` |
| O2 | Beat the baseline on Caps 2 and 3 with IR-driven tool retrieval and a stateful executor | Official score; tool Recall@k |
| O3 | Extend to Cap 4: document retrieval plus a policy guard in code | Official score; policy-violation rate |
| O4 | Bring Cap 1 to a competitive level (schema grounding, retrieved few-shot) | Official score; argument-error rate |
| O5 | Course deliverables: baseline vs. improved comparison, ablations, failure analysis, report | Results table + error taxonomy |
| O6 | Optional: submit to SemEval-2027 Task 11 and write the system paper | Submission accepted; paper submitted |

**Scope rule (deadline 2026-11-15):**

- **O1, O2 and O5 are the deliverable.** O1 is limited to Caps 2 and 3, scored on the fixed
  `dev-eval` subset ([§3](#3-timeline)), not all of `dev-heldout`.
- **O3 (Cap 4) is conditional.** It goes ahead only if a ≥ 16 GB machine is running the Cap 4
  container by 2026-11-02. Otherwise the report lists it as future work.
- **O4 (Cap 1) is dropped.**
- **O6 (SemEval) is outside the deadline.** The official evaluation window is January 2027, so
  it can only be a follow-up to the course project.

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

Weeks start on Mondays. Course milestones:

- **Midterm checkpoint: Saturday 2026-10-31.**
- **Final submission: Sunday 2026-11-15**, all course deliverables. Code freezes on 2026-11-12.

**Evaluation subset `dev-eval`:** a fixed, domain-stratified sample of `dev-heldout`. It
contains about 120 Cap 2 items and all 35 Cap 3 items, plus about 60 Cap 4 items if Cap 4 is in
scope. A full `dev-heldout` run takes about 4,500 Groq requests, which is roughly 5 days of the
free tier's 1,000 requests/day. A Caps 2–3 `dev-eval` run fits in under a day, so each variant
costs about one day of quota. Development iterates on `smoke`.

### Compressed schedule (v0.2)

**Stage 1: Close Phase 0 (Thu Oct 29 – Sun Nov 1)**

- [x] **All:** settle open decisions 1 and 6 ([§6](#6-open-decisions)). *(2026-10-29:
  V0-k32 on Groq free tier; Aayush's machine for Cap 4.)* Decision 2 (Kaggle) is not needed
  for the deadline.
- [x] **Aayush** (reassigned from C): add `dev-eval` to `make_splits.py` and commit it, by
  Oct 30. *(Built 2026-10-29: 60 / 120 / 35 / 60 items for Caps 1–4; see
  [splits/README.md](splits/README.md).)*
- [ ] **A:** V0-k32 on `dev-eval`, Caps 2 and 3, scored. This is the reference every other
  variant is compared against. Target: Oct 30, so it is in the midterm material.
- [ ] **B (Aayush):** reproduce the setup on a second machine. Report its RAM so the team can
  decide whether it can host Cap 4.
- [ ] **B:** start offline tool retrieval: index the tool catalogs, then measure Recall@k and
  MRR against gold tools on `train-rest`. Needs no LLM and no containers. A first BM25 Recall@k
  number by Oct 31 is a bonus for the midterm, not a requirement.
- [ ] **All, Sat Oct 31: midterm checkpoint.** Material:
  - Problem, task and the four capabilities (from README and SPEC).
  - Proposed architecture (SPEC §4).
  - Work done: environment, splits, runner and official scoring (results/phase0.md).
  - Baseline numbers: V0-k32 on `smoke`, and on `dev-eval` if the run finishes.
  - Blockers found and how they were handled (free-tier limits, Gemini, Cap 4 RAM).
  - Plan to Nov 15: this schedule, the experiment matrix (§4) and the scope cut (§1).

**Stage 2: Build (Mon Nov 2 – Sun Nov 8)**

- [ ] **A:** own runner and agent with the same output format as upstream (V1 parity check);
  trace logging; executor with schema validation and argument repair (V3).
- [ ] **B:** BM25, dense and hybrid (RRF) retrieval; pick k from the Recall@k curve (V2).
  Plan-then-act with state-store slots for Cap 3 (V4).
- [ ] **C:** `diagnostics.py` on top of traces. If Cap 4 is in scope: document retrieval,
  policy guard and abstention (V6).

**Stage 3: Experiments and analysis (Mon Nov 9 – Thu Nov 12)**

- [ ] **All:** V1–V4 (and V6 if in scope) on `dev-eval`, one variant per day of quota.
- [ ] **B:** retriever ablations (offline, no LLM cost).
- [ ] **C:** error taxonomy over failed items, about 20 per capability, with representative
  success and failure traces.
- [ ] **Thu Nov 12:** code freeze. Only bug fixes for reported numbers after this.

**Stage 4: Report and submission (Fri Nov 13 – Sun Nov 15)**

- [ ] **All:** results table, ablation table, error analysis and limitations written up. The
  report skeleton (design and method sections) should be drafted from Nov 9, in parallel with
  Stage 3.
- [ ] **All:** README reproducibility pass; every reported number links to a `run_id`.
- [ ] **Sun Nov 15:** submit.

### Original schedule (v0.1, superseded)

Kept for the record of Week 0 statuses. Dates after 2026-11-15 no longer apply.

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
- [ ] **A:** create the git repo; add upstream at `third_party/vakra` pinned to `00dc68f`; get
  data, image, containers and MCP validation working on at least one machine.
  *Partly done (2026-10-27), one machine (Anurag's laptop, 7 GiB RAM):*
  - Repo, submodule, train data and image are done.
  - Containers, MCP and checksums validated for Caps 1–3 via our scripts. Upstream's `make`/
    Compose path doesn't work on this machine; see [results/phase0.md](results/phase0.md).
  - **Cap 4 is not started**: 7 GiB RAM is less than its 8 GB limit, plus a 7.8 GB index.
- [ ] Everyone: run the upstream smoke test on one domain per capability. Browse the tools in
  `tools_explorer`. *Caps 1–3 smoke run on one machine (V0 and V0-k32); Cap 4 not run;
  teammates not yet.*

**Week 1 (Nov 2 – Nov 8)**

- [x] **C:** write `scripts/make_splits.py` and commit the `smoke`, `dev-seen`, `dev-heldout`
  and `train-rest` uuid lists. *(Done early, 2026-10-27; see [splits/README.md](splits/README.md).)*
- [x] **C:** set up the evaluation wrapper `scripts/evaluate.py` around upstream
  `evaluator/evaluator.py`; make it run end to end on `smoke`. *(Verified on Caps 1–3 smoke
  runs.)*
- [ ] **All:** data exploration notebook. Cover tool counts per domain, hop distribution, policy
  types and unanswerable rate in Cap 4. Answer the open questions in SPEC §11. *Partial: some
  first statistics are in results/phase0.md; no notebook yet.*
- [ ] **A:** **V0 baseline.** Run the upstream `LangGraphReActAgent` on `dev-heldout` for all
  4 caps with the chosen model, then score it. ***Blocked*** by free-tier limits; see §6.1.
  Smoke-only results so far: V0-k32 on Groq scored Cap 2 4/6 and Cap 3 0/4.

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

**Scope for 2026-11-15:** V0 (as V0-k32), V1, V2, V3 and V4 on Caps 2 and 3. V5 only if time
allows. V6 only if Cap 4 is in scope ([§1](#1-objectives)). V7 is dropped.

**Ablations for the report:**

- Retriever type (BM25 / dense / hybrid) × k ∈ {5, 10, 20, 50}. Offline, so it costs no quota.
  Reranking is a stretch goal.
- ReAct vs. plan-then-act, bucketed by hop count.
- Prompt-only policy vs. guard in code, only with V6.
- Dropped for the deadline: document expansion, and a second LLM.

## 5. Risks and mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| LLM API cost. A full test run is ~5.2k dialogues × several LLM calls each, plus judge calls | High | High | Budget first; iterate on `smoke` / `dev`; cache LLM responses by prompt hash; use an open-weights model via a cheap or free endpoint for development |
| Laptop hardware (35 GB disk, 8 GB Docker RAM) | **Occurred** (7 GiB laptop) | High | Subset data (~6 GB) and CPU image (2.75 GB) keep Caps 1–3 on the laptop; Cap 4 needs a ≥ 16 GB machine (lab server or cloud VM) |
| Free-tier LLM limits block the baseline | **Occurred** | High | See §6.1. Groq 8K TPM is smaller than one Cap 1–3 request at default top-k; Gemini 3.x is incompatible with upstream's agent path |
| Slow or unstable campus network (PyPI 30–150 kB/s) | **Occurred** | Medium | pip retries in the image build; keep images and data on one host and share them |
| Test domains unseen in train | High | Medium | `dev-heldout` split by domain; avoid domain-specific hand rules |
| Permitted resources and submission format only published late | Medium | Medium | Keep the provider swappable; avoid dependencies on proprietary-only features |
| PolicyJudge stays private | Medium | Low | Own rule-based policy checker for diagnostics; request access early |
| Upstream repo changes mid-project | Medium | Medium | Pin the commit; bump only deliberately and re-run V1 parity |
| Evaluator LLM judge is noisy | Medium | Low | Fixed judge model; report CIs; inspect disagreements by hand |
| Holiday period clashes with the January evaluation window | Medium | Medium | Freeze the config by 2027-01-03; dry-run the full pipeline before then |
| 17 days to the 2026-11-15 deadline; one slipped stage leaves no time for the report | High | High | Scope cut in §1; fixed `dev-eval` subset; code freeze on Nov 12; report drafted from Nov 9 in parallel |
| Free-tier quota covers about one `dev-eval` run per day | High | High | One variant per day in Stage 3; iterate on `smoke`; retriever ablations offline; fall back to Groq's paid tier if a run fails and needs repeating |

## 6. Open decisions

These must be settled in Week 0. Record each decision and its date here.

1. **Agent LLM and budget.** *Phase 0 decision (2026-10-27):* Groq free tier,
   `openai/gpt-oss-120b`, for the judge (fixed) and the primary agent series. Evidence and open
   choice for the dev-heldout baseline:

   | Option | Fits VAKRA? | Cost | Caveat |
   |---|---|---|---|
   | Groq free, default V0 (top-k 128) | **No.** Every Cap 1–3 request is 11K–14K tokens vs. an 8K TPM limit | Free | — |
   | Groq free, V0-k32 (`--top-k-tools 32`) | Yes for Caps 2–3 smoke; 1,000 requests/day limits dev-heldout to several days | Free | Not the upstream default; Cap 1 still rejected for large domains |
   | Groq paid tier, default V0 | Likely: higher TPM | Paid | Needs a team budget decision |
   | Gemini `gemini-3.8-flash` via upstream agent | **No.** Multi-step fails (missing `thought_signature`), and 150–437 s per call | Free | Works only with a client that preserves thought signatures (Phase 1 runner) |
   | Open weights on our own GPU (vLLM, OpenAI-compatible) | Yes, no TPM limit | Free if hardware is available | Needs a GPU host; Kaggle notebooks can't run the Docker environment |

   *Decided (2026-10-29):* **Groq free tier with `--top-k-tools 32` (V0-k32)** is the reference
   baseline for every comparison, scored on `dev-eval`. Groq's paid tier is the fallback if a
   run has to be repeated within a day. The report must call it V0-k32, not upstream's default
   V0.
2. **Kaggle** (`kaggle.json` is set up): useful for GPU work that needs no containers, such as
   training a tool retriever (decision 5). It can't host the benchmark containers.
3. **Course deadlines:** *Decided (2026-10-29):* midterm checkpoint on **2026-10-31**, final
   submission on **2026-11-15**. The plan is compressed to fit ([§3](#3-timeline)). Still to
   confirm: the grading criteria, and the midterm's format (report, slides or demo).
4. **Official SemEval submission:** yes or no? If yes, which subtasks? The FAQ allows any subset.
5. **Fine-tuning:** allowed and wanted? For example, fine-tuning a small tool-retriever
   bi-encoder or cross-encoder on train (query → gold tool) pairs is cheap and fits the IR
   course well.
6. **Compute host:** where do the containers and data live, and who has access? *Now urgent:
   Cap 4 needs a machine with ≥ 16 GB RAM.* *2026-10-29:* Aayush's machine is the Cap 4
   candidate and the second machine. It has 15 GiB RAM and 24 CPUs, no GPU. Docker 29.1 and
   Compose v2 are installed, and 59 GB of disk is free, so the ChromaDB index fits. Close other
   apps while the Cap 4 container runs: its limit is 8 GB, and about 10 GiB is usually free.

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

All items except the last are due **2026-11-15**.

- [ ] Reproducible code: setup instructions, configs, scripts (README).
- [ ] Baseline (V0-k32) and best variant for each capability in scope.
- [ ] Results table: official metric plus diagnostics, baseline vs. variants.
- [ ] Ablation tables ([§4](#4-experiment-matrix)).
- [ ] Error taxonomy with representative success and failure traces.
- [ ] Course report (design, method, results, limitations).
- [ ] (Optional, after the deadline) SemEval submission files and system paper. The evaluation
  window is January 2027.
