"""Offline V5 test: rewrite stored final answers from tool evidence only, then score officially.

Takes the items of scored runs that lost their point only on groundedness (ungrounded_items.py)
and a control sample of correct items (the same number per capability, fixed seed). For each one
it replays the agent's tool calls on the local MCP containers, the same way the evaluator does
(free), and asks the agent model to rewrite the final answer from that evidence (V5_PROMPT in
answer_rewrite.py, the prompt --evidence-answer uses at run time). It
writes two runs with the same items and gold data:

    runs/<id>-orig   answers unchanged (re-scoring them measures judge noise)
    runs/<id>-v5     answers rewritten

Score both with `python scripts/evaluate.py --run-id <id>-orig` (and `-v5`).
--dry-run replays the tools and prints the size of the rewrite prompts, without LLM calls.

Usage:
    python scripts/v5_answer_test.py --run-ids RUN [RUN ...] [--dry-run]
"""
import argparse
import asyncio
import json
import os
import random
import sys
import time
from collections import defaultdict

from answer_rewrite import V5_PROMPT, evidence_prompt
from common import CAPABILITIES, GROQ_OPENAI_BASE_URL, RUNS_DIR, UPSTREAM, load_dotenv
from ungrounded_items import ungrounded

MODEL = "openai/gpt-oss-120b"


def load_preds(run_id: str, cap_dir: str) -> dict:
    preds = {}
    for f in (RUNS_DIR / run_id / "output" / cap_dir).glob("*.json"):
        if not f.stem.endswith("_tools"):
            preds.update({r["uuid"]: r for r in json.loads(f.read_text())})
    return preds


def select(run_ids: list[str], seed: int) -> list[dict]:
    """[{run, cap, domain, uuid, group}] for the ungrounded items plus a matched control sample."""
    rng = random.Random(seed)
    picked = []
    for run_id in run_ids:
        bad = ungrounded(run_id)
        picked += [{"run": run_id, "cap": it["cap"], "domain": it["domain"], "uuid": it["uuid"],
                    "group": "ungrounded"} for it in bad]
        for cap_dir, _ in CAPABILITIES.values():
            eval_file = RUNS_DIR / run_id / "eval" / f"{cap_dir}.json"
            n = sum(it["cap"] == cap_dir for it in bad)
            if not n or not eval_file.exists():
                continue
            preds = load_preds(run_id, cap_dir)
            correct = [(dom, d["uuid"]) for dom, v in json.loads(eval_file.read_text())["domains"].items()
                       for d in v["dialogues"]
                       if d["score"] == 1.0 and preds.get(d["uuid"], {}).get("status") != "error"]
            picked += [{"run": run_id, "cap": cap_dir, "domain": dom, "uuid": u, "group": "control"}
                       for dom, u in rng.sample(sorted(correct), min(n, len(correct)))]
    return picked


async def replay(items: list[dict]) -> None:
    """Add item["evidence"]: [(tool call, response text)] for the final turn, as the evaluator replays it."""
    os.chdir(UPSTREAM)
    sys.path[:0] = [str(UPSTREAM), str(UPSTREAM / "evaluator")]
    from benchmark.mcp_client import create_client_and_connect, load_mcp_config
    from constant import N_TOOL_CALLS_PER_TURN
    from mcp_tools import execute_tools_batch, extract_toolcalls_for_mcp

    configs = load_mcp_config("benchmark/mcp_connection_config.yaml")
    cap_ids = {cap_dir: cap_id for cap_id, (cap_dir, _) in CAPABILITIES.items()}
    by_domain = defaultdict(list)
    for it in items:
        by_domain[(it["cap"], it["domain"])].append(it)
    for (cap_dir, domain), its in by_domain.items():
        async with create_client_and_connect(configs[cap_ids[cap_dir]], domain) as session:
            schema_map = {t.name: t.inputSchema for t in (await session.list_tools()).tools}
            batch = [extract_toolcalls_for_mcp(it["pred"], limit_last_n=N_TOOL_CALLS_PER_TURN) for it in its]
            if cap_dir == "capability_1_bi_apis":
                # As evaluator.py's _prepend_get_data_to_batch: load the item's universe first.
                for calls, it in zip(batch, its):
                    calls[:1] = [[{"name": "get_data", "arguments": {"tool_universe_id": it["uuid"]}},
                                  *(calls[0] if calls else [])]]
            responses = await execute_tools_batch(session, batch, schema_map)
        for it, calls, resps in zip(its, batch, responses):
            it["evidence"] = list(zip(calls[-1], resps[-1])) if calls else []


