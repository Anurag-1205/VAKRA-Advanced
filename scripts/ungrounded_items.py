"""List the items that lost their point only on groundedness: query, answer, tool calls, verdicts.

These are the items failure_breakdown.py counts as "right answer, not grounded" or "right tool
responses, answer not grounded". Upstream's groundedness judge sees the query and the replayed
tool responses (last 20 calls), but not the tool calls' arguments.

Usage:
    python scripts/ungrounded_items.py --run-id 20261109-2356-v2hybridfixrt-groq-dev-eval [--json out.json]
"""
import argparse
import json
import sys

from common import CAPABILITIES, RUNS_DIR


def ungrounded(run_id: str) -> list[dict]:
    run = RUNS_DIR / run_id
    items = []
    for cap_dir, _ in CAPABILITIES.values():
        eval_file = run / "eval" / f"{cap_dir}.json"
        if not eval_file.exists():
            continue
        preds = {}
        for f in (run / "output" / cap_dir).glob("*.json"):
            if not f.stem.endswith("_tools"):
                preds.update({r["uuid"]: r for r in json.loads(f.read_text())})
        for domain, dom in json.loads(eval_file.read_text())["domains"].items():
            for d in dom["dialogues"]:
                pred = preds.get(d["uuid"], {})
                if d["score"] == 1.0 or pred.get("status") == "error":
                    continue
                # Cap 4 is scored on its final turn only; Caps 1-3 have one turn.
                turn = d["details"]["per_turn"][-1]
                meta = turn["metadata"]
                if meta.get("exactmatch_score") != 1.0 and meta.get("answer_score") != 1.0:
                    continue
                calls = pred["output"][-1]["sequence"]["tool_call"] if pred.get("output") else []
                items.append({
                    "cap": cap_dir, "domain": domain, "uuid": d["uuid"], "query": turn["query"],
                    "answer": turn["pred_answer"], "tool_calls": calls,
                    "groundedness": (meta.get("score_explanation") or {}).get("groundedness"),
                })
    return items


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--json", help="write the items here")
    args = ap.parse_args()

    items = ungrounded(args.run_id)
    for it in items:
        print(f"\n=== {it['cap']} {it['domain']} {it['uuid']} ({len(it['tool_calls'])} tool calls, "
              f"{len(it['answer'])} chars)")
        print("Q:", it["query"][:300])
        print("A:", it["answer"][:400].replace("\n", " | "))
        print("Judge:", (it["groundedness"] or "")[:400].replace("\n", " "))
    print(f"\n{len(items)} item(s)")
    if args.json:
        with open(args.json, "w") as fh:
            json.dump(items, fh, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
