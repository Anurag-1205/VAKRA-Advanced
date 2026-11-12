"""V3: when Groq rejects the model's tool call, show the model the error and let it retry once
(stdlib only at module level).

Groq checks each tool call against the request's tools before it answers. A call to a tool that
is not in the request, arguments that miss a required property or have the wrong type, or
arguments that are not JSON come back as HTTP 400 (code "tool_use_failed", with the model's
output in "failed_generation"). Upstream does not catch it, so the item ends as an agent error
and its earlier tool calls are lost too. After the schema fix this is 6 items of the V5 dev-eval
runs (2 Cap 1, 1 Cap 2, 2 Cap 3, 1 Cap 4).

Here such a rejected LLM call is sent again once, with one more user message that quotes the
error and the rejected call. The note is only in that retry's input, not in the agent's history;
if the retry is rejected too, the error is raised as before.

Used at run time by run_baseline.py --repair-tool-calls (REPAIR_PATCH); each retry is logged to
<output>/v3_repairs.jsonl.

Usage:
    python scripts/tool_call_repair.py --self-test      # the patch on a LangGraph agent, fake LLM
    python scripts/tool_call_repair.py --run-id <run>   # items that still end with a rejected call
"""
import argparse
import asyncio
import json
import os
import re
import sys
import tempfile

REJECTED_CODE = "tool_use_failed"
REJECTED_MESSAGE = re.compile(r"Tool call validation failed|Failed to parse tool call arguments", re.I)
MAX_FAILED_CHARS = 1000  # of the rejected call, quoted in the note


def is_rejected_call(code: str | None, message: str | None) -> bool:
    """True for Groq's tool-call rejections, not for other HTTP 400s (e.g. context too long)."""
    return code == REJECTED_CODE or bool(REJECTED_MESSAGE.search(message or ""))


def repair_note(message: str, failed_generation: str | None = None) -> str:
    """The user message added to the retry."""
    call = (failed_generation or "").strip()
    if len(call) > MAX_FAILED_CHARS:
        call = call[:MAX_FAILED_CHARS] + " ..."
    return ("Your last tool call was rejected and not run. The error was:\n"
            f"{message.strip()}\n"
            + (f"The rejected call was:\n{call}\n" if call else "")
            + "Call only tools from your tool list, by their exact names, with arguments that match "
              "their parameter schemas (every required parameter, the right types), or answer "
              "without a tool call if you can.")


async def self_test() -> int:
    """REPAIR_PATCH on a real LangGraph ReAct agent whose LLM call is faked: Groq's 400 is raised
    as langchain_openai raises it. No network, no cost."""
    import httpx
    import openai
    from langchain_core.messages import AIMessage, HumanMessage
    from langchain_core.outputs import ChatGeneration, ChatResult
    from langchain_core.tools import tool
    from langchain_openai import ChatOpenAI
    from langchain_openai.chat_models.base import BaseChatOpenAI, _handle_openai_bad_request
    from langgraph.prebuilt import create_react_agent

    from run_baseline import REPAIR_PATCH, SCRIPTS_DIR

    seen, script = [], []

    def groq_400(message: str, code: str) -> openai.BadRequestError:
        response = httpx.Response(400, request=httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions"))
        body = {"message": message, "type": "invalid_request_error", "code": code,
                "failed_generation": '{"name": "get_count", "arguments": {}}'}
        return openai.BadRequestError(f"Error code: 400 - {message}", response=response, body=body)

    async def fake_agenerate(self, messages, *args, **kwargs):
        seen.append(messages)
        step = script.pop(0)
        if isinstance(step, Exception):
            _handle_openai_bad_request(step)
        return ChatResult(generations=[ChatGeneration(message=step)])

    @tool
    def get_count(year: int) -> str:
        """Count the rows of a year."""
        return f"42 rows in {year}"

    BaseChatOpenAI._agenerate = fake_agenerate
    out = tempfile.mkdtemp()
    sys.argv = [sys.argv[0], "--output", out]
    exec(REPAIR_PATCH.format(scripts_dir=str(SCRIPTS_DIR)), {"sys": sys})  # as in the shim, which imports sys
    agent = create_react_agent(ChatOpenAI(api_key="none", model="none"), [get_count])
    rejected = ("Tool call validation failed: parameters for tool get_count did not match schema: "
                "errors: [missing properties: 'year']")
    call = AIMessage(content="", tool_calls=[{"name": "get_count", "args": {"year": 2020}, "id": "c1"}])

    async def ask(*steps):
        seen.clear()
        script[:] = list(steps)
        try:
            return (await agent.ainvoke({"messages": [HumanMessage(content="How many in 2020?")]}))["messages"]
        except openai.BadRequestError:
            return None

    history = await ask(groq_400(rejected, REJECTED_CODE), call, AIMessage(content="There are 42."))
    checks = {
        "rejected, then accepted: the agent finishes": history is not None and history[-1].content == "There are 42.",
        "the retry's input ends with the note": "was rejected" in str(seen[1][-1].content),
        "the note is not in the agent's history": history is not None and [m.type for m in history] == ["human", "ai", "tool", "ai"],
        "rejected twice: raised, after one retry": await ask(groq_400(rejected, REJECTED_CODE),
                                                              groq_400(rejected, REJECTED_CODE)) is None and len(seen) == 2,
        "another 400 (context too long): not retried": await ask(groq_400(
            "Please reduce the length of the messages or completion.", "context_length_exceeded")) is None and len(seen) == 1,
    }
    log = [json.loads(ln) for ln in open(os.path.join(out, "v3_repairs.jsonl"))]
    checks["both retries logged"] = [r["retry_calls"] for r in log] == [["get_count"], None] and bool(log[1]["retry_error"])
    for name, ok in checks.items():
        print(f"{'ok ' if ok else 'BAD'} {name}")
    return 0 if all(checks.values()) else 1


def main() -> int:
    from common import RUNS_DIR

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-id", help="list a run's items that still end with a rejected tool call")
    ap.add_argument("--self-test", action="store_true", help="check the patch offline (fake LLM, no cost)")
    args = ap.parse_args()
    if args.self_test:
        return asyncio.run(self_test())
    if not args.run_id:
        ap.error("--run-id or --self-test")
    run = RUNS_DIR / args.run_id

    lost = []
    for f in sorted(run.glob("output/*/*.json")):
        if f.stem.endswith("_tools"):
            continue
        for rec in json.loads(f.read_text()):
            if rec.get("status") == "error" and is_rejected_call(None, rec.get("error")):
                lost.append((f.parent.name, f.stem, rec["uuid"], rec["error"]))
    print(f"{len(lost)} items end with a rejected tool call")
    for cap, domain, uuid, error in lost:
        print(f"  {cap} / {domain} / {uuid}: {error[:200]}")
    for log in sorted(run.glob("output/*/v3_repairs.jsonl")):
        rows = [json.loads(ln) for ln in log.read_text().splitlines() if ln.strip()]
        fixed = sum(r.get("retry_error") is None for r in rows)
        print(f"{log.parent.name}: {len(rows)} rejected calls retried, {fixed} accepted on retry")
    return 0


if __name__ == "__main__":
    sys.exit(main())
