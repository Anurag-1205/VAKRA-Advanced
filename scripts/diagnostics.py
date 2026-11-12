"""Per-item diagnostics for any scored run: what went wrong in each trajectory (#11).

Reads only what upstream writes, for every capability in the run:
  runs/<run>/output/<cap>/<domain>.json   agent status and error, tool calls, final answer
  runs/<run>/output/<cap>/run.log         trajectories with tool results (no uuids: items are
                                          matched by domain and position, checked by query text)
  runs/<run>/eval/<cap>.json              score and judge verdicts per item
  runs/<run>/data/<cap>/{input,output}    gold tool calls (final turn) and Cap 4 policies

Flags per item (an item can have several):
  agent error              the agent crashed (status error); see failure_breakdown.py for kinds
  no tool call             answered without calling any tool (gold calls at least one)
  gold tool never called   some gold tool name is not among the agent's calls
  gold tools, other args   every gold tool was called, but some never with the gold arguments
  more calls than gold     more tool calls than the gold sequence
  repeated identical call  the same tool with the same arguments twice or more
  tool error result        a tool result reports an error (from run.log)
  empty tool result        a tool result is empty ([], {}, null)
  says not available       the answer says it cannot answer or the data is not available
  asks the user back       the answer asks the user a question (clarification) instead of answering
  policy: retriever used   Cap 4, the policy forbids document retrievers (query_*) and one was called
  policy: data tool used   Cap 4, the policy allows only retrievers and another tool was called

Gold tool calls exclude Cap 1's setup step (initialize_active_data, which the runner does through
get_data). Cap 1 also has many equivalent tool paths, so its gold-tool flags are a weak signal:
compare the failed and correct columns.

Usage:
    python scripts/diagnostics.py --run-id <run> [--jsonl items.jsonl] [--show 5]
"""
import argparse
import json
import random
import re
import sys
from collections import Counter

from common import CAPABILITIES, RUNS_DIR
from failure_breakdown import outcome
from policy_guard import RETRIEVER_PREFIX, parse_policy

FLAGS = ("agent error", "no tool call", "gold tool never called", "gold tools, other args",
         "more calls than gold", "repeated identical call", "tool error result", "empty tool result",
         "says not available", "asks the user back", "policy: retriever used", "policy: data tool used")

_TS = re.compile(r"^\[\d\d:\d\d:\d\d\.\d{3}\] ?", re.M)
_DEBUG = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d,\d+ |\{\"ts\": )")
_ERROR_RESULT = re.compile(r"\"error\"|validation error|Unknown tool|Traceback|Exception|not found|Invalid|"
                           r"status_code\"?: ?[45]\d\d", re.I)
_NOT_AVAILABLE = re.compile(r"not available|can ?not answer|unable to|i'm sorry|i am sorry|no data|"
                            r"don't have|do not have|cannot (find|determine|provide)", re.I)
_ASKS_BACK = re.compile(r"could you|can you (provide|clarify|confirm)|would you like|do you want|"
                        r"please (provide|clarify|specify|confirm|let me know)|let me know", re.I)
SETUP_CALLS = {"initialize_active_data"}  # Cap 1 gold only; the runner's get_data does it


def parse_log(path) -> dict[tuple[str, int], dict]:
    """{(domain, position): {"query", "results": [(tool, text)], "entries": [text]}} from run.log."""
    if not path.exists():
        return {}
    lines = [ln for ln in path.read_text(errors="replace").splitlines() if not _DEBUG.match(ln)]
    items, domain, cur = {}, None, None
    for entry in _TS.split("\n".join(lines)):
        text = entry.strip()
        if m := re.match(r"# DOMAIN: (\S+) \(", text):
            domain, cur = m.group(1), None
        elif m := re.match(r"\[(\d+)/\d+\] Query: (.*)", text):
            cur = items[(domain, int(m.group(1)))] = {"query": m.group(2), "results": [], "entries": []}
        elif cur is not None:
            cur["entries"].append(text)
            if text.startswith("[TOOL RESULT]"):
                head, _, body = text.partition("\n")
                cur["results"].append((head.removeprefix("[TOOL RESULT]").strip(), body.strip()))
    return items


def _args(a) -> str:
    return json.dumps({k: str(v).strip().lower() for k, v in (a or {}).items()}, sort_keys=True)


def _same_query(log_query: str, query: str) -> bool:
    a, b = " ".join(log_query.removesuffix("...").split()), " ".join(query.split())
    return b.startswith(a[:60])


def diagnose(pred: dict, gold_calls: list[dict], results: list[tuple[str, str]], policy: str | None) -> list[str]:
    turn = pred["output"][-1] if pred.get("output") else {}
    calls = turn.get("sequence", {}).get("tool_call", [])
    names = [c["name"] for c in calls]
    flags = []
    if pred.get("status") == "error":
        flags.append("agent error")
    if gold_calls and not calls:
        flags.append("no tool call")
    gold_names = {c["name"] for c in gold_calls}
    if calls and gold_names - set(names):
        flags.append("gold tool never called")
    elif calls and gold_calls:
        made = {(c["name"], _args(c.get("arguments"))) for c in calls}
        if any((g["name"], _args(g.get("arguments"))) not in made for g in gold_calls):
            flags.append("gold tools, other args")
    if gold_calls and len(calls) > len(gold_calls):
        flags.append("more calls than gold")
    if max(Counter((c["name"], _args(c.get("arguments"))) for c in calls).values(), default=0) > 1:
        flags.append("repeated identical call")
    if any(_ERROR_RESULT.search(text) for _, text in results):
        flags.append("tool error result")
    if any(text.strip() in ("[]", "{}", "null", '""', "") for _, text in results):
        flags.append("empty tool result")
    if _NOT_AVAILABLE.search(turn.get("answer") or ""):
        flags.append("says not available")
    if _ASKS_BACK.search(turn.get("answer") or ""):
        flags.append("asks the user back")
    mode, _, _ = parse_policy(policy)
    if mode == "no" and any(n.startswith(RETRIEVER_PREFIX) for n in names):
        flags.append("policy: retriever used")
    if mode == "only" and any(not n.startswith(RETRIEVER_PREFIX) for n in names):
        flags.append("policy: data tool used")
    return flags


