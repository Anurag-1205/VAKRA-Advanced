# Tool retrieval: does the gold tool survive the shortlist? (2026-10-29)

Offline, no LLM calls: `python scripts/tool_recall.py --split <split> --caps 2 3`.

- **Text:** every retriever ranks the domain's tool catalog against the user query, using the
  same `name: description` text upstream embeds.
- **Pinned tools:** `query_*` tools take the first slots, as in upstream.
- **recall@k:** the share of items whose gold tools are **all** inside the top k.
- **MRR:** the mean reciprocal rank of the first gold tool.

Retrievers:

- **minilm:** upstream's `ToolShortlister` (all-MiniLM-L6-v2, cosine), i.e. what V0 / V0-k32
  sends to the LLM. Checked: our top-32 equals upstream's `shortlist()` on 45/45 sampled items.
- **bm25:** Okapi BM25, k1 = 1.5, b = 0.75.
- **hybrid:** reciprocal-rank fusion of minilm and bm25 (constant 60).

## dev-heldout (Cap 2: 511 items, Cap 3: 35)

| Cap | Retriever | R@5 | R@10 | R@20 | **R@32** | R@50 | R@128 | MRR |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 2 | minilm (V0) | 0.763 | 0.879 | 0.933 | **0.953** | 0.977 | 0.996 | 0.608 |
| 2 | bm25 | 0.659 | 0.779 | 0.871 | 0.928 | 0.957 | 0.992 | 0.486 |
| 2 | hybrid | 0.783 | 0.875 | 0.949 | **0.969** | 0.980 | 0.996 | 0.610 |
| 3 | minilm (V0) | 0.257 | 0.343 | 0.514 | **0.714** | 0.800 | 0.943 | 0.624 |
| 3 | bm25 | 0.200 | 0.371 | 0.543 | 0.714 | 0.971 | 1.000 | 0.540 |
| 3 | hybrid | 0.257 | 0.314 | 0.571 | **0.800** | 0.857 | 1.000 | 0.685 |

On `dev-eval` the Cap 2 sample (120 items) gives R@32 = 0.925 (minilm) and 0.958 (hybrid).
Cap 3 is the same 35 items as dev-heldout.

## Findings

1. **Cost of the 32-tool shortlist.** Going from upstream's 128 to 32 tools drops gold-tool
   recall by **4.3 points on Cap 2** (0.996 → 0.953) and **22.9 points on Cap 3**
   (0.943 → 0.714). V0-k32 therefore loses up to ~5% of Cap 2 and ~29% of Cap 3 items before
   the LLM acts. This bounds V0-k32's Cap 3 score at about 0.71.
2. **Hybrid beats upstream's retriever at the same k.** At k = 32 it reaches 0.969 vs 0.953 on
   Cap 2 and 0.800 vs 0.714 on Cap 3. BM25 alone is worse than MiniLM at small k, but the
   fusion helps. This supports V2 in the experiment matrix.
3. **Cap 3 is a multi-hop retrieval problem.** One query must surface every hop's tool, and
   later hops are often not named in the question. R@10 is only 0.31–0.37 for all three
   retrievers. Retrieving again at each step, using the previous tool output, is the obvious
   next experiment (V4).
4. **One unsolvable item.** In Cap 2 `world`, the gold tool of item `486ea46224d1-cdd0b84e2de8`
   (`get_countries_with_cities_in_population_range_and_low_life_expectancy`) is not in the
   domain's tool catalog, so no agent can solve it.
