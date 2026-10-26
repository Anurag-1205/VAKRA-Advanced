# Dev splits

Built from the public VAKRA **train** split by [`scripts/make_splits.py`](../scripts/make_splits.py)
(seed 2027). Each file maps `capability_dir → [uuid, …]`; [`manifest.json`](manifest.json) records
parameters, counts, domains per split and a fingerprint of the train data.

| Split | Definition | Cap 1 | Cap 2 | Cap 3 | Cap 4 |
|---|---|---:|---:|---:|---:|
| `smoke` | ≤ 6 dev-heldout items per capability, from 2 domains (`authors`, `cars`) | 6 | 6 | 4 | 6 |
| `dev-seen` | ~15 % of items of each non-held-out domain | 163 | 203 | 45 | 99 |
| `dev-heldout` | **all** items of 9 domains held out from every capability | 246 | 511 | 35 | 223 |
| `train-rest` | everything else (few-shot pool, index expansion) | 915 | 1,146 | 266 | 576 |

Held-out domains: `authors, cars, european_football_1, hockey, ice_hockey_draft, menu,
sales_in_weather, student_loan, world`.

- Domains are held out **globally**: Caps 2–4 share each domain's REST tool catalog, so a domain
  held out in one capability but seen in another would leak tool knowledge.
- The 8 domains with databases > 1 GB (`bike_share_1, codebase_comments, movie_platform,
  world_development_indicators, language_corpus, talkingdata, music_platform_2, coinmarketcap`)
  are excluded from the held-out draw so dev-heldout runs need only 1.37 GB of databases. They
  remain in dev-seen / train-rest.
- Rebuild: `cd scripts && python make_splits.py --heldout-exclude <those 8>`; verify with
  `python make_splits.py --check` (partition, smoke ⊂ dev-heldout, no domain leakage, train
  fingerprint).