def rewrite_prompt(it: dict) -> str:
    turn = it["pred"]["output"][-1]
    calls = [(call["name"], call["arguments"], resp) for call, resp in it["evidence"]]
    return evidence_prompt(turn["query"], calls, turn["answer"])


def rewrite(items: list[dict]) -> dict:
    from openai import OpenAI
    env = load_dotenv()
    client = OpenAI(api_key=os.environ.get("API_KEY") or env["API_KEY"], base_url=GROQ_OPENAI_BASE_URL,
                    max_retries=8)
    usage = defaultdict(int)
    for n, it in enumerate(items, 1):
        resp = client.chat.completions.create(
            model=MODEL, temperature=0,
            messages=[{"role": "system", "content": V5_PROMPT}, {"role": "user", "content": rewrite_prompt(it)}])
        it["v5_answer"] = (resp.choices[0].message.content or "").strip() or it["pred"]["output"][-1]["answer"]
        usage["prompt_tokens"] += resp.usage.prompt_tokens
        usage["completion_tokens"] += resp.usage.completion_tokens
        print(f"  rewrote {n}/{len(items)} ({it['group']}, {it['cap'][:12]})", flush=True)
    return dict(usage)


def write_run(run_id: str, items: list[dict], answer_key: str | None, meta: dict) -> None:
    run = RUNS_DIR / run_id
    gold, preds = defaultdict(list), defaultdict(list)
    for it in items:
        key = (it["cap"], it["domain"])
        src_gold = RUNS_DIR / it["run"] / "data" / it["cap"] / "output" / f"{it['domain']}.json"
        gold[key] += [g for g in json.loads(src_gold.read_text()) if g["uuid"] == it["uuid"]]
        pred = json.loads(json.dumps(it["pred"]))
        if answer_key:
            pred["output"][-1]["answer"] = it[answer_key]
        preds[key].append(pred)
    for (cap_dir, domain), gs in gold.items():
        for sub, rows in (("data/" + cap_dir + "/output", gs), ("output/" + cap_dir, preds[(cap_dir, domain)])):
            (run / sub).mkdir(parents=True, exist_ok=True)
            (run / sub / f"{domain}.json").write_text(json.dumps(rows, indent=1, ensure_ascii=False))
    (run / "config.json").write_text(json.dumps(meta, indent=1) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-ids", nargs="+", required=True)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    items = select(args.run_ids, args.seed)
    for it in items:
        it["pred"] = load_preds(it["run"], it["cap"])[it["uuid"]]
    asyncio.run(replay(items))
    chars = [len(V5_PROMPT) + len(rewrite_prompt(it)) for it in items]
    groups = {g: sum(it["group"] == g for it in items) for g in ("ungrounded", "control")}
    print(f"{len(items)} items {groups}; rewrite prompts: {sum(chars)} chars "
          f"(~{sum(chars) // 4} tokens), largest {max(chars)}")
    if args.dry_run:
        return 0

    usage = rewrite(items)
    test_id = time.strftime("%Y%m%d-%H%M") + "-v5test"
    meta = {"source_runs": args.run_ids, "seed": args.seed, "model": MODEL, "v5_prompt": V5_PROMPT,
            "rewrite_usage": usage,
            "items": [{k: it[k] for k in ("run", "cap", "domain", "uuid", "group")} for it in items]}
    write_run(f"{test_id}-orig", items, None, meta)
    write_run(f"{test_id}-v5", items, "v5_answer", meta)
    print(f"wrote runs/{test_id}-orig and runs/{test_id}-v5; rewrite usage {usage}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
