# Baseline on dev-eval (2026-10-29)

Upstream's unmodified `LangGraphReActAgent` on `dev-eval`, Caps 2, 3 and 4, scored by
upstream's evaluator.

- **Model:** `openai/gpt-oss-120b` on Groq's Developer (paid) tier, temperature 0.
- **Judge:** Groq `gpt-oss-120b`.
- **Retries:** `--llm-max-retries 8`. This only affects retries of rate-limited calls; no 429s
  occurred on the paid tier.
- **Machine:** Aayush's machine. See [phase0.md](phase0.md) §4a for setup.
- **Reproduce:**
  `python scripts/run_baseline.py --split dev-eval --caps 2 3 --top-k-tools {128|32} --llm-max-retries 8`
  (Cap 4: `--caps 4 --top-k-tools 128`),
  then `python scripts/evaluate.py --run-id <id>` and
  `python scripts/failure_breakdown.py --run-id <id>`.

## Scores

| Variant | Cap 2 (n = 120) | Cap 3 (n = 35) | Cap 4 (n = 60) | Macro avg, Caps 2–4 |
|---|---:|---:|---:|---:|
| **V0**: top-k 128 (upstream default) | **0.408** (49/120) | **0.343** (12/35) | **0.350** (21/60)* | **0.367** |
| V0-k32: top-k 32 | 0.425 (51/120) | 0.171 (6/35) | not run | – |

\* 0.300 without the 3 dialogues credited despite an agent crash (see below).

Run ids:

- V0, Caps 2–3: `20261029-1738-v0-groq-dev-eval`
- V0, Cap 4: `20261029-1925-v0-groq-dev-eval`
- V0-k32, Caps 2–3: `20261029-1802-v0k32-groq-dev-eval`

Cap 4 is scored on the **final turn** of each dialogue. Earlier turns are given to the agent as
history, together with their gold answers. Of the official 0.350, **3 of 60 dialogues are
credited although the agent crashed**. Their gold answer is "I can not answer", and upstream
grants full credit for "unanswerable and no tool call", which an agent that errors out before
calling any tool also satisfies. Without them, V0 scores **18/60 = 0.300** on Cap 4. V0 never
abstained deliberately: it got 0 of the 11 unanswerable final turns in `dev-eval` by abstaining.

The samples are small. The 95% half-width is about ±0.09 for Cap 2, ±0.16 for Cap 3 and ±0.12
for Cap 4.

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

### Cap 4 (V0, n = 60 dialogues)

| Outcome | Share |
|---|---:|
| Correct: gold tool responses produced | 28.3% |
| Correct: answer judged right | 1.7% |
| Credited, but the agent crashed (unanswerable gold, no tool call) | 5.0% |
| Wrong or no answer | 30.0% |
| **Agent error: context too long** | **16.7%** |
| Right tool responses, answer not grounded | 11.7% |
| Right answer, not grounded | 5.0% |
| Agent error: timed out (300 s) | 1.7% |

- **Context too long:** all 10 such dialogues are in `authors` and `menu`, whose histories hold
  1.9–9.7 million characters of earlier gold answers ([data_stats.md](data_stats.md)). No
  request can fit them, whatever the tool count. The timeout is another `authors` dialogue: its
  ~10 MB request takes more than 300 s to upload.
- **Memory:** the Cap 4 container peaked at 1.3 GB, against its 8 GB limit.
- **Missing argument:** the Groq HTTP 400 for a missing required argument hit 3 dialogues. All 3
  had an unanswerable gold, so they appear in the "credited, but crashed" row.

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
4. **Cap 4: truncate history, and abstain on purpose.**
   - Truncating long gold answers in the dialogue history would make 17% of `dev-eval`
     dialogues answerable at all.
   - 18% of final turns are unanswerable under the dialogue's tool-use policy. V0 abstained on
     none of them deliberately, so a policy guard (V6) has up to 11 dialogues to win.
   - Any diagnostic must separate genuine abstentions from crash credit, as
     `failure_breakdown.py` now does.
