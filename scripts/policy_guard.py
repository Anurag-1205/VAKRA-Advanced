"""V6: follow Cap 4's tool policies (stdlib only at module level).

Every Cap 4 policy in the training data is one of four templates, over 12 topics:

  global  "Use document retrievers to answer questions. Do not use any other type of tool."
  global  "Do not use document retrievers to answer questions. Use other types of tools."
  topic   "If a user's query pertains to <topic>, which is/are about <description>, make sure you
           try answering them by only using document retrievers. Do not use other types of tools."
  topic   "... make sure you do not use document retrievers to try answering those questions. ..."

Document retrievers are the query_* tools; the data tools (get_*) are "other types". In all 898
training dialogues, the gold answer is "I can not answer." exactly when only retrievers are
allowed and the policy applies: always for the global form (65 / 65), and for the topic form
when the topic is the domain's (68 / 68, 0 of the other 79). Each domain has one topic.

So, per dialogue:
  only retrievers, applies   -> answer "I can not answer." with no tool call
  no retrievers, applies     -> the agent runs without the query_* tools
  otherwise                  -> unchanged

A domain's topic is looked up in DOMAIN_TOPICS_FILE: the topics the training gold shows for
domains of train-rest and dev-seen, so no held-out (dev-eval) domain is in it. For any other
domain the agent's LLM picks the topic from the domain's name and tool names, once per domain;
`--check` scores that call on all 29 labelled training domains.

Used at run time by run_baseline.py --policy-guard (POLICY_PATCH).

Usage:
    python scripts/policy_guard.py --write-topics   # rebuild DOMAIN_TOPICS_FILE (no LLM)
    python scripts/policy_guard.py --check          # LLM topic call vs the training labels
"""
import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

REFUSAL = "I can not answer."
RETRIEVER_PREFIX = "query_"
MAX_TOOL_NAMES = 30  # in the topic prompt
TOPIC_SPLITS = ("train-rest", "dev-seen")  # no held-out domain
DOMAIN_TOPICS_FILE = Path(__file__).resolve().parent.parent / "splits" / "cap4_domain_topics.json"

TOPICS = {
    "Food, Restaurants & Beverage": "Topics concerning restaurants, food inspection, menu items, and beverages like beer",
    "Transportation & Mobility": "Topics dealing with modes of transport such as trains, cars, bikes, and flights",
    "Movies, TV & Entertainment, Social Media": "Topics focused on movies, episodes, characters, and streaming platforms",
    "Government, Law & Public Services, Human Capital": "Topics concerning legislation, public databases, law enforcement, and civic institutions",
    "Literature, Language & Publishing": "Topics focusing on books, authors, literary works, and linguistic corpora",
    "Sports & Athletics": "Topics covering various sports, athletes, games, and statistics from different leagues",
    "Education & Students": "Topics related to schools, universities, student information, and education statistics",
    "Finance & Economics": "Topics that revolve around financial data, transactions, donations, and currencies",
    "Health & Medicine": "Topics that pertain to health data, medical conditions, surveys, and synthetic patients",
    "Retail, Sales & Commerce": "Topics related to retail operations, customer purchases, inventory, and product ordering",
    "Technology & Software": "Topics focusing on codebases, software platforms, applications, and user interactions in tech",
    "Geography & Demographics": "Topics centered around population, regional information, countries, and life expectancy",
}

_TOPIC_POLICY = re.compile(r"If a user's query pertains to (.+?), which is/are about (.+?), make sure")


def parse_policy(text: str | None) -> tuple[str | None, str | None, str | None]:
    """(mode, topic, description): mode is "only" (retrievers only), "no" (no retrievers) or None;
    topic is None for a global policy."""
    text = (text or "").strip()
    if "only using document retrievers" in text or text.startswith("Use document retrievers"):
        mode = "only"
    elif "not use document retrievers" in text:
        mode = "no"
    else:
        return None, None, None
    m = _TOPIC_POLICY.match(text)
    return (mode, m.group(1), m.group(2)) if m else (mode, None, None)


