"""Offline V4 check: does retrieving tools again at each hop keep the gold tools at small k?

For each multi-hop (Cap 3) item of a split, compare three ways of choosing the k tools the agent
sees at hop i (1-based), using the gold chain:
  once     rank once by the query (V2 today); the same top k at every hop
  per-hop  hop 1 by the query; hop i > 1 by the query plus hop i-1's gold call and response
  fused    hop i > 1: reciprocal-rank fusion of the query ranking and the per-hop ranking
An item counts as kept at k if every hop's gold tool is inside that hop's top k. Using the gold
previous response makes per-hop an upper bound: a live agent's previous call can be wrong.

Rankings come from retrieval.py (the same code as V2); query_* tools are pinned first, as in
upstream. No LLM calls.

Usage:
    python scripts/hop_recall.py --split dev-eval [--retriever hybrid]
"""
import argparse
import asyncio
import json
import sys

from common import CAPABILITIES, TRAIN_DIR, load_split
from tool_recall import fetch_catalog

from agents.components.tool_shortlister import ToolShortlister  # noqa: E402 (path set by tool_recall)
from retrieval import BM25, RETRIEVERS, normalize, rankings, rrf  # noqa: E402

CAP_ID = 3
KS = (5, 10, 20, 32, 50)
MAX_RESPONSE_CHARS = 500  # of the previous response, appended to the query


def load_chains(cap_dir: str, uuids: set[str]) -> dict[str, list[dict]]:
    """{domain: [{uuid, query, calls, responses}]} from the gold output files."""
    by_domain = {}
    for f in sorted((TRAIN_DIR / cap_dir / "output").glob("*.json")):
        items = []
        for rec in json.loads(f.read_text()):
            if rec["uuid"] in uuids:
                seq = rec["output"][0]["sequence"]
                items.append({"uuid": rec["uuid"], "query": rec["output"][0]["query"],
                              "calls": seq["tool_call"], "responses": seq.get("tool_response", [])})
        if items:
            by_domain[f.stem] = items
    return by_domain


def hop_text(item: dict, hop: int) -> str:
    """Query plus the previous hop's gold call and response (hop is 0-based, > 0)."""
    call, resp = item["calls"][hop - 1], item["responses"][hop - 1] if hop - 1 < len(item["responses"]) else ""
    return (f"{item['query']} {call['name']} {json.dumps(call.get('arguments', {}))} "
            f"{json.dumps(resp, ensure_ascii=False)[:MAX_RESPONSE_CHARS]}")


def main_domain(catalog: list[dict], items: list[dict], model, retriever: str) -> list[dict]:
    """Per item: {mode: [rank of hop i's gold tool in hop i's ordering, ...]}."""
    names = [t["name"] for t in catalog]
    pinned = [n for n in names if n.startswith("query_")]
    cand = [t for t in catalog if not t["name"].startswith("query_")]
    texts = [ToolShortlister._tool_text(t) for t in cand]
    emb = normalize(model.encode(texts, convert_to_numpy=True))
    bm25 = BM25(texts)

    def order(text: str) -> list[int]:
        return rankings(text, emb, bm25, model)[retriever]

    def rank(o: list[int], tool: str) -> int | None:
        ranking = pinned + [cand[i]["name"] for i in o]
        return ranking.index(tool) + 1 if tool in ranking else None

    out = []
    for it in items:
        q = order(it["query"])
        modes = {"once": [], "per-hop": [], "fused": []}
        for hop, call in enumerate(it["calls"]):
            if hop == 0:
                for m in modes:
                    modes[m].append(rank(q, call["name"]))
                continue
            h = order(hop_text(it, hop))
            modes["once"].append(rank(q, call["name"]))
            modes["per-hop"].append(rank(h, call["name"]))
            modes["fused"].append(rank(rrf(q, h), call["name"]))
        out.append({"size": len(names), **modes})
    return out


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--split", default="dev-eval")
    ap.add_argument("--retriever", default="hybrid", choices=RETRIEVERS)
    args = ap.parse_args()

    cap_dir, _ = CAPABILITIES[CAP_ID]
    model = ToolShortlister(top_k=max(KS)).model
    rows = []
    for domain, items in load_chains(cap_dir, set(load_split(args.split).get(cap_dir, []))).items():
        rows += main_domain(await fetch_catalog(CAP_ID, domain), items, model, args.retriever)

    n = len(rows)
    print(f"split: {args.split}, {cap_dir}, retriever: {args.retriever}, {n} items")
    print("| mode | " + " | ".join(f"R@{k}" for k in KS) + " |\n|---|" + "---:|" * len(KS))
    for mode in ("once", "per-hop", "fused"):
        # A catalog of <= k tools is passed through whole by upstream, so every gold tool is kept.
        hits = [sum(all(r is not None and (r <= k or row["size"] <= k) for r in row[mode]) for row in rows)
                for k in KS]
        print(f"| {mode} | " + " | ".join(f"{h / n:.3f}" for h in hits) + " |")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
