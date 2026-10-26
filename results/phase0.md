# Phase 0 results log (2026-10-27)

Machine: Ubuntu 24.04 laptop, 8 CPUs, 7 GiB RAM, Docker 29.1 (Compose v2 not installed), campus
network. Code: our repo at the commits listed per run; upstream `IBM/vakra@00dc68f`.
Run artifacts live in `runs/<run_id>/` (gitignored). This file is the committed record.

## 1. Environment validation

| Item | Result |
|---|---|
| Python venv (3.12, CPU torch, `mcp<2` via `constraints.txt`) | OK, 1.6 GB |
| Data: public train split + 9 held-out-domain databases (anonymous, no gated access) | OK, 5.7 GB; file counts match the dataset card (33/40/28/36 domains) |
| Image `benchmark_environ` (upstream Dockerfile + CPU torch + pip retries) | OK, 2.75 GB |
| Containers Cap 1–3 (`scripts/containers.sh`) | OK; ~150–260 MiB each |
| Container Cap 4 | **Not started.** Needs the 7.8 GB ChromaDB index and an 8 GB memory limit; host has 7 GiB total |
| MCP connections + upstream tool checksums, Caps 1–3, all 9 held-out domains | OK (`scripts/inspect_tools.py`) |
| Upstream evaluator end to end (ground-truth replay over MCP + Groq judge) | OK after pinning `mcp<2` |

## 2. API tests (no secrets printed)

| Backend | Model | Tool calling | Notes |
|---|---|---|---|
| Groq (`API_KEY`) | `openai/gpt-oss-120b` | OK, raw API and upstream `create_llm` | Free-tier headers: 1,000 requests/day, 8,000 tokens/min. Latency < 1 s |
| Groq judge (upstream `ChatGroq`, `JUDGE_BACKEND=groq`) | `openai/gpt-oss-120b` | n/a | OK |
| Gemini (`GEMINI_API_KEY`) | `gemini-3.8-flash` | First call OK via upstream `create_llm` | 150–437 s per call, even for a 7-token prompt. Multi-step fails, see §4 |

## 3. Runs

All runs use the `smoke` split (held-out domains `authors`, `cars`) and temperature 0.
"mpd" = max items per domain.

| Run id | Agent | Config | Cap | Items | Agent OK | Score | Wall time |
|---|---|---|---|---:|---:|---|---:|
| `20261027-plumbing-v0-gemini-smoke` | gemini-3.8-flash | V0 (top-k 128), mpd 1 | 2 | 2 | 0 | not scored | 432 s |
| `20261027-0354-v0-groq-smoke` | gpt-oss-120b | V0 (top-k 128) | 1 | 6 | 0 | 0/6 = 0.00 | 104 s |
| `20261027-v0-groq-smoke-c23-probe` | gpt-oss-120b | V0 (top-k 128), mpd 1 | 2 | 2 | 0 | not scored | 15 s |
| 〃 | 〃 | 〃 | 3 | 2 | 0 | not scored | 14 s |
| `20261027-0400-v0k32-groq-smoke` | gpt-oss-120b | **V0-k32** (`--top-k-tools 32`) | 2 | 6 | 5 | **4/6 = 0.667** | ~9 min |
| 〃 | 〃 | 〃 | 3 | 4 | 3 | **0/4 = 0.00** | ~10 min |

- **V0** is upstream's default configuration.
- **V0-k32** uses upstream's own `--top-k-tools` flag set to 32, so that requests fit Groq's
  free tier. It is a separate configuration and must not be reported as V0.
- Neither has a Cap 4 result.

## 4. Failures and blockers (with evidence)

1. **Groq free-tier token limit vs. tool-schema size (blocks default V0 on Caps 1–3).**
   - Held-out domains expose 56–236 tools per domain for Caps 2/3.
   - Groq rejected every default-V0 request with HTTP 413: 11,285–14,472 tokens requested
     against an 8,000 TPM limit.
   - My local o200k count of the serialized schemas is higher (~460 tokens/tool), so it
     over-estimates Groq's count. Groq's figure is authoritative.
2. **Groq validates generated tool calls server-side.**
   - When gpt-oss-120b omits a required argument (e.g. `config` for `filter_data`), Groq
     returns HTTP 400 instead of the tool call, and the item ends with no trajectory.
   - Seen in 3/6 Cap 1 items and 1/6 Cap 2 items.
   - This differs from providers that return the malformed call to the agent.
3. **Gemini 3.x is incompatible with upstream's agent path for multi-step tool use.**
   - Gemini attaches a `thought_signature` (in `extra_content`) to each tool call and rejects
     the next request without it: HTTP 400, "Function call is missing a thought_signature".
   - LangChain `ChatOpenAI`, used by upstream `create_llm`, drops that field.
   - Gemini 2.5 models are no longer available to this key.
   - Latency was 150–437 s per call.
4. **Cap 1 on train data needed a universe mapping (fixed).**
   - Upstream's `mcp_tool_universe_id_mapping.yaml` covers gated-test uuids only.
   - `scripts/make_cap1_mapping.py` adds train entries using upstream's generator rules.
5. **Tooling issues (fixed or worked around):**
   - `mcp` 2.x breaks the evaluator (pinned `<2`).
   - `docker-compose` v1 can't parse the compose file (`containers.sh`).
   - PyPI read timeouts at ~30–150 kB/s (pip retries in the image build).
   - Upstream `make download` would try the gated repo using a cached HF login
     (`download_data.py` is anonymous).

**V0-k32 smoke diagnostics:**

- The gold tool was in the top-32 shortlist for 10/10 items. Failures are selection and
  reasoning, not retrieval:
  - Cap 2: one item answered "no data" without calling a tool; one hit failure 2 above.
  - Cap 3: two items stopped after 1 of 2 hops, one timed out at 300 s while being
    rate-limited, and one had a wrong final entity.
- Cap 4 dev-heldout statistics, from ground truth, excluding `authors` (426 MB file):
  - 202 dialogues
  - 101 with a tool-use policy
  - 33 (16 %) with "I can not answer" as the gold answer

## 5. Resource usage

- **Disk:** about 10 GB added in total (venv 1.6 GB, data 5.7 GB, image 2.75 GB). 26 GB free
  afterwards.
- **Groq:** roughly 60 agent requests and 20 judge requests today, well under 1,000/day. Exact
  token totals were not logged: upstream's runner records no usage. Token accounting is planned
  for our own runner in Phase 1.
- **Gemini:** about 10 generation requests.
