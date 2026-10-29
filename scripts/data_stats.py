"""Descriptive statistics of the VAKRA train split, for the report.

Per capability: domains, items, gold tool calls per item (hops) for all train and for
dev-eval; tool catalog sizes per domain (Caps 2-4); and for Cap 4: turns per dialogue,
document-retrieval vs API calls, tool-use policies and "I can not answer" turns.

Output files are parsed as an ijson event stream (`pip install ijson`), keeping only tool
names, policies and an unanswerable flag: some files are > 2 GB (movie_platform) and single
records hold table dumps of hundreds of MB, so even per-record parsing ran out of a 3 GB cap.
Tool catalogs are listed over MCP from the running containers and cached in
generated/tool_catalogs/ (needs no databases). No LLM calls.

Usage:
    python scripts/data_stats.py > stats.md
"""
import asyncio
import re
import statistics
import sys
from collections import Counter

import ijson

from common import CAPABILITIES, TRAIN_DIR, load_split

HOP_BINS = ("0", "1", "2", "3", "4", "5+")
# Cap 1 gold sequences start with initialize_active_data, which the evaluator strips
# (SPEC §11 q2), so it is not counted as a hop.
NOT_A_HOP = {"initialize_active_data"}


def hop_bin(n: int) -> str:
    return str(n) if n < 5 else "5+"


def records(cap_dir: str, domain: str):
    """Yield {uuid, policy, turns: [{names, unanswerable}]} per gold output record."""
    with open(TRAIN_DIR / cap_dir / "output" / f"{domain}.json", "rb") as fh:
        rec = turn = None
        for prefix, event, value in ijson.parse(fh):
            if prefix == "item" and event == "start_map":
                rec = {"uuid": None, "policy": None, "turns": []}
            elif prefix == "item" and event == "end_map":
                yield rec
            elif prefix == "item.uuid":
                rec["uuid"] = value
            elif prefix == "item.additional_instructions" and event == "string":
                rec["policy"] = value
            elif prefix == "item.output.item" and event == "start_map":
                turn = {"names": [], "unanswerable": False}
                rec["turns"].append(turn)
            elif prefix == "item.output.item.sequence.tool_call.item.name":
                turn["names"].append(value)
            elif prefix.startswith("item.output.item.answer") and event == "string":
                low = value[:200].lower()
                turn["unanswerable"] |= "can not answer" in low or "cannot answer" in low


def domains(cap_dir: str) -> list[str]:
    return sorted(f.stem for f in (TRAIN_DIR / cap_dir / "input").glob("*.json"))


def policy_category(text: str) -> tuple[str, str | None]:
    p = text.lower()
    scope = "topic-conditional" if p.startswith("if a user's query pertains to") else "all queries"
    if "only using document retrievers" in p or "use document retrievers to answer questions. do not use any other" in p:
        rule = "documents only"
    elif "do not use document retrievers" in p:
        rule = "no document retrievers"
    else:
        rule = "other"
    topic = None
    if scope == "topic-conditional":
        m = re.search(r"pertains to (.+?), which", text)
        topic = m.group(1) if m else "?"
    return f"{scope}: {rule}", topic


def pct(n: int, d: int) -> str:
    return f"{n} ({n / d:.0%})" if d else "0"


def hist_row(label: str, c: Counter) -> str:
    n = sum(c.values())
    return f"| {label} | {n} | " + " | ".join(f"{c[b] / n:.0%}" if n else "–" for b in HOP_BINS) + " |"


def main() -> int:
    dev_eval = {cap: set(u) for cap, u in load_split("dev-eval").items()}
    out = []

    # 1. Overview
    out += ["## Items and domains", "",
            "| Cap | Domains | Items | Items per domain (min / median / max) | dev-eval items |",
            "|---|---:|---:|---|---:|"]
    hops = {}
    cap4 = {}
    for cap_id, (cap_dir, _) in CAPABILITIES.items():
        per_domain = []
        hops[cap_id] = {"all": Counter(), "dev-eval": Counter()}
        for dom in domains(cap_dir):
            n = 0
            for rec in records(cap_dir, dom):
                n += 1
                calls_per_turn = [sum(name not in NOT_A_HOP for name in t["names"]) for t in rec["turns"]]
                for split in ("all", "dev-eval"):
                    if split == "dev-eval" and rec["uuid"] not in dev_eval.get(cap_dir, ()):
                        continue
                    for k in calls_per_turn:
                        hops[cap_id][split][hop_bin(k)] += 1
                if cap_id == 4:
                    collect_cap4(cap4, rec, dev_eval[cap_dir])
            per_domain.append(n)
        out.append(f"| {cap_id} | {len(per_domain)} | {sum(per_domain)} | {min(per_domain)} / "
                   f"{statistics.median(per_domain):g} / {max(per_domain)} | {len(dev_eval.get(cap_dir, ()))} |")

    # 2. Hops
    out += ["", "## Gold tool calls per item (per turn for Cap 4)", "",
            "| Cap / set | n | " + " | ".join(f"{b} calls" for b in HOP_BINS) + " |",
            "|---|---:|" + "---:|" * len(HOP_BINS)]
    for cap_id in CAPABILITIES:
        for split in ("all", "dev-eval"):
            out.append(hist_row(f"Cap {cap_id}, {split}", hops[cap_id][split]))

    # 3. Tool catalogs (imported late: tool_recall pulls in sentence-transformers / torch)
    from tool_recall import fetch_catalog
    out += ["", "## Tool catalog size per domain (tools offered to the agent)", "",
            "| Cap | Domains | min | median | mean | max | domains with > 128 tools |",
            "|---|---:|---:|---:|---:|---:|---:|"]
    for cap_id in (2, 3, 4):
        cap_dir, _ = CAPABILITIES[cap_id]
        sizes = [len(asyncio.run(fetch_catalog(cap_id, d))) for d in domains(cap_dir)]
        out.append(f"| {cap_id} | {len(sizes)} | {min(sizes)} | {statistics.median(sizes):g} | "
                   f"{statistics.mean(sizes):.0f} | {max(sizes)} | {sum(s > 128 for s in sizes)} |")

    # 4. Cap 4
    out += cap4_section(cap4)
    print("\n".join(out))
    return 0


