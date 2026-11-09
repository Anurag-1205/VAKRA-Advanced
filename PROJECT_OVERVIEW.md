# VAKRA-Advanced: what it is, what we have done, what is left

*Status as of 2026-11-09. Team: Anurag Kaushal, Aayush Pandey, Piyush Agarwal.*

This page is the short version. The details live in [PLAN.md](PLAN.md) (schedule and decisions),
[SPEC.md](SPEC.md) (environment and scoring facts), [results/](results/) (all measured numbers)
and the midterm report, [report/Phase_1_report.pdf](report/Phase_1_report.pdf).

---

## 1. What the project is

VAKRA-Advanced is our course project for **Information Retrieval and Extraction**. It is also our
planned entry to **SemEval-2027 Task 11**.

The task is to build an **LLM agent that answers questions by calling tools**, instead of
answering from what the language model already knows. The tools run in IBM's **VAKRA**
environment:

- more than **8,000 APIs** over real SQLite databases, in **62 domains** (hockey, cars, movies,
  sales, …);
- **document collections** for questions the APIs cannot answer alone;
- each domain offers anywhere from 6 to about 330 tools.

### The four capabilities

The benchmark tests four capabilities. We also call them Tasks 1–4.

| # | Capability | What the agent must do |
|---|---|---|
| 1 | API chaining | Run a chain of generic data operations (filter, sort, aggregate, …) on a dataset, each step building on the last |
| 2 | Tool selection | Pick the one right API out of a large catalog and fill in its arguments |
| 3 | Multi-hop API reasoning | Chain several APIs, where one call's output is the next call's input |
| 4 | Multi-turn, multi-source, with policies | Hold a dialogue that mixes API calls and document search, while obeying a plain-English rule about which tools may be used, and refuse when the rule forbids every useful tool |

### How answers are scored

The official evaluator gives each item **1 or 0**:

1. It **replays the agent's tool calls** against the live APIs. If they return what the expected
   ("gold") calls return, the tool use counts as correct.
2. Otherwise, an **LLM judge** decides whether the final answer is still correct.
3. A second judge checks that the answer is **grounded**: backed by what the tools actually
   returned. A right answer that was not taken from the tool outputs scores 0.
4. A correct refusal ("I can not answer", with no tool call) also scores 1.

For multi-turn dialogues (Capability 4), only the **final turn** is scored. A capability's score
is the share of items that score 1.

### Our approach

1. Run IBM's own agent unchanged as the **baseline (V0)**, and measure where it loses points.
2. Build our own agent as a series of **variants (V1–V6)**. Each one fixes one measured failure.
3. Score every variant on the same items, with the same model and the official judge, so that
   only real improvements count.

Shortlisting tools is where the "information retrieval" part of the course comes in. A domain can
have 300 tools, too many to show the model, so the agent first **retrieves** the most relevant
ones: each tool's description is a document and the user's question is the query.

---

## 2. What we have done (up to the midterm, 2026-10-31)

### 2.1 Environment set up and reproduced on two machines

- IBM's environment (Docker containers, databases, a 7.8 GB document index) runs on both team
  machines, and scores reproduce exactly between them.
- IBM's code is pinned at a fixed version and never modified. Our scripts in
  [scripts/](scripts/) wrap it, and work around several problems we hit:
  - the official download script reaches for a restricted test set whenever it finds any login
    token, so ours downloads only the public data;
  - the image build times out on slow networks, so ours can retry with a faster installer;
  - newer versions of one library break the official evaluator, so we pin it.

### 2.2 Choosing the language model

This took longer than planned:

- **Groq's free tier** rejected every request. The descriptions of 128 tools alone need 11–14K
  tokens, against its limit of 8K tokens per minute. With a 32-tool shortlist, a daily limit of
  200K tokens still allowed only about 25 items a day.
- **Gemini 3** failed at the second tool call, because the LangChain library drops a field Gemini
  requires.
- We settled on **`gpt-oss-120b` on Groq's paid tier**, temperature 0, for both the agent and the
  judge. The three baseline runs cost **$2.00** in total, so testing one variant costs about $2.

### 2.3 An honest evaluation set

- We hold out **nine domains** from every capability. Capabilities 2–4 share each domain's tools,
  so holding a domain out of only one capability would leak its tools through the others.
- **`dev-eval`** is a fixed sample of those held-out domains, spread across domains:
  **60 / 120 / 35 / 60** items for Capabilities 1–4. Every result is scored on it.
- The official test set is restricted. Access has been requested; until it arrives, all scores
  are on held-out *training* domains.

### 2.4 What the data looks like

From [results/data_stats.md](results/data_stats.md):

- Every Capability 2 item is **exactly one tool call**, so it is purely a selection problem.
- 90% of Capability 3 items are **exactly two hops**.
- 60% of Capability 1 items need **three or more** data operations.
- In Capability 4, documents are rare (3% of turns). In **15–18% of dialogues the only correct
  final answer is a refusal**, because the dialogue's policy forbids the tool the question needs.

### 2.5 Baseline scores

IBM's agent, unchanged, on `dev-eval` ([results/baseline_dev_eval.md](results/baseline_dev_eval.md)):

| Tool shortlist | Cap 2 (n = 120) | Cap 3 (n = 35) | Cap 4 (n = 60) |
|---|---:|---:|---:|
| **128 tools (default, V0)** | **0.408** | **0.343** | **0.350**\* |
| 32 tools | 0.425 | 0.171 | not run |
| 95% interval | ±0.09 | ±0.16 | ±0.12 |

