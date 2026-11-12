"""Error analysis (#13): one primary category per failed item, and a sample to annotate by hand.

Built on diagnostics.py (same inputs: IBM's output files, run.log, eval and gold). The first split
is the evaluator's own exact-match verdict: were all the gold tool responses among the agent's?

  agent crash                              the item ended with an agent error
  right answer, not grounded               the correctness judge passed, the groundedness judge did not
  right tool results, answer not grounded  every gold tool response present; groundedness failed
  right tool results, wrong answer         every gold tool response present; correctness failed
  tool results missing, because:
    no tool call                           the agent answered without calling a tool
    different tool                         some gold tool was never called (Cap 1: often an
                                           equivalent path, so a weak signal there)
    argument differs only in case/spaces   a gold tool was called with the gold arguments up to
                                           case and surrounding spaces (the data is case-sensitive)
    other argument value                   every gold tool called, some never with the gold arguments
    gold calls made, results still missing every gold call was made exactly; the responses differ

Usage:
    python scripts/error_analysis.py --run-id <final run> [--sample 20] [--out sample.md]
    python scripts/error_analysis.py --cap-run 1=<run> --cap-run 2=<run> ... [--sample 20 --out F]
The sample is drawn per capability, proportional to the categories (at least one each), with a
fixed seed. It holds benchmark items, so write it under runs/ (gitignored), not into the repo.
"""
import argparse
import json
import random
import sys
from collections import Counter

from common import CAPABILITIES, RUNS_DIR
from diagnostics import load_cap

CATEGORIES = ("agent crash", "right answer, not grounded", "right tool results, answer not grounded",
              "right tool results, wrong answer", "tool results missing: no tool call",
              "tool results missing: different tool", "tool results missing: argument differs only in case/spaces",
              "tool results missing: other argument value", "tool results missing: gold calls made, results differ")
MAX_TRACE_CHARS = 300


def _args(arguments, fold: bool) -> str:
    norm = (lambda v: str(v).strip().lower()) if fold else str
    return json.dumps({k: norm(v) for k, v in (arguments or {}).items()}, sort_keys=True)


def category(row: dict) -> str:
    judge = row["judge"] if isinstance(row["judge"], dict) else {}
    tools_complete = str(judge.get("exactmatch") or "").startswith("All expected tool_responses are present")
    if "agent error" in row["flags"] or row["outcome"].startswith("agent error"):
        return "agent crash"
    if row["outcome"] == "right answer, not grounded":
        return "right answer, not grounded"
    if tools_complete:
        return ("right tool results, answer not grounded" if "not grounded" in row["outcome"]
                else "right tool results, wrong answer")
    if not row["calls"]:
        return "tool results missing: no tool call"
    made = {c["name"] for c in row["calls"]}
    if any(g["name"] not in made for g in row["gold_calls"]):
        return "tool results missing: different tool"
    exact = {(c["name"], _args(c["arguments"], False)) for c in row["calls"]}
    folded = {(c["name"], _args(c["arguments"], True)) for c in row["calls"]}
    gold_exact = [(g["name"], _args(g.get("arguments"), False)) for g in row["gold_calls"]]
    gold_folded = [(g["name"], _args(g.get("arguments"), True)) for g in row["gold_calls"]]
    if any(e not in exact and f in folded for e, f in zip(gold_exact, gold_folded)):
        return "tool results missing: argument differs only in case/spaces"
    if any(e not in exact for e in gold_exact):
        return "tool results missing: other argument value"
    return "tool results missing: gold calls made, results differ"


def sample(rows: list[dict], n: int, seed: int) -> list[dict]:
    """n rows, proportional to their categories, at least one per category."""
    groups = {}
    for r in rows:
        groups.setdefault(r["category"], []).append(r)
    rng = random.Random(seed)
    for g in groups.values():
        rng.shuffle(g)
    quota = {c: max(1, round(n * len(g) / len(rows))) for c, g in groups.items()}
    while sum(quota.values()) > n and any(q > 1 for q in quota.values()):
        quota[max(quota, key=lambda c: (quota[c], c))] -= 1
    return [r for c in CATEGORIES if c in groups for r in groups[c][:quota[c]]]


def _cut(text, limit: int = MAX_TRACE_CHARS) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[:limit] + " ..."


def write_sample(rows: list[dict], path: str) -> None:
    lines = ["# Error-analysis sample (annotate the last line of each item)\n"]
    for r in rows:
        lines += [f"## {r['cap']} · {r['category']} · {r['domain']} / {r['uuid']}\n",
                  f"- **Query:** {_cut(r['query'], 500)}",
                  "- **Gold calls:** " + "; ".join(f"`{g['name']}({_cut(json.dumps(g.get('arguments')), 150)})`"
                                                   for g in r["gold_calls"]),
                  "- **Agent calls:** " + ("; ".join(f"`{c['name']}({_cut(json.dumps(c['arguments']), 150)})`"
                                                    for c in r["calls"]) or "none")]
        for e in r["log"] or []:
            if e.startswith("[TOOL RESULT]"):
                lines.append(f"  - {_cut(e)}")
        lines += [f"- **Gold answer:** {_cut(r['gold_answer'])}", f"- **Agent answer:** {_cut(r['answer'], 500)}",
                  f"- **Judge:** {_cut(json.dumps(r['judge'], ensure_ascii=False), 500)}",
                  f"- **Flags:** {', '.join(r['flags']) or '-'}", "- **Root cause:** \n"]
    with open(path, "w") as fh:
        fh.write("\n".join(lines))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-id", help="one run for every capability it has")
    ap.add_argument("--cap-run", action="append", default=[], metavar="CAP=RUN",
                    help="the run for one capability (repeatable); overrides --run-id for that capability")
    ap.add_argument("--sample", type=int, default=0, help="failed items per capability to write to --out")
    ap.add_argument("--out", help="markdown file for the sample (under runs/, not the repo)")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    runs = {cap_id: args.run_id for cap_id in CAPABILITIES} if args.run_id else {}
    runs.update({int(c): r for c, r in (s.split("=", 1) for s in args.cap_run)})
    if not runs or (args.sample and not args.out):
        ap.error("give --run-id or --cap-run, and --out with --sample")

    picked = []
    print("| Category | " + " | ".join(f"Cap {c}" for c in sorted(runs)) + " |\n|---|" + "---:|" * len(runs))
    table, totals = {}, {}
    for cap_id in sorted(runs):
        cap_dir, _ = CAPABILITIES[cap_id]
        rows = load_cap(RUNS_DIR / runs[cap_id], cap_dir)
        failed = [r for r in rows if r["score"] < 1]
        for r in failed:
            r["category"] = category(r)
        table[cap_id], totals[cap_id] = Counter(r["category"] for r in failed), (len(failed), len(rows))
        if args.sample:
            picked += sample(failed, args.sample, args.seed)
    for c in CATEGORIES:
        if any(table[k][c] for k in table):
            print(f"| {c} | " + " | ".join(f"{table[k][c]} ({table[k][c] / max(totals[k][0], 1):.0%})"
                                            for k in sorted(runs)) + " |")
    print("| **failed / items** | " + " | ".join(f"**{f} / {n}**" for f, n in (totals[k] for k in sorted(runs))) + " |")
    print("\nRuns: " + ", ".join(f"Cap {c} `{r}`" for c, r in sorted(runs.items())))
    if args.sample:
        write_sample(picked, args.out)
        print(f"{len(picked)} sampled items -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