def load_cap(run, cap_dir: str) -> list[dict]:
    eval_file = run / "eval" / f"{cap_dir}.json"
    if not eval_file.exists():
        return []
    scored = {}
    for dom in json.loads(eval_file.read_text())["domains"].values():
        for d in dom["dialogues"]:
            scored[d["uuid"]] = d
    log = parse_log(run / "output" / cap_dir / "run.log")
    rows = []
    for f in sorted((run / "output" / cap_dir).glob("*.json")):
        if f.stem.endswith("_tools"):
            continue
        gold_file, input_file = (run / "data" / cap_dir / sub / f.name for sub in ("output", "input"))
        gold = {g["uuid"]: g for g in json.loads(gold_file.read_text())} if gold_file.exists() else {}
        inputs = {i["uuid"]: i for i in json.loads(input_file.read_text())} if input_file.exists() else {}
        for pos, pred in enumerate(json.loads(f.read_text()), 1):
            d = scored.get(pred["uuid"])
            if d is None:
                continue
            turn = pred["output"][-1] if pred.get("output") else {}
            entry = log.get((f.stem, pos))
            if entry and not _same_query(entry["query"], turn.get("query", "")):
                entry = None  # log and output out of step (e.g. a resumed run): no tool results
            g = gold.get(pred["uuid"], {}).get("output") or [{}]
            gold_calls = [c for c in g[-1].get("sequence", {}).get("tool_call", []) if c["name"] not in SETUP_CALLS]
            policy = inputs.get(pred["uuid"], {}).get("additional_instructions")
            meta = d["details"]["per_turn"][0]["metadata"]
            rows.append({
                "cap": cap_dir, "domain": f.stem, "uuid": pred["uuid"], "query": turn.get("query", ""),
                "score": d["score"], "outcome": outcome(d["score"], pred, meta),
                "n_calls": len(turn.get("sequence", {}).get("tool_call", [])), "n_gold_calls": len(gold_calls),
                "flags": diagnose(pred, gold_calls, entry["results"] if entry else [], policy),
                "calls": [{"name": c["name"], "arguments": c.get("arguments")}
                          for c in turn.get("sequence", {}).get("tool_call", [])],
                "gold_calls": gold_calls, "gold_answer": str(g[-1].get("answer"))[:500],
                "answer": (turn.get("answer") or "")[:500], "error": (pred.get("error") or "")[:200],
                "judge": meta.get("score_explanation"), "log": entry["entries"] if entry else None,
            })
    return rows


def show(row: dict, max_chars: int = 400) -> None:
    print(f"\n--- {row['cap']} / {row['domain']} / {row['uuid']}  score {row['score']}  [{row['outcome']}]")
    print(f"flags: {', '.join(row['flags']) or '-'}")
    print(f"query: {row['query']}")
    for e in row["log"] or []:
        if e.startswith(("[TOOL CALL]", "[TOOL RESULT]", "[FINAL ANSWER]", "Status:")):
            print("  " + (e if len(e) <= max_chars else e[:max_chars] + " ...").replace("\n", "\n  "))
    print(f"judge: {json.dumps(row['judge'], ensure_ascii=False)[:max_chars]}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--jsonl", default=None, help="write one line per item (without the log) here")
    ap.add_argument("--show", type=int, default=0, help="print this many failed trajectories per capability")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    run = RUNS_DIR / args.run_id

    all_rows = []
    for cap_dir, _ in CAPABILITIES.values():
        rows = load_cap(run, cap_dir)
        if not rows:
            continue
        all_rows += rows
        failed, correct = [r for r in rows if r["score"] < 1], [r for r in rows if r["score"] == 1]
        matched = sum(r["log"] is not None for r in rows)
        print(f"\n{cap_dir}: {len(rows)} items, {len(failed)} failed; run.log matched for {matched}")
        print(f"| flag | failed (n = {len(failed)}) | correct (n = {len(correct)}) |\n|---|---:|---:|")
        for flag in FLAGS:
            nf, nc = (sum(flag in r["flags"] for r in rs) for rs in (failed, correct))
            if nf or nc:
                print(f"| {flag} | {nf} | {nc} |")
        print(f"| no flag | {sum(not r['flags'] for r in failed)} | {sum(not r['flags'] for r in correct)} |")
        for row in random.Random(args.seed).sample(failed, min(args.show, len(failed))):
            show(row)

    if args.jsonl:
        with open(args.jsonl, "w") as fh:
            for r in all_rows:
                fh.write(json.dumps({k: v for k, v in r.items() if k != "log"}, ensure_ascii=False) + "\n")
        print(f"\n{len(all_rows)} items -> {args.jsonl}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