\* 0.300 without 3 dialogues that were credited even though the agent crashed.

Capability 1 has no baseline yet; the midterm report defers it to the next phase.

### 2.6 Tool retrieval

How often **all** of an item's gold tools make it into the shortlist (recall@k), plus MRR, on all
held-out items ([results/tool_recall.md](results/tool_recall.md)):

| Cap | Retriever | R@10 | R@32 | R@128 | MRR |
|---|---|---:|---:|---:|---:|
| 2 | Dense (MiniLM, IBM's default) | **.879** | .953 | **.996** | .608 |
| 2 | BM25 (keyword) | .779 | .928 | .992 | .486 |
| 2 | Hybrid (both, fused) | .875 | **.969** | **.996** | **.610** |
| 3 | Dense (MiniLM, IBM's default) | .343 | .714 | .943 | .624 |
| 3 | BM25 (keyword) | **.371** | .714 | **1.00** | .540 |
| 3 | Hybrid (both, fused) | .314 | **.800** | **1.00** | **.685** |

### 2.7 What we found

1. **Shortlisting is the bottleneck for multi-hop questions.** With 32 tools, all the needed
   tools survive for only 71% of Capability 3 items, because later hops are often not named in
   the question. That is why the 32-tool score halves. Hybrid retrieval raises this to 80% at the
   same size.
2. **About a fifth of items fail on a tool-schema bug, not a model mistake.** 22.5% of
   Capability 2 and 17.1% of Capability 3 items end with Groq rejecting a tool call for a
   "missing argument". For tools that take no parameters, the official code passes no schema, so
   LangChain invents one with a required internal `config` field. The model's call is correct,
   but it gets rejected anyway.
3. **Correct work still scores 0.** 10%, 9% and 17% of Capability 2, 3 and 4 items get the right
   tool outputs or answer but fail the groundedness check, for example by answering from a later
   call that dropped the question's filters.
4. **Capability 4 loses points to context length and policy.**
   - 17% of dialogues carry 1.9–9.7 million characters of history and fit no model's context.
   - The agent never refused on purpose: it got 0 of the 11 dialogues that require a refusal.

### 2.8 Midterm report

Written and submitted: [report/Phase_1_report.pdf](report/Phase_1_report.pdf)
(source: [report/phase1_report.tex](report/phase1_report.tex)).

---

## 3. What is left (2026-11-09 → 2026-11-15)

### 3.1 Where we stand on the schedule

| Stage | Dates | Status |
|---|---|---|
| 1. Setup, baseline, midterm | to Oct 31 | **Done** |
| 2. Build our agent (V1–V4, V6) | Nov 2–8 | **No code in the repository yet** |
| 3. Experiments and analysis | Nov 9–13 | Starts now; **code freeze at the end of Fri Nov 13** |
| 4. Final report and submission | Nov 14–15 | **Submit Sun Nov 15** |

The code freeze was moved from Nov 12 to Nov 13 on 2026-11-09. It is our own milestone, not a
course rule. Stage 2 and Stage 3 now have to happen in the same five days, so the work below is
ordered by expected gain per hour. The full ordered task list, with owners and dates, is in
[POST_MID_WORK.md](POST_MID_WORK.md).

### 3.2 Our agent, in priority order

| Priority | Variant | What it does | Failure it targets | Owner |
|---|---|---|---|---|
| 1 | **V1** | Our own runner, same output format as IBM's. Fix the `config` schema bug, and catch Groq's rejection instead of crashing. Must first match V0 within noise. | ~20% of Cap 2–3 items lost to the schema bug | Anurag |
| 2 | **V2** | Hybrid (BM25 + dense) tool shortlist, with k chosen from the recall curve | Cap 3 shortlist misses; fewer tokens per call | Aayush |
| 3 | **V3** | Check each tool call against its schema and repair bad arguments | Remaining invalid calls | Anurag |
| 4 | **V4** | Plan-then-act: retrieve tools again for each hop | Cap 3 hops the question doesn't name | Aayush |
| 5 | **V6** | Cap 4: shorten long answers in the dialogue history; a policy guard that refuses on purpose | 17% too-long dialogues; up to 18% refusal dialogues | Piyush |
| 6 | V5 *(if time)* | Answer only from collected tool evidence | Groundedness failures (9–17%) | Shared |

### 3.3 Experiments and analysis

- Run each variant on `dev-eval` and compare it with V0 (about $2 and under an hour per variant).
- **Capability 1:** run the V0 baseline once (about $0.30), or drop Capability 1 from scope
  explicitly in the final report.
- **Retriever ablations:** retriever type × shortlist size. These are offline and cost nothing.
  *(Aayush)*
- **Error analysis:** about 20 failed items per capability, with example traces. *(Piyush)*

### 3.4 Final report and submission

- Results table, ablation table, error analysis and limitations.
- A reproducibility check of the README: every reported number links to the run that produced it.
- Submit on **Sun Nov 15**.

### 3.5 Pending outside the code

- **Official test set:** access requested, still pending. Until it arrives, every score is on
  held-out training domains, and the final report must say so.
- **PolicyJudge:** IBM's judge for Capability 4 policies is not public. A request on the
  IBM/vakra repository is still to be filed (optional).
- **After the course:** the SemEval-2027 evaluation itself, on data released through the task's
  registration. Running it needs one full test run, which we estimate at about $35 at current
  rates.
