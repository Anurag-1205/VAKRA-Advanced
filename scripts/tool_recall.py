"""Offline tool-retrieval evaluation: does the gold tool survive the shortlist?

For each item of a split, rank the domain's tool catalog against the user query and
report, per capability, retriever and k:
  recall@k  share of items whose gold tools are ALL inside the top k
  MRR       mean reciprocal rank of the first gold tool (full ranking)

Retrievers, all over the same "name: description" text upstream embeds:
  minilm  upstream ToolShortlister's model and similarity (all-MiniLM-L6-v2, cosine): V0
  bm25    Okapi BM25 (k1=1.5, b=0.75)
  hybrid  reciprocal-rank fusion of minilm and bm25 (RRF constant 60)
Like upstream, tools named query_* are always kept and take the first slots.

Catalogs come from the running containers (MCP list_tools through upstream's
MCPToolWrapper, as the agent sees them) and are cached in generated/tool_catalogs/
(derived from VAKRA data; gitignored). No LLM calls, so no Groq quota.

Usage:
    python scripts/tool_recall.py --split dev-heldout --caps 2 3
    python scripts/tool_recall.py --split dev-eval --caps 2 3 --json out.json
"""
import argparse
import asyncio
import json
import math
import re
import sys
from collections import Counter

import numpy as np

from common import CAPABILITIES, REPO_ROOT, TRAIN_DIR, UPSTREAM, load_split

sys.path.insert(0, str(UPSTREAM))
from agents.components.tool_shortlister import ToolShortlister  # noqa: E402
from agents.mcp_tool_wrapper import MCPToolWrapper  # noqa: E402
from benchmark.mcp_client import create_client_and_connect, load_mcp_config  # noqa: E402

CATALOG_DIR = REPO_ROOT / "generated" / "tool_catalogs"
KS = (5, 10, 20, 32, 50, 128)  # 32: our V0-k32 baseline; 128: upstream's default
RRF_K = 60


async def fetch_catalog(cap_id: int, domain: str) -> list[dict]:
    path = CATALOG_DIR / f"cap{cap_id}" / f"{domain}.json"
    if path.exists():
        return json.loads(path.read_text())
    cfg = load_mcp_config(str(UPSTREAM / "benchmark" / "mcp_connection_config.yaml"))[cap_id]
    async with create_client_and_connect(cfg, domain) as session:
        tools = await MCPToolWrapper(session).get_tools()
    catalog = [{"name": t.name, "description": t.description or ""} for t in tools]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(catalog, indent=1))
    return catalog


def load_items(cap_dir: str, uuids: set[str]) -> dict[str, list[dict]]:
    """{domain: [{uuid, query, gold}]} for single-turn items; gold = tool names in call order.

    Only opens output files of domains with split items: some train output files are
    > 2 GB (movie_platform) and parsing one takes ~9 GB RAM.
    """
    by_domain = {}
    for in_file in sorted((TRAIN_DIR / cap_dir / "input").glob("*.json")):
        if not any(x["uuid"] in uuids for x in json.loads(in_file.read_text())):
            continue
        f = TRAIN_DIR / cap_dir / "output" / in_file.name
        items = []
        for rec in json.loads(f.read_text()):
            if rec["uuid"] not in uuids:
                continue
            turn = rec["output"][0]
            gold = list(dict.fromkeys(c["name"] for c in turn["sequence"]["tool_call"]))
            items.append({"uuid": rec["uuid"], "query": turn["query"], "gold": gold})
        if items:
            by_domain[f.stem] = items
    return by_domain


def tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


class BM25:
    def __init__(self, docs: list[str], k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.docs = [Counter(tokenize(d)) for d in docs]
        self.lens = np.array([sum(d.values()) for d in self.docs], dtype=float)
        self.avg = self.lens.mean() if len(self.docs) else 0.0
        df = Counter(t for d in self.docs for t in d)
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in df.items()}

    def scores(self, query: str) -> np.ndarray:
        out = np.zeros(len(self.docs))
        norm = self.k1 * (1 - self.b + self.b * self.lens / self.avg)
        for t in set(tokenize(query)):
            if t not in self.idf:
                continue
            tf = np.array([d.get(t, 0) for d in self.docs], dtype=float)
            out += self.idf[t] * tf * (self.k1 + 1) / (tf + norm)
        return out


