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

Verified on Ubuntu 24.04 (7 GiB RAM, Docker 29, Python 3.12) against `IBM/vakra@00dc68f`.
Upstream code is never modified; our `scripts/` wrap it.

**Requirements:**

- Linux, Python ≥ 3.11, Docker
- **RAM:** ≥ 8 GB free for Docker is needed only for Capability 4 (ChromaDB)
- **Disk:** ~15 GB for this subset setup (vs. ~35 GB for upstream's full download)
- **API keys** in `.env` (copy [`.env.example`](.env.example)):
  - `API_KEY`: a Groq key. It serves both the official judge and the default agent.
  - `GEMINI_API_KEY`: optional, for the second agent backend.

```bash
# 1. Clone with the upstream benchmark (git submodule pinned under third_party/vakra)
git clone --recurse-submodules https://github.com/Anurag-1205/VAKRA-Advanced.git
cd VAKRA-Advanced          # (already cloned? git submodule update --init)
cp .env.example .env       # then put your keys in .env

# 2. Python env (CPU-only torch saves ~3 GB)
python3 -m venv .venv && source .venv/bin/activate
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -e "third_party/vakra[init]" -r third_party/vakra/requirements_benchmark.txt

# 3. Check the LLM key: model list, one tool call, rate-limit headers. Prints no secrets.
python scripts/check_llm.py

# 4. Data: public train split + databases for the held-out domains (~6 GB).
#    Anonymous, so it never touches the gated test repo. See splits/README.md.
python scripts/download_data.py --train
python scripts/download_data.py --domains authors cars european_football_1 hockey \
    ice_hockey_draft menu sales_in_weather student_loan world

# 5. Image + containers
scripts/build_image.sh           # = upstream `make build`, with CPU-only torch
scripts/containers.sh start 1 2 3   # or `docker compose up -d` if you have Compose v2
scripts/containers.sh status

# 6. V0 baseline on a split, then official scoring (judge: Groq gpt-oss-120b)
python scripts/run_baseline.py --split smoke --caps 1 2 3
python scripts/evaluate.py --run-id <run_id printed above>
```

Notes:

- **Why not upstream `make download`?** It tries the gated test repo whenever *any* Hugging
  Face token is found, including a cached CLI login, and then skips the train split.
- **Compose:** `scripts/containers.sh` mirrors `docker-compose.yml` with plain `docker run`,
  because Ubuntu's `docker-compose` v1.29 rejects that file. Prefer
  `sudo apt install docker-compose-v2`.
- **Splits:** [`splits/`](splits/) holds committed uuid lists. Rebuild or verify them with
  `scripts/make_splits.py`.
- **Runs:** results land in `runs/<run_id>/` (gitignored):
  - `config.json` (models, SHAs, counts, timings)
  - `output/` (official submission format)
  - `eval/` (upstream evaluator reports)

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
