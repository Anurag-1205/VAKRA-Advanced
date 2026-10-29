# Baseline on dev-eval (2026-10-29)

Upstream's unmodified `LangGraphReActAgent` on `dev-eval`, Caps 2 and 3, scored by
upstream's evaluator.

- **Model:** `openai/gpt-oss-120b` on Groq's Developer (paid) tier, temperature 0.
- **Judge:** Groq `gpt-oss-120b`.
- **Retries:** `--llm-max-retries 8`. This only affects retries of rate-limited calls; no 429s
  occurred on the paid tier.
- **Machine:** Aayush's machine. See [phase0.md](phase0.md) §4a for setup.
- **Reproduce:**
  `python scripts/run_baseline.py --split dev-eval --caps 2 3 --top-k-tools {128|32} --llm-max-retries 8`,
  then `python scripts/evaluate.py --run-id <id>` and
  `python scripts/failure_breakdown.py --run-id <id>`.

## Scores

| Variant | Run id | Cap 2 (n = 120) | Cap 3 (n = 35) | Macro avg |
|---|---|---:|---:|---:|
| **V0**: top-k 128 (upstream default) | `20261029-1738-v0-groq-dev-eval` | **49/120 = 0.408** | **12/35 = 0.343** | **0.376** |
| V0-k32: top-k 32 | `20261029-1802-v0k32-groq-dev-eval` | 51/120 = 0.425 | 6/35 = 0.171 | 0.298 |

The samples are small. The 95% half-width is about ±0.09 for Cap 2 and ±0.16 for Cap 3.

- **Cap 2:** the two variants are within noise (a 2-item difference).
- **Cap 3:** halving from 12 to 6 matches the retrieval measurement in
  [tool_recall.md](tool_recall.md). With 32 tools, all gold tools survive the shortlist for
  only 71% of Cap 3 items, against 94% with 128.

Wall time: V0 about 20 min for both caps, V0-k32 about 15 min.

## Where items are lost

`scripts/failure_breakdown.py`:

| Outcome | V0 Cap 2 | V0-k32 Cap 2 | V0 Cap 3 | V0-k32 Cap 3 |
|---|---:|---:|---:|---:|
| Correct: gold tool responses produced | 37.5% | 39.2% | 31.4% | 17.1% |
| Correct: answer judged right | 3.3% | 3.3% | 2.9% | — |
| Wrong or no answer | 25.8% | 30.0% | 40.0% | 42.9% |
| **Agent error: tool call missing a required argument (Groq HTTP 400)** | **22.5%** | **20.0%** | **17.1%** | **17.1%** |
| Right tool responses, answer not grounded | 10.0% | 6.7% | 2.9% | 11.4% |
| Right answer, not grounded | — | — | 5.7% | 11.4% |
| Agent error: context too long | 0.8% | 0.8% | — | — |

## Findings for the next variants

1. **About a fifth of all items die on Groq's server-side tool-call validation.** The model
   omits a required argument, and Groq returns HTTP 400 instead of the call. Upstream's agent
   treats this as fatal, so the item ends with no answer. Providers that return the malformed
   call would let the agent see a tool error and retry. Our own runner (V1) should catch this
   400 and re-prompt with the schema error. Schema validation and repair (V3) target the same
   items. This is the largest single source of loss and needs no retrieval change.
2. **Cap 3 is limited by the shortlist.** V0-k32 halves Cap 3. Hybrid retrieval at k = 32
   recovers part of the gap offline (R@32 0.800 vs 0.714). Per-step re-retrieval (V4) targets
   the hops the question doesn't name.
3. **Groundedness failures.** 7–23% of items reach the right tool responses or the right
   answer but are scored 0 for groundedness. An evidence-only answer synthesizer (V5) targets
   these.