def rank(scores: np.ndarray) -> np.ndarray:
    """Candidate indices, best first (stable, like np.argsort on ties)."""
    return np.argsort(-scores, kind="stable")


def evaluate_domain(catalog: list[dict], items: list[dict], shortlister: ToolShortlister) -> dict:
    """{retriever: [(gold_ranks, n_tools), ...]} with 1-based ranks in the final ordering."""
    names = [t["name"] for t in catalog]
    pinned = [n for n in names if n.startswith("query_")]
    cand = [t for t in catalog if not t["name"].startswith("query_")]
    texts = [ToolShortlister._tool_text(t) for t in cand]

    emb = shortlister.model.encode(texts, convert_to_numpy=True)
    emb = emb / np.where((n := np.linalg.norm(emb, axis=1, keepdims=True)) == 0, 1, n)
    bm25 = BM25(texts)

    out = {"minilm": [], "bm25": [], "hybrid": []}
    for it in items:
        q = shortlister.model.encode([it["query"]], convert_to_numpy=True)[0]
        q = q / (np.linalg.norm(q) or 1)
        order = {"minilm": rank(emb @ q), "bm25": rank(bm25.scores(it["query"]))}
        pos = {r: np.empty(len(cand), dtype=int) for r in order}
        for r, o in order.items():
            pos[r][o] = np.arange(len(cand))
        order["hybrid"] = rank(1 / (RRF_K + 1 + pos["minilm"]) + 1 / (RRF_K + 1 + pos["bm25"]))
        for r, o in order.items():
            ranking = pinned + [cand[i]["name"] for i in o]
            where = {name: i + 1 for i, name in enumerate(ranking)}
            out[r].append(([where.get(g) for g in it["gold"]], len(names)))
    return out


def summarize(rows: list[tuple[list, int]]) -> dict:
    n = len(rows)
    res = {"items": n, "missing_gold_in_catalog": sum(None in g for g, _ in rows)}
    for k in KS:
        # A catalog of <= k tools is passed through whole by upstream, so every gold tool is kept.
        hit = sum(all(r is not None and (r <= k or size <= k) for r in g) for g, size in rows)
        res[f"recall@{k}"] = round(hit / n, 3)
    res["mrr"] = round(sum(1 / min(r for r in g if r) for g, _ in rows if any(g)) / n, 3)
    return res


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--split", default="dev-heldout")
    ap.add_argument("--caps", type=int, nargs="+", default=[2, 3], choices=[2, 3])
    ap.add_argument("--json", help="write the summary here")
    args = ap.parse_args()

    shortlister = ToolShortlister(top_k=max(KS))
    split = load_split(args.split)
    summary = {}
    for cap_id in args.caps:
        cap_dir, _ = CAPABILITIES[cap_id]
        rows = {"minilm": [], "bm25": [], "hybrid": []}
        for domain, items in load_items(cap_dir, set(split.get(cap_dir, []))).items():
            catalog = await fetch_catalog(cap_id, domain)
            for r, rs in evaluate_domain(catalog, items, shortlister).items():
                rows[r] += rs
        summary[cap_dir] = {r: summarize(rs) for r, rs in rows.items()}

    cols = ["items", *(f"recall@{k}" for k in KS), "mrr"]
    print(f"split: {args.split}")
    for cap_dir, by_r in summary.items():
        print(f"\n{cap_dir}\n| retriever | " + " | ".join(cols) + " |\n|---|" + "---:|" * len(cols))
        for r, s in by_r.items():
            print(f"| {r} | " + " | ".join(str(s[c]) for c in cols) + " |")
        missing = by_r["minilm"]["missing_gold_in_catalog"]
        if missing:
            print(f"({missing} item(s) have a gold tool missing from the catalog)")
    if args.json:
        with open(args.json, "w") as fh:
            json.dump({"split": args.split, "ks": KS, "summary": summary}, fh, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
