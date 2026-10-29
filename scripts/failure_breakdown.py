"""Break a scored run down by outcome: correct, agent error, or which scorer stage failed.

Reads runs/<run_id>/output (agent status and errors) and runs/<run_id>/eval (upstream
evaluator details). Upstream's scorer (evaluator/scorer.py) checks the gold tool responses
first ("exact match"); if those are present it only judges groundedness, otherwise it
judges the answer, then groundedness.

Usage:
    python scripts/failure_breakdown.py --run-id 20261029-1738-v0-groq-dev-eval
"""
import argparse
import json
import sys
from collections import Counter

from common import CAPABILITIES, RUNS_DIR


def outcome(score: float, pred: dict, meta: dict) -> str:
    if score == 1.0:
        # Upstream gives full credit when the gold says "I can not answer" and no tool was called,
        # which a crashed agent also satisfies (empty answer, no calls). Keep that apart.
        if pred.get("status") == "error":
            return "credited, but the agent crashed (unanswerable gold, no tool call)"
        grounded = (meta.get("score_explanation") or {}).get("groundedness") or ""
        if "Special case" in grounded:
            return "correct: abstained on an unanswerable item"
        return "correct: exact tool match" if meta.get("exactmatch_score") == 1.0 else "correct: answer judged right"
    if pred.get("status") == "error":
        err = pred.get("error", "")
        if "validation failed" in err:
            return "agent error: tool call missing a required argument (Groq HTTP 400)"
        if "reduce the length" in err:
            return "agent error: context too long"
        return "agent error: " + err[:50]
    if meta.get("exactmatch_score") == 1.0:
        return "right tool responses, answer not grounded"
    if meta.get("answer_score") == 0.0:
        return "wrong or no answer"
    if meta.get("groundedness_score") == 0.0:
        return "right answer, not grounded"
    return "other"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-id", required=True)
    args = ap.parse_args()
    run = RUNS_DIR / args.run_id

    for cap_dir, _ in CAPABILITIES.values():
        eval_file = run / "eval" / f"{cap_dir}.json"
        if not eval_file.exists():
            continue
        preds = {}
        for f in (run / "output" / cap_dir).glob("*.json"):
            if not f.stem.endswith("_tools"):
                preds.update({r["uuid"]: r for r in json.loads(f.read_text())})
        counts = Counter()
        for dom in json.loads(eval_file.read_text())["domains"].values():
            for d in dom["dialogues"]:
                # One scored turn per item: Caps 2-3 are single-turn, and for Cap 4 upstream scores
                # only the final turn (earlier turns are given as history with their gold answers).
                meta = d["details"]["per_turn"][0]["metadata"]
                counts[outcome(d["score"], preds.get(d["uuid"], {}), meta)] += 1
        n = sum(counts.values())
        print(f"\n{cap_dir} (n={n})")
        for key, v in counts.most_common():
            print(f"  {v:4d}  {v / n:6.1%}  {key}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
