"""Shorten long earlier answers in Cap 4 dialogue histories (no upstream imports).

Upstream (benchmark/runner_helpers.py, BenchmarkItem.from_dict) puts every earlier turn's gold
answer into the history as str(answer). Some are whole tables (up to 9.4M characters, 258k
rows), so the first LLM call is rejected ("Please reduce the length of the messages") before any
tool is called: 10 of the 60 dev-eval dialogues. Here an earlier answer longer than
MAX_HISTORY_CHARS keeps its first rows plus a note with the total, and the agent can still
call tools for the rest.

Used at run time by run_baseline.py --short-history (HISTORY_PATCH); `python
scripts/short_history.py --run-id <run>` checks it offline on a run's Cap 4 inputs.
"""
import argparse
import json
import sys

MAX_HISTORY_CHARS = 2000  # per earlier answer, as upstream renders it (str)


def shorten_answer(answer, max_chars: int = MAX_HISTORY_CHARS):
    """The answer unchanged if str(answer) fits, else a string with its first rows and a note."""
    text = str(answer)
    if len(text) <= max_chars:
        return answer
    if isinstance(answer, list):
        k = 0
        while k < len(answer) and len(str(answer[:k + 1])) <= max_chars:
            k += 1
        if k:
            return f"{answer[:k]} ... ({len(answer)} rows in total; only the first {k} are shown)"
    return f"{text[:max_chars]} ... (cut; {len(text)} characters in total)"


def shorten_dialogue(data: dict, max_chars: int = MAX_HISTORY_CHARS) -> dict:
    """A copy of a Cap 4 input item with every turn's answer shortened."""
    dialogue = data.get("dialogue") or {}
    turns = [{**t, "answer": shorten_answer(t["answer"], max_chars)} if t.get("answer") else t
             for t in dialogue.get("turns", [])]
    return {**data, "dialogue": {**dialogue, "turns": turns}}


def main() -> int:
    from common import RUNS_DIR

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-id", required=True, help="a run with Cap 4 inputs in data/")
    ap.add_argument("--max-chars", type=int, default=MAX_HISTORY_CHARS)
    args = ap.parse_args()

    files = sorted((RUNS_DIR / args.run_id / "data" / "capability_4_multiturn" / "input").glob("*.json"))
    rows = []
    for f in files:
        for item in json.loads(f.read_text()):
            turns = item["dialogue"]["turns"]
            short = shorten_dialogue(item, args.max_chars)["dialogue"]["turns"]
            before = sum(len(t["query"]) + len(str(t.get("answer") or "")) for t in turns)
            after = sum(len(t["query"]) + len(str(t.get("answer") or "")) for t in short)
            rows.append((item["uuid"], f.stem, before, after))
    changed = [r for r in rows if r[2] != r[3]]
    print(f"{len(rows)} dialogues, {len(changed)} shortened (max {args.max_chars} characters per answer)")
    print("| uuid | domain | history chars before | after |\n|---|---|---:|---:|")
    for uuid, domain, before, after in sorted(changed, key=lambda r: -r[2]):
        print(f"| {uuid} | {domain} | {before:,} | {after:,} |")
    print(f"largest history after: {max(r[3] for r in rows):,} characters")
    return 0


if __name__ == "__main__":
    sys.exit(main())
