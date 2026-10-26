# VAKRA-Advanced: Technical Specification

Status: **draft v0.1 (2026-10-26)**. Owners: Anurag Kaushal, Aayush Pandey, Piyush Agarwal.

This document defines **what we build and how it is judged**. Facts about the official environment
were read from `IBM/vakra@00dc68f` (2026-09-22), the HF dataset card, and the task site on
2026-10-26. Items still unconfirmed are listed in [§11](#11-open-questions-to-verify).

---

## 1. Goal

Build an agent that, for each VAKRA dialogue, emits a **tool-call trajectory and a final answer**
that score as correct under the official evaluator, for as many of the four capabilities as time
allows.

Priority order (from the proposal): **2 → 3 → 4 → 1**.

Two secondary goals, because this is an IR course:

- treat tool selection and document selection as **retrieval problems**, and evaluate them with
  IR metrics;
- report a clean comparison of baseline vs. improved variants.

**Non-goals:**

- changing the official environment or evaluator;
- training a large model from scratch;
- optimizing for the public leaderboard over the SemEval test.

---

## 2. Environment facts (verified)

### 2.1 Runtime

- One Docker image (`benchmark_environ`) runs as **four containers**, one per capability:
  - `capability_1_bi_apis`
  - `capability_2_dashboard_apis`
  - `capability_3_multihop_reasoning`
  - `capability_4_multiturn`
- The client talks to them over **MCP stdio via `docker exec`**, not over a network socket.
- An MCP server is started per domain run. `MCP_DOMAIN` must exactly match a domain name, or the
  server fails silently and returns empty results.
- Resources: ≥ 8 GB RAM for the container runtime (Cap 4 ChromaDB) and ~35 GB disk for data.
- Running several domains in parallel spawns one Python process per domain inside the same
  container. Raise `mem_limit` if processes are OOM-killed.
- The upstream runner's per-item timeout is `AGENT_TIMEOUT_SECONDS`, default **300 s**.

| Cap | MCP server | Backend | Tools the agent sees |
|---|---|---|---|
| 1 | `RouterMCPServer` (routes to SLOT or SEL tools per query) | SQLite, direct | `get_data(tool_universe_id)`, plus generic data ops (SLOT: filter / sort / aggregate / transform / retrieve / concatenate …) or expanded parameterized getters (SEL, avg. ~4 per instance) |
| 2 | `FastAPIMCPServer` | SQLite via M3 REST :8000 | 6–328 endpoint tools per domain (avg. 116) |
| 3 | BPO FastMCP (`bpo` domain) or `FastAPIMCPServer` | BPO in-process / SQLite via :8000 | Endpoint tools |
| 4 | `Capability4CombinedMCPServer` | SQLite via :8000 + ChromaDB via :8001 | M3 REST endpoint tools + `retriever_*` tools for the primary domain **plus distractor ("negative") domains** |

**Capability 1 handle system.** Data never travels in full:

- Every tool returns a *peek* of the form
  `{"handle": "...", "num_records": N, "key_details": [{"name", "dtype", "first_3_values"}]}`.
- Later calls reference that data by passing the handle as `data_label` / `data_source`.
- The runner calls `get_data(tool_universe_id=<uuid>)` before each item. That call switches the
  dataset and returns the initial handle.

**Tool-count limit.** The OpenAI tools spec allows at most **128 tools per call**, so a
shortlisting step is mandatory for large Cap 2 domains. Upstream's default is
`--top-k-tools 128`, using MiniLM embeddings over `name: description`.

### 2.2 Data

| Capability | Train (domains / samples / avg calls / max calls) | Test (domains / samples / avg calls / max calls) |
|---|---|---|
| 1 API Chaining | 33 / 1,324 / 4.05 / 12 | 54 / 2,077 / 3.96 / 10 |
| 2 Tool Selection | 40 / 1,860 / 1.00 / 1 | 17 / 1,597 / 1.00 / 1 |
| 3 Multi-hop API | 28 / 346 / 2.05 / 3 | 38 / 869 / 2.04 / 5 |
| 4 Multi-source + policy | 36 / 898 / 1.05 / 3 (avg 2.06 turns, max 5) | 41 / 644 / 1.34 / 4 (avg 2.01 turns, max 7) |

**On-disk layout** (after `make download`):

```
data/
  databases/<domain>/{domain.sqlite, database_description/}
  indexed_documents/              # ChromaDB collections for Cap 4
  train/<capability_dir>/{input,output}/<domain>.json
  test/<capability_dir>/input/<domain>.json       # gated; requires registration
```

The test split has **more domains than train** for Caps 1, 3, 4 and **fewer** for Cap 2. Some
test domains are probably unseen in training, so all dev evaluation must include
**held-out domains** ([§7.1](#71-data-splits)).

### 2.3 Input / output contract

**Input record:**

```json
{
  "uuid": "…", "domain": "olympics", "num_turns": 2,
  "dialogue": {"turns": [
    {"turn_id": 0, "query": "…", "answer": "…"},
    {"turn_id": 1, "query": "…"}
  ]},
  "additional_instructions": "Only use retrievers for Retail, Sales & Commerce, …"
}
```

- `answer` appears only on **historical turns**, and only in Cap 4. The last turn never has one.
- `additional_instructions` (the tool-use policy) is Cap 4 only.

**Output** (one JSON array per domain file, `output/<capability_dir>/<domain>.json`):

```json
[{
  "uuid": "…", "domain": "hockey", "status": "success", "error": "", "duration_s": 3.14,
  "output": [{
    "turn_id": 1, "query": "…", "answer": "16",
    "sequence": {"tool_call": [{"name": "get_hockey_teams", "arguments": {"season": 2018}}]}
  }]
}]
```

- Validate with upstream `validate_output.py` before every submission.
- `*_tools.json` sidecar files are ignored by the validator.
- If a file has duplicate `uuid`s, the evaluator silently keeps the last one.

---

## 3. How we are scored, and what it implies

Read from `evaluator/scorer.py`, `judge.py` and `constant.py`. The evaluator
**re-executes our tool calls** and ignores any tool responses we submit. It then scores
**only the last turn** of each dialogue, as a **binary** value, in this order:

1. **PolicyJudge** (Cap 4 only, if enabled). A violation scores 0 immediately.
   - The judge file is private. Access is requested through a GitHub issue.
2. **ExactMatchJudge** (deterministic). Pass if *every* ground-truth tool response string appears
   among our **last 20** tool responses (`N_TOOL_CALLS_PER_TURN = 20`).
3. If exact match fails, **CorrectnessJudge** runs: an LLM judge with a CRAG-style prompt compares
   our answer to the ground-truth answer. A fail scores 0.
4. **GroundednessJudge**: an LLM judge checks that our answer is supported by our executed tool
   outputs. Its verdict *is* the turn score.
5. **Unanswerable case:** if the ground-truth answer contains "i can not answer" and we make no
   tool calls (or give an empty answer), we get full credit.

- The judge LLM is `openai/gpt-oss-120b`, reached via an OpenAI-compatible endpoint
  (env `API_KEY`; Groq by default).
- The leaderboard averages capabilities equally. On the leaderboard, Cap 4 multi-source queries
  are weighted 2×. The SemEval ranking rules are not published yet.

**Design implications (these drive the architecture):**

| # | Implication | Consequence for us |
|---|---|---|
| I1 | Reproducing the ground-truth tool *responses* is the most reliable way to score | Getting the right tool with exact arguments matters more than answer prose |
| I2 | Extra or exploratory calls are **not penalized** (only logged as `extra_steps`) | Probing calls (e.g. looking up an ID, trying a variant) are safe, provided the decisive calls stay within the **last 20** |
| I3 | The answer must be grounded in *our* tool outputs | Never answer from parametric knowledge. The answer synthesizer may only use evidence from the state store |
| I4 | Calls are replayed | Every recorded call must be valid and deterministic. Drop failed or erroring calls from the submitted trajectory, or keep them only if harmless |
| I5 | Only the final turn is scored | In Cap 4, earlier turns are *context*. Their answers are given in the input, so we do not re-solve them |
| I6 | A correct abstention earns credit | Cap 4 needs a calibrated "I can not answer" path, with **zero** tool calls, for policy-blocked or unanswerable queries |

---

## 4. System architecture

```
                 ┌────────────────────────────────────────────────────────────┐
 input dialogue →│ Request Interpreter  (goal, entities, constraints, policy) │
                 └──────────────┬─────────────────────────────────────────────┘
                                ▼
          ┌──────────────────────────────┐    ┌───────────────────────────┐
          │ Tool Retriever (IR)          │    │ Policy Guard              │
          │ BM25 + dense + rerank        │◄───│ allowed/forbidden tools   │
          └──────────────┬───────────────┘    └───────────────────────────┘
                         ▼
          ┌──────────────────────────────┐   tool call    ┌──────────────────┐
          │ Planner / Tool Selector (LLM)│──────────────► │ Execution Engine │──► MCP (docker exec)
          │ plan → next call + arguments │◄────────────── │ validate, repair │
          └──────────────┬───────────────┘   result/error └────────┬─────────┘
                         │                                         ▼
                         │                           ┌──────────────────────────┐
                         └──────────────────────────►│ State & Evidence Store   │
                                                     │ handles, IDs, provenance │
                                                     └────────────┬─────────────┘
                                                                  ▼
                                                     ┌──────────────────────────┐
                                                     │ Answer Synthesizer       │→ answer + trajectory
                                                     └──────────────────────────┘
```

### 4.1 Components

| Component | Responsibility | Interface (sketch) |
|---|---|---|
| `runner` | Load items; open one MCP session per (capability, domain); call `get_data` for Cap 1; invoke the agent; write official output and our trace | `run(config) -> run_dir` |
| `interpreter` | Pull out the target quantity, entities and literals; resolve coreference from history (Cap 4); classify the query type | `interpret(dialogue) -> Intent` |
| `tool_retrieval` | Index each domain's tool catalog; return the top-k tools for a query or sub-query | `build(tools) / search(query, k) -> [ToolHit]` |
| `policy` | Parse `additional_instructions` once per dialogue into a structured rule; filter tools; decide whether to abstain | `parse(text) -> Policy`, `allowed(tool, intent) -> bool` |
| `planner` | Choose the next call (ReAct), or emit an explicit plan of sub-questions first (plan-then-act). Swappable strategy | `next_action(state) -> ToolCall \| Finish` |
| `executor` | Check arguments against JSON schema; normalize types; fuzzy-map argument names and values (e.g. column names); execute; classify errors; allow ≤ 2 repair attempts; enforce the step budget | `execute(call) -> Observation` |
| `state` | Append-only log of calls, observations, handles, extracted IDs and entities, each with provenance | `add(obs)`, `lookup(key)`, `trajectory()` |
| `doc_retrieval` | Rewrite the query using dialogue context; choose the right `retriever_*` tool (primary vs. distractor collections); extract the evidence span | `retrieve(intent, state) -> [Passage]` |
| `answer` | Write the final answer **only** from evidence in the state store; copy exact values; use the abstention template when needed | `synthesize(state) -> str` |
| `llm` | Provider-agnostic chat and tool-calling wrapper. Reuses upstream `agents/llm.py` (LangChain / LiteLLM) and logs tokens and latency | `chat(messages, tools) -> Reply` |

**Integration with upstream.** Upstream `benchmark_runner.py` hard-codes `LangGraphReActAgent`
(`_get_agent()` and an `assert isinstance(...)`). So:

- we implement upstream's `AgentInterface.run(input, additional_instructions)` in our own agent;
- we drive it from **our own runner**, which reuses `benchmark.mcp_client`,
  `agents.mcp_tool_wrapper.MCPToolWrapper` and `benchmark.runner_helpers`;
- upstream stays **unmodified** in `third_party/vakra`, pinned to a commit.

---

## 5. Per-capability strategy

### Capability 2: Tool Selection (start here)

One gold call per query. Success means picking the right tool from about 116 candidates and
filling its arguments exactly.

1. **Tool retrieval, the core IR contribution.**
   - Document = tool name (snake_case split, version and route suffixes removed) + description
     + parameter names and descriptions.
   - Retrievers: BM25, dense (bi-encoder), and hybrid (Reciprocal Rank Fusion), with an optional
     cross-encoder reranker on top.
   - **Document expansion:** append train queries whose gold call used that tool (doc2query-style
     expansion; on held-out domains, use LLM-generated synthetic queries instead).
   - Report Recall@{1,5,10,20} and MRR against gold tools. Then give the LLM only the top-k
     (k ≈ 10–20) instead of 128.
2. **Argument filling.** Use the schema-constrained call, plus value normalization: dates,
   numbers, casing, and matching entity strings against values seen in the database or in earlier
   outputs.
3. **Answer.** Render the tool output faithfully. The blog reports that strong models often make
   the right call and still answer wrongly.

### Capability 3: Multi-hop API Reasoning

1–3 hops in train, up to 5 in test.

1. **Plan-then-act:** decompose the query into hop sub-questions. Run tool retrieval *per hop*.
2. **Carry entities through the state store.** IDs and names from hop *i* become typed slots for
   hop *i+1*. The LLM fills arguments from slots, not from raw JSON.
3. **Hop checks:** an empty or erroring result triggers a re-plan (an alternate tool or
   argument). Probing is allowed under I2.
4. Compare against plain ReAct, bucketed by hop count.

### Capability 4: Multi-hop, Multi-source with Policies

1. **History handling:** earlier turns and their gold answers are context. Resolve references
   like "these" or "that team" into an explicit query.
2. **Policy guard (in code, not just in the prompt).**
   - Parse the policy into `{topic/domain scope → allowed source types}`.
   - Remove forbidden tools before the planner sees them.
   - If the only viable source is forbidden, **abstain with zero calls** (I6).
3. **Source routing:** decide API vs. retriever vs. both. Choose the right retriever collection
   by matching the query against the domain descriptions shipped upstream
   (`environment/retrievers/domain_description_dict.json`), while avoiding the distractor
   collections.
4. **Retrieval:** rewrite the query (context-resolved and keyword-focused), then extract the
   evidence span. Align text-derived values to API parameter formats.

### Capability 1: API Chaining (BI APIs)

The main failure is **wrong argument or column names**; with SEL tools, it is also tool choice.

1. Put the full `get_data` peek (all columns, dtypes and sample values) in the prompt, plus the
   database description.
2. **Executor-side grounding:** before executing, fuzzy-map `key_name`, `data_label` and similar
   arguments to existing columns and handles.
3. **Retrieved few-shot examples:** find the *k* most similar train queries (BM25 or dense) and
   show their gold tool sequences.
4. Make one call per step (upstream's default iteration cap is 10).

---

## 6. LLM usage

- **Provider-agnostic** through one config key. Candidates: an open-weights model via
  Groq / Ollama / vLLM, or an API model. The choice is pending ([PLAN.md §6](PLAN.md#6-open-decisions)).
- Default `temperature = 0`. Use the same model for all variants in a comparison.
- Separate the *agent* LLM from the *judge* LLM (fixed: `gpt-oss-120b`), so that our metric is
  never self-graded.
- Log prompt/completion tokens, call count and latency per item.

---

## 7. Evaluation protocol

### 7.1 Data splits

| Split | Source | Use |
|---|---|---|
| `smoke` | ~10 items × 4 caps, fixed | CI-style sanity check on every change (< 10 min) |
| `dev-seen` | 15 % of items from train domains, stratified by domain | Fast iteration |
| `dev-heldout` | All items from ~20 % of train **domains**, per capability | **Primary model-selection metric.** Mimics unseen test domains |
| `train-rest` | Remainder | Few-shot pool, doc2query expansion, error mining |
| `test` | Official, gated (registration required) | Final runs only, during the evaluation window |

- Splits are produced by `scripts/make_splits.py` with a fixed seed and committed as uuid lists.
- No information from held-out domains may enter indexes or few-shot pools when scoring
  `dev-heldout`.

### 7.2 Metrics

**Official metric (headline):**

- mean dialogue score per capability, computed with the upstream evaluator against train ground
  truth;
- macro-average over capabilities.

**Diagnostics (ours), computed from traces against gold trajectories:**

| Area | Metric |
|---|---|
| Tool retrieval | Recall@k and MRR of gold tools in the shortlist (Caps 2–4) |
| Tool selection | Exact tool-name match with gold, per step |
| Arguments | Exact argument match given the correct tool; schema-valid call rate; execution error rate |
| Multi-hop | Hop completion rate; score bucketed by gold hop count |
| Scoring path | Fraction of passes through exact match vs. correctness judge; groundedness failure rate |
| Policy (Cap 4) | Violation rate (our own checker); abstention precision and recall |
| Efficiency | Tool calls, LLM calls, tokens, latency and $ per item |

### 7.3 Experiment rules

- Every run is defined by a YAML config and identified by `run_id = <date>-<short-hash>`.
- Every run logs the config, our git SHA, the upstream SHA and the model name.
- Each comparison changes **one factor** at a time. Report the mean on `dev-heldout`.
  Use a paired bootstrap 95% CI when the difference is < 3 points.

---

## 8. Traces and artifacts

Per run, in `runs/<run_id>/` (gitignored):

- `config.yaml`
- `output/<capability_dir>/<domain>.json`: official format, ready for submission
- `traces.jsonl`: per item, the shortlist with scores, every LLM call (messages, tokens,
  latency), every tool call with result or error and repair attempts, state snapshots, and the
  final answer
- `eval/results.json`: upstream evaluator output
- `diagnostics.json`: our metrics from [§7.2](#72-metrics)

---

## 9. Repository layout (target)

```
VAKRA-Advanced/
├── README.md  PLAN.md  SPEC.md  VAKRA_Advanced_Project_Proposal.pdf
├── third_party/vakra/          # upstream benchmark, pinned, unmodified (data/ lives here, gitignored)
├── src/vakra_adv/
│   ├── runner.py  agent.py  llm.py
│   ├── interpreter.py  planner.py  executor.py  state.py  answer.py  policy.py
│   ├── tool_retrieval/         # index.py, bm25.py, dense.py, rerank.py, expand.py
│   └── doc_retrieval.py
├── configs/                    # baseline.yaml, cap2_hybrid.yaml, …
├── scripts/                    # make_splits.py, evaluate.py, diagnostics.py, analyze_errors.py
├── splits/                     # committed uuid lists
├── tests/                      # unit tests (executor, policy parser, retrieval), smoke run
├── notebooks/                  # data exploration, error analysis
├── runs/                       # gitignored
└── report/                     # course report + SemEval system paper
```

**Conventions:**

- Python 3.11, type hints, `ruff` for lint and format, `pytest`.
- Secrets live in `.env` (gitignored) and are never committed.

---

## 10. Constraints and compliance

- Follow the organizers' rules on permitted resources and submission format. These are to be
  published before the evaluation window, so keep the model and provider swappable.
- The data license is CC BY-NC-SA 4.0. Do not publish derived indexes without that license.
- Never train on or tune against the gated test split.

---

## 11. Open questions to verify

1. Are Cap 2 test domains disjoint from train domains? Check after download, and compare against
   the test inputs once registered.
2. Cap 1: during replay, does the evaluator re-issue `get_data` itself, or must our trajectory
   include it? Compare the gold `output` sequences (`initialize_active_data`, `$label.data_path$`
   references) with what upstream records.
3. Exact string format of tool responses compared by ExactMatchJudge. Does dict key order or
   float formatting ever break matching?
4. How does the official SemEval ranking weight the capabilities? (Not published yet.)
5. Can we get PolicyJudge access (GitHub issue) for local Cap 4 scoring?
6. Exact directory names under `data/train/` after `make download` (the HF card shows
   `capability-X`; the repo uses `capability_N_<name>`).
