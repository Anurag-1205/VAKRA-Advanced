"""Build deterministic dev splits from the public VAKRA train split.

Splits (SPEC.md §7.1), all as uuid lists per capability:
  dev-heldout  every item of a held-out set of DOMAINS. Domains are held out
               globally (unseen in every capability), because Caps 2-4 share a
               domain's REST tool catalog and few-shot/index leakage across
               capabilities would otherwise make "unseen domain" untrue.
  dev-seen     ~15% of items of each remaining domain, per capability.
  train-rest   everything else (few-shot pool, index expansion, error mining).
  smoke        a few dev-heldout items per capability from <= 2 domains.

Usage:
    python scripts/make_splits.py                       # writes splits/*.json
    python scripts/make_splits.py --heldout-exclude bike_share_1 ...
    python scripts/make_splits.py --check               # verify committed splits
"""
import argparse
import hashlib
import json
import math
import random
import sys
from collections import defaultdict

from common import CAPABILITIES, SPLIT_NAMES, SPLITS_DIR, TRAIN_DIR


def load_train() -> dict[str, dict[str, list[str]]]:
    """{capability_dir: {domain: [uuid, ...]}} from train input files."""
    data = {}
    for cap_dir, _ in CAPABILITIES.values():
        files = sorted((TRAIN_DIR / cap_dir / "input").glob("*.json"))
        if not files:
            raise SystemExit(f"No train inputs under {TRAIN_DIR / cap_dir}; run scripts/download_data.py --train")
        data[cap_dir] = {f.stem: [x["uuid"] for x in json.loads(f.read_text())] for f in files}
    return data


def fingerprint() -> str:
    h = hashlib.sha256()
    for f in sorted(TRAIN_DIR.glob("*/*/*.json")):
        h.update(str(f.relative_to(TRAIN_DIR)).encode())
        # Stream: some output files are > 2 GB and would not fit in RAM on 7 GB machines.
        with f.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
    return h.hexdigest()[:16]


def pick_heldout(data, frac: float, rng: random.Random, exclude: set[str]) -> set[str]:
    """Greedy over shuffled domains until every capability reaches its quota."""
    quota = {cap: math.ceil(frac * len(doms)) for cap, doms in data.items()}
    count = defaultdict(int)
    candidates = sorted({d for doms in data.values() for d in doms} - exclude)
    rng.shuffle(candidates)
    heldout = set()
    for dom in candidates:
        caps = [c for c in data if dom in data[c]]
        if any(count[c] < quota[c] for c in caps):
            heldout.add(dom)
            for c in caps:
                count[c] += 1
        if all(count[c] >= quota[c] for c in data):
            break
    return heldout


def build(args) -> tuple[dict, dict]:
    data = load_train()
    rng = random.Random(args.seed)
    heldout = pick_heldout(data, args.heldout_frac, rng, set(args.heldout_exclude))

    splits = {name: {} for name in SPLIT_NAMES}
    for cap_dir, doms in data.items():
        dev_heldout, dev_seen, rest = [], [], []
        for dom in sorted(doms):
            uuids = sorted(doms[dom])
            if dom in heldout:
                dev_heldout += uuids
                continue
            rng.shuffle(uuids)
            k = round(args.seen_frac * len(uuids)) if len(uuids) >= 3 else 0
            dev_seen += uuids[:k]
            rest += uuids[k:]

        # Smoke: a few held-out items from at most 2 domains (keeps DB downloads small).
        smoke_doms = sorted(d for d in doms if d in heldout)[:2]
        smoke = []
        for dom in smoke_doms:
            uuids = sorted(doms[dom])
            rng.shuffle(uuids)
            smoke += uuids[: math.ceil(args.smoke_per_cap / len(smoke_doms))]

        for name, uuids in zip(SPLIT_NAMES, (smoke[: args.smoke_per_cap], dev_seen, dev_heldout, rest)):
            splits[name][cap_dir] = sorted(uuids)

    uuid_domain = {u: d for cap in data.values() for d, us in cap.items() for u in us}
    manifest = {
        "seed": args.seed,
        "heldout_frac": args.heldout_frac,
        "seen_frac": args.seen_frac,
        "smoke_per_cap": args.smoke_per_cap,
        "heldout_exclude": sorted(args.heldout_exclude),
        "train_fingerprint": fingerprint(),
        "heldout_domains": sorted(heldout),
        "counts": {
            name: {cap: len(u) for cap, u in s.items()} for name, s in splits.items()
        },
        "domains": {
            name: {cap: sorted({uuid_domain[u] for u in us}) for cap, us in s.items()}
            for name, s in splits.items()
        },
    }
    return splits, manifest


def validate(splits: dict, data: dict) -> list[str]:
    """Return a list of problems (empty == valid)."""
    problems = []
    for cap_dir, doms in data.items():
        every = {u for us in doms.values() for u in us}
        parts = [set(splits[n][cap_dir]) for n in ("dev-seen", "dev-heldout", "train-rest")]
        if sum(map(len, parts)) != len(every) or set().union(*parts) != every:
            problems.append(f"{cap_dir}: dev-seen/dev-heldout/train-rest do not partition the train split")
        if not set(splits["smoke"][cap_dir]) <= parts[1]:
            problems.append(f"{cap_dir}: smoke is not a subset of dev-heldout")
        dom_of = {u: d for d, us in doms.items() for u in us}
        held = {dom_of[u] for u in parts[1]}
        seen = {dom_of[u] for u in parts[0] | parts[2]}
        if held & seen:
            problems.append(f"{cap_dir}: held-out domains leak into seen splits: {sorted(held & seen)}")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=2027)
    ap.add_argument("--heldout-frac", type=float, default=0.2)
    ap.add_argument("--seen-frac", type=float, default=0.15)
    ap.add_argument("--smoke-per-cap", type=int, default=6)
    ap.add_argument("--heldout-exclude", nargs="*", default=[],
                    help="Domains never chosen as held-out (e.g. very large databases)")
    ap.add_argument("--check", action="store_true", help="Validate committed splits; write nothing")
    args = ap.parse_args()

    data = load_train()
    if args.check:
        splits = {n: json.loads((SPLITS_DIR / f"{n}.json").read_text()) for n in SPLIT_NAMES}
        manifest = json.loads((SPLITS_DIR / "manifest.json").read_text())
        problems = validate(splits, data)
        if manifest["train_fingerprint"] != fingerprint():
            problems.append("train data changed since splits were built (fingerprint mismatch)")
        print("\n".join(problems) or "splits OK")
        return 1 if problems else 0

    splits, manifest = build(args)
    problems = validate(splits, data)
    if problems:
        print("\n".join(problems))
        return 1
    SPLITS_DIR.mkdir(exist_ok=True)
    for name, s in splits.items():
        (SPLITS_DIR / f"{name}.json").write_text(json.dumps(s, indent=1) + "\n")
    (SPLITS_DIR / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n")
    print(json.dumps(manifest["counts"], indent=1))
    print("held-out domains:", manifest["heldout_domains"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