def candidate_topics(topic: str | None, description: str | None) -> dict[str, str]:
    """TOPICS, plus a policy's topic if it is a new one."""
    return TOPICS if not topic or topic in TOPICS else {**TOPICS, topic: description or ""}


def topic_prompt(domain: str, tool_names: list[str], topics: dict[str, str]) -> str:
    names = [n for n in tool_names if not n.startswith(RETRIEVER_PREFIX)][:MAX_TOOL_NAMES]
    listing = "\n".join(f"- {t}: {d}" for t, d in topics.items())
    return (f"A database is named \"{domain}\". Some of its tools: {', '.join(names)}.\n\n"
            f"Which one of these topics does the database belong to?\n{listing}\n\n"
            "Reply with the topic name only, exactly as written above.")


def parse_topic(reply: str, topics: dict[str, str]) -> str | None:
    reply = reply.strip().strip("\"'*.` ").lower()
    for t in topics:
        if reply == t.lower() or reply.startswith(t.lower()):
            return t
    return None


def known_topics() -> dict[str, str]:
    """{domain: topic} from DOMAIN_TOPICS_FILE ({} if it was not built)."""
    return json.loads(DOMAIN_TOPICS_FILE.read_text())["topics"] if DOMAIN_TOPICS_FILE.exists() else {}


def training_labels(splits: tuple[str, ...] | None = TOPIC_SPLITS) -> dict[str, str]:
    """{domain: topic} from the training gold: the topic of a retrievers-only policy that refuses.
    Only items of the given splits (None: all training items)."""
    from common import TRAIN_DIR, load_split

    cap = TRAIN_DIR / "capability_4_multiturn"
    keep = None if splits is None else {u for s in splits for u in load_split(s).get(cap.name, [])}
    labels = {}
    for f in sorted((cap / "input").glob("*.json")):
        gold = {r["uuid"]: r for r in json.loads((cap / "output" / f.name).read_text())}
        for r in json.loads(f.read_text()):
            if keep is not None and r["uuid"] not in keep:
                continue
            mode, topic, _ = parse_policy(r.get("additional_instructions"))
            answer = str(gold[r["uuid"]]["output"][-1].get("answer", "")).lower()
            if mode == "only" and topic and "i can not answer" in answer:
                labels[r["domain"]] = topic
    return labels


async def check(model: str) -> int:
    """The LLM topic call (no lookup) on every labelled training domain, against its label."""
    from openai import AsyncOpenAI

    from common import subprocess_env
    from tool_recall import fetch_catalog

    env = subprocess_env(agent_backend="groq")
    client = AsyncOpenAI(base_url=env["OPENAI_BASE_URL"], api_key=env["OPENAI_API_KEY"])
    labels = training_labels(None)
    right = 0
    for domain, label in sorted(labels.items()):
        names = [t["name"] for t in await fetch_catalog(4, domain)]
        msg = await client.chat.completions.create(
            model=model, temperature=0,
            messages=[{"role": "user", "content": topic_prompt(domain, names, TOPICS)}])
        picked = parse_topic(msg.choices[0].message.content or "", TOPICS)
        right += picked == label
        print(f"{'ok ' if picked == label else 'BAD'} {domain}: label {label!r}, picked {picked!r}")
    print(f"{right} / {len(labels)} domains right")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--write-topics", action="store_true", help=f"rebuild {DOMAIN_TOPICS_FILE.name}")
    ap.add_argument("--check", action="store_true", help="score the LLM topic call on the training domains")
    ap.add_argument("--model", default="openai/gpt-oss-120b")
    args = ap.parse_args()
    if args.check:
        return asyncio.run(check(args.model))
    if args.write_topics:
        topics = training_labels()
        DOMAIN_TOPICS_FILE.write_text(json.dumps(
            {"_comment": f"Built by scripts/policy_guard.py --write-topics from Cap 4 gold of {list(TOPIC_SPLITS)}",
             "topics": dict(sorted(topics.items()))}, indent=1) + "\n")
        print(f"{len(topics)} domains -> {DOMAIN_TOPICS_FILE}")
        return 0
    for domain, topic in sorted(known_topics().items()):
        print(f"{domain}: {topic}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