def collect_cap4(acc: dict, rec: dict, dev_eval_uuids: set[str]) -> None:
    for split in ("all", "dev-eval"):
        if split == "dev-eval" and rec["uuid"] not in dev_eval_uuids:
            continue
        a = acc.setdefault(split, {"dialogues": 0, "turns": Counter(), "turn_kind": Counter(),
                                   "unanswerable": 0, "n_turns": 0, "policy": Counter(), "topics": Counter(),
                                   "unans_with_policy": 0, "unans_no_tools": 0})
        a["dialogues"] += 1
        a["turns"][hop_bin(len(rec["turns"]))] += 1
        policy = rec["policy"]
        if policy:
            cat, topic = policy_category(policy)
            a["policy"][cat] += 1
            if topic:
                a["topics"][topic] += 1
        else:
            a["policy"]["no policy"] += 1
        for t in rec["turns"]:
            a["n_turns"] += 1
            names = t["names"]
            # Gold names retrievers retriever_clapnq_<domain>; the live server exposes them as query_<domain>.
            docs = sum(n.startswith(("retriever_", "query_")) for n in names)
            kind = "no tool call" if not names else "documents only" if docs == len(names) else \
                "APIs only" if docs == 0 else "documents + APIs"
            a["turn_kind"][kind] += 1
            if t["unanswerable"]:
                a["unanswerable"] += 1
                a["unans_with_policy"] += bool(policy)
                a["unans_no_tools"] += not names


def cap4_section(acc: dict) -> list[str]:
    out = ["", "## Cap 4: multi-turn dialogues, documents and policies", "",
           "| | all train | dev-eval |", "|---|---:|---:|"]
    al, ev = acc["all"], acc["dev-eval"]
    rows = [
        ("Dialogues", al["dialogues"], ev["dialogues"]),
        ("Turns", al["n_turns"], ev["n_turns"]),
    ]
    out += [f"| {k} | {a} | {e} |" for k, a, e in rows]
    for b in HOP_BINS[1:]:
        out.append(f"| Dialogues with {b} turn(s) | {pct(al['turns'][b], al['dialogues'])} | "
                   f"{pct(ev['turns'][b], ev['dialogues'])} |")
    for kind in ("APIs only", "documents only", "documents + APIs", "no tool call"):
        out.append(f"| Turns: {kind} | {pct(al['turn_kind'][kind], al['n_turns'])} | "
                   f"{pct(ev['turn_kind'][kind], ev['n_turns'])} |")
    out.append(f"| Turns whose gold answer is \"I can not answer\" | {pct(al['unanswerable'], al['n_turns'])} | "
               f"{pct(ev['unanswerable'], ev['n_turns'])} |")
    out.append(f"| … of which the dialogue has a policy | {pct(al['unans_with_policy'], al['unanswerable'])} | "
               f"{pct(ev['unans_with_policy'], ev['unanswerable'])} |")
    out.append(f"| … of which the gold makes no tool call | {pct(al['unans_no_tools'], al['unanswerable'])} | "
               f"{pct(ev['unans_no_tools'], ev['unanswerable'])} |")
    out += ["", "**Tool-use policies (per dialogue):**", "", "| Policy | all train | dev-eval |", "|---|---:|---:|"]
    for cat in sorted(set(al["policy"]) | set(ev["policy"])):
        out.append(f"| {cat} | {pct(al['policy'][cat], al['dialogues'])} | {pct(ev['policy'][cat], ev['dialogues'])} |")
    out += ["", "**Topics named by topic-conditional policies (all train):**", ""]
    out += [f"- {t}: {n}" for t, n in al["topics"].most_common()]
    return out


if __name__ == "__main__":
    sys.exit(main())
