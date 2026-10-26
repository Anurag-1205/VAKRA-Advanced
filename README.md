# VAKRA-Advanced: Tool-Using LLM Agents for Multi-Hop, Multi-Source Reasoning

Course project for **Information Retrieval and Extraction**. It is also our planned entry to
**[SemEval-2027 Task 11: VAKRA-Advanced](https://sites.google.com/view/vakrasemeval2027/home)**.

We are building a modular LLM agent that:

1. picks the right tools from catalogs of up to ~330 APIs,
2. chains API calls by passing IDs and entities from one call to the next,
3. retrieves evidence from document collections when the APIs are not enough,
4. follows natural-language tool-use policies, and
5. writes a final answer grounded in what the tools returned.

All of this runs against IBM's executable VAKRA environment: 8,000+ locally hosted APIs over
62 domains, backed by real SQLite databases plus ChromaDB document collections.

## Team

| Member | Proposed focus (see [PLAN.md](PLAN.md)) |
|---|---|
| Anurag Kaushal | Agent core: runner, executor, state store; Capability 1 (API chaining) |
| Aayush Pandey | Tool retrieval and selection; Capabilities 2 and 3 |
| Piyush Agarwal | Document retrieval, policy handling; Capability 4; evaluation and error analysis |

## The task in one table

| # | Subtask | What the agent must do | Test size |
|---|---|---|---|
| 1 | API Chaining | Compose generic BI operations (filter, sort, aggregate, …) over a dataset *handle* | 2,077 / 54 domains |
| 2 | Tool Selection | Pick the one correct endpoint out of 6–328 tools (avg. 116) and fill its arguments | 1,597 / 17 domains |
| 3 | Multi-hop API Reasoning | Chain endpoints, where earlier outputs become later inputs (up to 5 hops) | 869 / 38 domains |
| 4 | Multi-hop, Multi-source + Policies | Mix API calls and document retrieval in multi-turn dialogues while obeying tool-use policies | 644 / 41 domains |

Scoring replays our tool calls against the live APIs. The full scoring rules are in
[SPEC.md §3](SPEC.md#3-how-we-are-scored-and-what-it-implies).

## Documents

- **[PLAN.md](PLAN.md)**: milestones, timeline, owners, experiments, risks, open decisions.
- **[SPEC.md](SPEC.md)**: verified environment facts, I/O contract, scoring rules, architecture,
  per-capability strategy, evaluation protocol, repository layout.
- [VAKRA_Advanced_Project_Proposal.pdf](VAKRA_Advanced_Project_Proposal.pdf): the original course proposal.

## Status

**Week 0 (from 2026-10-26):** planning documents only. No code yet.

## Setup

> These are the official environment steps as of the upstream commit we have read
> (`IBM/vakra@00dc68f`, 2026-09-22). Our own agent code is not written yet; this section will
> grow as `src/` lands.

**Requirements:**

- Linux or macOS
- Python ≥ 3.11
- Docker with the Compose plugin, with **≥ 8 GB RAM** given to the container runtime
  (the Capability 4 ChromaDB service runs out of memory at 2 GB)
- **~35 GB free disk**
- `make`
- A Hugging Face token
- An LLM provider (OpenAI / Anthropic / LiteLLM / watsonx key, or a local Ollama)

```bash
# 1. Get the upstream benchmark (we keep it unmodified under third_party/)
git clone https://github.com/IBM/vakra.git third_party/vakra
cd third_party/vakra
git checkout 00dc68f        # pin; bump deliberately

# 2. Python environment
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[init]"
pip install -r requirements_benchmark.txt

# 3. Data (~30–35 GB). Uses HF_TOKEN. Downloads the gated test split if you have access,
#    otherwise the public train split.
export HF_TOKEN=hf_...
make download

# 4. Build the image and start the 4 capability containers.
#    setup.md mentions `make pull`, but the Makefile has no such target, so build locally.
make build
docker compose up -d
sleep 60 && make validate     # checks the live MCP connections

# 5. Smoke test with the upstream ReAct baseline
python benchmark_runner.py --capability_id 2 --domain hockey \
  --max-samples-per-domain 5 --provider ollama --model llama3.1:8b
```

**Optional:** to browse the tool catalogs, run
`cd tools_explorer && uvicorn tools_explorer.app:app --port 7861`.

**Local evaluation:** the official evaluator's LLM judges use `openai/gpt-oss-120b` through an
OpenAI-compatible endpoint (Groq by default). Set `API_KEY` before running
`python evaluator/evaluator.py ...`. See [SPEC.md §7](SPEC.md#7-evaluation-protocol).

## Official resources

- Task site: <https://sites.google.com/view/vakrasemeval2027/home>. Evaluation-data registration
  form: <https://forms.gle/2MLpxaU1kcD1SbCm7>.
- Mailing list: <https://groups.google.com/g/vakra-advanced>
- Code and setup guide: <https://github.com/IBM/vakra> ([setup.md](https://github.com/IBM/vakra/blob/main/setup.md))
- Training data: <https://huggingface.co/datasets/ibm-research/VAKRA>
- Public leaderboard (separate from the SemEval ranking): <https://ibm-research-vakra.hf.space>
- Benchmark analysis blog: <https://huggingface.co/blog/ibm-research/vakra-benchmark-analysis>
- SemEval paper requirements: <https://semeval.github.io/paper-requirements.html>

## License note

The VAKRA data and code are released under **CC BY-NC-SA 4.0**. Anything we redistribute that is
derived from them (e.g. processed data, indexes) inherits those terms. Our own code's license is
still to be decided.
