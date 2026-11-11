"""Run the unmodified upstream V0 baseline (LangGraphReActAgent) on one of our splits.

For each capability: copy the split's items into runs/<run_id>/data/<cap_dir>/,
point upstream's CAPABILITY_<N>_DIR at it, and invoke third_party/vakra/benchmark_runner.py.
Predictions land in runs/<run_id>/output/<cap_dir>/<domain>.json (official format).

V2 (--retriever bm25|hybrid) is the same agent with our tool shortlist (scripts/retrieval.py)
patched in at run time; upstream's code is not modified. --fix-tool-schema adds the
zero-parameter tool-schema fix (SCHEMA_PATCH) to either. --refresh-tools fixes upstream's Cap 1
tool list going stale (see REFRESH_PATCH). --evidence-answer is V5: the final answer is rewritten
from the run's tool results only (ANSWER_PATCH, answer_rewrite.py). --short-history shortens long
earlier answers in Cap 4 dialogue histories (HISTORY_PATCH, short_history.py). --policy-guard is V6:
Cap 4's tool policies are followed, not only stated (POLICY_PATCH, policy_guard.py).

Usage:
    python scripts/run_baseline.py --split smoke --caps 1 2 3
    python scripts/run_baseline.py --split dev-heldout --caps 2 --max-per-domain 3
    python scripts/run_baseline.py --split dev-eval --caps 2 3 --retriever hybrid --top-k-tools 50
    python scripts/run_baseline.py --split dev-eval --caps 2 3 --retriever hybrid --fix-tool-schema
"""
import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from common import AGENT_BACKENDS, CAPABILITIES, REPO_ROOT, RUNS_DIR, UPSTREAM, materialize_split, subprocess_env

SCRIPTS_DIR = Path(__file__).resolve().parent
RETRIEVERS = ("minilm", "bm25", "hybrid")  # as in retrieval.py, which imports upstream code

DEFAULT_MODELS = {"groq": "openai/gpt-oss-120b", "gemini": "gemini-3.8-flash"}

# Patches applied in the runner's process before upstream's benchmark_runner.py runs unchanged.
SHIM = """
import runpy, sys
{patches}
sys.argv[0] = "benchmark_runner.py"
runpy.run_path("benchmark_runner.py", run_name="__main__")
"""

# Upstream create_llm builds ChatOpenAI with langchain's default max_retries=2. On Groq's
# free tier, an HTTP 429 (tokens/minute) that outlasts two retries ends the item as an error,
# which scores rate limiting as agent failure. This raises the default; prompts, tools and
# agent logic are untouched.
RETRY_PATCH = """
from langchain_openai import ChatOpenAI
_init = ChatOpenAI.__init__
def _init_with_retries(self, *args, **kwargs):
    kwargs.setdefault("max_retries", {max_retries})
    _init(self, *args, **kwargs)
ChatOpenAI.__init__ = _init_with_retries
"""

# Cap 1's server (RouterMCPServer) swaps its tool set when get_data switches to an item's
# universe: generic tools (filter_data, ...) for "slot_filling" items, item-specific ones
# (select_data_equal_to, get_<Column>s, ...) for "selection" items. Upstream's runner lists tools
# once per domain, so on items of the other type every call is "Unknown tool" and the agent loops.
# This re-lists the tools before each agent run (after the switch) and rebuilds the agent when
# they changed; a no-op for Caps 2-4, whose tools never change.
REFRESH_PATCH = """
import agents.agent_interface, agents.mcp_tool_wrapper
_wrappers = []
_wrapper_init = agents.mcp_tool_wrapper.MCPToolWrapper.__init__
def _track_wrapper(self, *args, **kwargs):
    _wrapper_init(self, *args, **kwargs)
    _wrappers[:] = [self]
agents.mcp_tool_wrapper.MCPToolWrapper.__init__ = _track_wrapper
_run = agents.agent_interface.LangGraphReActAgent.run
async def _run_with_current_tools(self, *args, **kwargs):
    if _wrappers:
        wrapper = _wrappers[0]
        tools = [wrapper._create_langchain_tool(t) for t in (await wrapper.session.list_tools()).tools]
        if [t.name for t in tools] != [t.name for t in self._tools]:
            self._tools = tools
            self._agent = self._build_agent(tools)
            if self._shortlister is not None:
                self._shortlister.encode_tools(tools)
    return await _run(self, *args, **kwargs)
agents.agent_interface.LangGraphReActAgent.run = _run_with_current_tools
"""

# V2: swap upstream's MiniLM shortlist for ours. Appended (not prepended) to sys.path so
# upstream's own modules always win a name clash.
RETRIEVER_PATCH = """
sys.path.append({scripts_dir!r})
import agents.agent_interface
from retrieval import Shortlister
Shortlister.retriever = {retriever!r}
agents.agent_interface.ToolShortlister = Shortlister
"""

# Tool-schema fix (--fix-tool-schema). For a tool with no parameters, upstream's
# MCPToolWrapper._convert_json_schema_to_pydantic returns None, so LangChain infers a schema
# from the wrapper's (**kwargs) function and sends the LLM an `args` array, a required
# `config` (LangChain's RunnableConfig, with its whole docstring) and `kwargs`. Groq then
# rejects the model's correct `{}` call with HTTP 400 ("missing properties: 'config'" or
# "`/args`: expected array, but got null"). Here such a tool gets an explicit empty schema,
# which the LLM sees as {"properties": {}, "type": "object"}. Tools with parameters are
# unchanged, as are prompts, the tool calls sent to the MCP server and the agent logic.
SCHEMA_PATCH = """
from pydantic import create_model
from agents.mcp_tool_wrapper import MCPToolWrapper
_to_pydantic = MCPToolWrapper._convert_json_schema_to_pydantic
def _to_pydantic_or_empty(self, tool_name, input_schema):
    model = _to_pydantic(self, tool_name, input_schema)
    return model if model is not None else create_model(f"{tool_name}Input")
MCPToolWrapper._convert_json_schema_to_pydantic = _to_pydantic_or_empty
"""

# --short-history (#7): upstream puts every earlier Cap 4 turn's gold answer into the history
# in full, and the longest (up to 9.4M characters) make the first LLM call fail. Each earlier
# answer over MAX_HISTORY_CHARS keeps its first rows plus a note with the total (short_history.py).
# Only the agent's input changes; the evaluator never reads the history.
HISTORY_PATCH = """
sys.path.append({scripts_dir!r})
from benchmark.runner_helpers import BenchmarkItem
from short_history import shorten_dialogue
_from_dict = BenchmarkItem.from_dict.__func__
BenchmarkItem.from_dict = classmethod(lambda cls, data: _from_dict(cls, shorten_dialogue(data)))
"""

# V6 (--policy-guard): Cap 4 dialogues carry a tool policy that upstream only states to the model
# (and, for single-turn dialogues, not at all). Here the policy is followed (policy_guard.py):
# "only document retrievers" -> "I can not answer." with no tool call, as the gold does in every
# training dialogue; "no document retrievers" -> the agent runs without the query_* tools. A
# topic policy applies when it names the domain's topic. The domain comes from the MCP connect
# call. Each decision is appended to <output>/v6_policy.jsonl.
POLICY_PATCH = """
sys.path.append({scripts_dir!r})
import json, os
import agents.agent_interface, benchmark.mcp_client
from langchain_core.messages import HumanMessage
from policy_guard import (REFUSAL, RETRIEVER_PREFIX, candidate_topics, known_topics, parse_policy,
                          parse_topic, topic_prompt)
_domain, _domain_topic = [""], known_topics()
_connect = benchmark.mcp_client.create_client_and_connect
def _connect_noting_domain(cfg, domain="", *args, **kwargs):
    _domain[0] = domain
    return _connect(cfg, domain, *args, **kwargs)
benchmark.mcp_client.create_client_and_connect = _connect_noting_domain
_policy_log = os.path.join(sys.argv[sys.argv.index("--output") + 1], "v6_policy.jsonl") if "--output" in sys.argv else None
async def _topic_of(agent, topic, description):
    domain = _domain[0]
    if domain not in _domain_topic:
        topics = candidate_topics(topic, description)
        msg = await agent._llm.ainvoke([HumanMessage(content=topic_prompt(domain, [t.name for t in agent._tools], topics))])
        _domain_topic[domain] = parse_topic(str(msg.content), topics)
    return _domain_topic[domain]
_policy_run = agents.agent_interface.LangGraphReActAgent.run
async def _run_with_policy(self, input, additional_instructions=None, *args, **kwargs):
    mode, topic, description = parse_policy(additional_instructions)
    domain_topic = await _topic_of(self, topic, description) if topic else None
    applies = mode is not None and (topic is None or domain_topic == topic)
    action = ("refuse" if mode == "only" else "no retrievers") if applies else "unchanged"
    if _policy_log and mode is not None:
        os.makedirs(os.path.dirname(_policy_log), exist_ok=True)
        with open(_policy_log, "a") as fh:
            fh.write(json.dumps({{"domain": _domain[0], "mode": mode, "topic": topic,
                                 "domain_topic": domain_topic, "action": action}}) + "\\n")
    if action == "refuse":
        return agents.agent_interface.AgentResponse(content=REFUSAL, all_tools=[t.name for t in self._tools])
    if action == "no retrievers":
        build, agent = self._build_agent, self._agent
        allowed = lambda tools: [t for t in tools if not t.name.startswith(RETRIEVER_PREFIX)]
        self._build_agent = lambda tools: build(allowed(tools))
        self._agent = build(allowed(self._tools))
        try:
            return await _policy_run(self, input, additional_instructions, *args, **kwargs)
        finally:
            del self._build_agent
            self._agent = agent
    return await _policy_run(self, input, additional_instructions, *args, **kwargs)
agents.agent_interface.LangGraphReActAgent.run = _run_with_policy
"""

# V5 (--evidence-answer): after the agent finishes, the same LLM rewrites its final answer from
# that run's tool calls and results only (answer_rewrite.py). The tool calls, and so the replayed
# evidence the judges see, are unchanged. Skipped when no tool was called, so Cap 4's
# "no tool call" refusals keep upstream's special-case credit. On a failed rewrite the draft is kept.
# Each rewrite (query, draft, final answer) is appended to <output>/v5_drafts.jsonl, so V5's own
# changes can be told apart from run-to-run agent noise.
ANSWER_PATCH = """
sys.path.append({scripts_dir!r})
import json, logging, os
import agents.agent_interface
from langchain_core.messages import HumanMessage, SystemMessage
from answer_rewrite import V5_PROMPT, evidence_prompt
_answer_run = agents.agent_interface.LangGraphReActAgent.run
_drafts = os.path.join(sys.argv[sys.argv.index("--output") + 1], "v5_drafts.jsonl") if "--output" in sys.argv else None
async def _run_with_evidence_answer(self, input, *args, **kwargs):
    response = await _answer_run(self, input, *args, **kwargs)
    if response.content and response.tool_calls:
        query = input if isinstance(input, str) else next(
            (m.content for m in reversed(input) if m.role == "user"), "")
        calls = [(c["tool_name"], c["arguments"], c["result"]) for c in response.tool_calls]
        draft, error = response.content, None
        try:
            msg = await self._llm.ainvoke([SystemMessage(content=V5_PROMPT),
                                           HumanMessage(content=evidence_prompt(query, calls, draft))])
            if str(msg.content).strip():
                response.content = str(msg.content).strip()
        except Exception as e:
            error = repr(e)[:300]
            logging.getLogger("v5").warning("evidence-answer rewrite failed, keeping the draft: %s", error)
        if _drafts:
            os.makedirs(os.path.dirname(_drafts), exist_ok=True)
            with open(_drafts, "a") as fh:
                fh.write(json.dumps({{"query": query, "draft": draft, "answer": response.content,
                                     "n_tool_calls": len(calls), "error": error}}, ensure_ascii=False) + "\\n")
    return response
agents.agent_interface.LangGraphReActAgent.run = _run_with_evidence_answer
"""


def git_sha(path: Path) -> str:
    """Short HEAD sha, suffixed '-dirty' when tracked files have local changes."""
    out = subprocess.run(["git", "-C", str(path), "rev-parse", "--short", "HEAD"], capture_output=True, text=True)
    dirty = subprocess.run(["git", "-C", str(path), "status", "--porcelain", "--untracked-files=no"],
                           capture_output=True, text=True).stdout.strip()
    return (out.stdout.strip() or "unknown") + ("-dirty" if dirty else "")


def summarize(out_dir: Path) -> dict:
    """Count statuses, tool calls and agent wall time from upstream output files."""
    stats = {"items": 0, "success": 0, "error": 0, "tool_calls": 0, "agent_seconds": 0.0, "errors": {}}
    for f in sorted(out_dir.glob("*.json")):
        if f.stem.endswith("_tools"):
            continue
        for rec in json.loads(f.read_text()):
            stats["items"] += 1
            status = rec.get("status", "error")
            stats["success" if status == "success" else "error"] += 1
            stats["agent_seconds"] += rec.get("duration_s") or 0.0
            for turn in rec.get("output", []):
                stats["tool_calls"] += len((turn.get("sequence") or {}).get("tool_call", []))
            if status != "success":
                key = (rec.get("error") or "unknown")[:120]
                stats["errors"][key] = stats["errors"].get(key, 0) + 1
    stats["agent_seconds"] = round(stats["agent_seconds"], 1)
    return stats


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--split", default="smoke")
    ap.add_argument("--caps", type=int, nargs="+", default=[1, 2, 3, 4], choices=sorted(CAPABILITIES))
    ap.add_argument("--max-per-domain", type=int, default=None)
    ap.add_argument("--agent-backend", default="groq", choices=sorted(AGENT_BACKENDS),
                    help="OpenAI-compatible endpoint for the agent (judge always uses Groq)")
    ap.add_argument("--provider", default="openai", help="upstream create_llm provider (openai -> backend via OPENAI_BASE_URL)")
    ap.add_argument("--model", default=None, help=f"default per backend: {DEFAULT_MODELS}")
    ap.add_argument("--top-k-tools", type=int, default=128, help="upstream default is 128")
    ap.add_argument("--retriever", default="minilm", choices=RETRIEVERS,
                    help="tool shortlist ranking: minilm is upstream's (V0); bm25 or hybrid is V2")
    ap.add_argument("--fix-tool-schema", action="store_true",
                    help="give zero-parameter tools an empty schema instead of LangChain's inferred one")
    ap.add_argument("--max-iterations", type=int, default=None)
    ap.add_argument("--refresh-tools", action="store_true",
                    help="re-list tools after Cap 1's per-item universe switch (fixes an upstream runner bug)")
    ap.add_argument("--evidence-answer", action="store_true",
                    help="V5: rewrite the final answer from the run's tool results only")
    ap.add_argument("--short-history", action="store_true",
                    help="Cap 4: shorten long earlier answers in the dialogue history (first rows + total)")
    ap.add_argument("--policy-guard", action="store_true",
                    help="V6: follow Cap 4's tool policies (refuse when only retrievers are allowed)")
    ap.add_argument("--llm-max-retries", type=int, default=None,
                    help="retries per agent LLM call, e.g. for HTTP 429 on Groq's free tier (upstream: 2)")
    ap.add_argument("--run-id", default=None, help="reuse to resume a run")
    args = ap.parse_args()

    # The backend is part of the run id: results from different agent models are
    # separate experiment series and must never be pooled (SPEC §7.3).
    variant = "v0" if args.retriever == "minilm" else f"v2{args.retriever}"
    variant += "fix" if args.fix_tool_schema else ""
    variant += "" if args.top_k_tools == 128 else f"k{args.top_k_tools}"
    variant += "rt" if args.refresh_tools else ""
    variant += "v5" if args.evidence_answer else ""
    variant += "sh" if args.short_history else ""
    variant += "v6" if args.policy_guard else ""
    run_id = args.run_id or f"{datetime.now():%Y%m%d-%H%M}-{variant}-{args.agent_backend}-{args.split}"
    run_dir = RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    env = subprocess_env(agent_backend=args.agent_backend)
    args.model = args.model or DEFAULT_MODELS[args.agent_backend]

    config = {
        "run_id": run_id,
        "variant": ("V0 upstream LangGraphReActAgent" if args.retriever == "minilm"
                    else f"V2 upstream LangGraphReActAgent + {args.retriever} tool shortlist")
                   + (" + tool-schema fix" if args.fix_tool_schema else "")
                   + (" + tool refresh" if args.refresh_tools else "")
                   + (" + V5 evidence-only answer" if args.evidence_answer else "")
                   + (" + short history" if args.short_history else "")
                   + (" + V6 policy guard" if args.policy_guard else "")
                   + ("" if args.top_k_tools == 128 else f" (top-k-tools={args.top_k_tools})"),
        "split": args.split,
        "caps": args.caps,
        "max_per_domain": args.max_per_domain,
        "agent_backend": args.agent_backend,
        "provider": args.provider,
        "model": args.model,
        "base_url": env["OPENAI_BASE_URL"],
        "top_k_tools": args.top_k_tools,
        "retriever": args.retriever,
        "fix_tool_schema": args.fix_tool_schema,
        "refresh_tools": args.refresh_tools,
        "evidence_answer": args.evidence_answer,
        "short_history": args.short_history,
        "policy_guard": args.policy_guard,
        "max_iterations": args.max_iterations,
        "llm_max_retries": args.llm_max_retries or 2,
        "temperature": 0.0,
        "git_sha": git_sha(REPO_ROOT),
        "upstream_sha": git_sha(UPSTREAM),
        "started": datetime.now().isoformat(timespec="seconds"),
        "capabilities": {},
    }

    for cap_id in args.caps:
        cap_dir, _ = CAPABILITIES[cap_id]
        data_dir = run_dir / "data" / cap_dir
        out_dir = run_dir / "output" / cap_dir
        domains = materialize_split(args.split, cap_id, data_dir, args.max_per_domain)
        if not domains:
            print(f"[cap {cap_id}] no items in split '{args.split}', skipping")
            continue
        patches = []
        if args.llm_max_retries is not None:
            patches.append(RETRY_PATCH.format(max_retries=args.llm_max_retries))
        if args.retriever != "minilm":
            patches.append(RETRIEVER_PATCH.format(scripts_dir=str(SCRIPTS_DIR), retriever=args.retriever))
        if args.fix_tool_schema:
            patches.append(SCHEMA_PATCH)
        if args.refresh_tools:
            patches.append(REFRESH_PATCH)
        if args.short_history:
            patches.append(HISTORY_PATCH.format(scripts_dir=str(SCRIPTS_DIR)))
        if args.policy_guard:
            patches.append(POLICY_PATCH.format(scripts_dir=str(SCRIPTS_DIR)))
        if args.evidence_answer:
            patches.append(ANSWER_PATCH.format(scripts_dir=str(SCRIPTS_DIR)))
        runner = ["-c", SHIM.format(patches="".join(patches))] if patches else ["benchmark_runner.py"]
        cmd = [
            sys.executable, *runner,
            "--capability_id", str(cap_id),
            "--output", str(out_dir),
            "--provider", args.provider,
            "--model", args.model,
            "--top-k-tools", str(args.top_k_tools),
        ]
        if args.max_iterations:
            cmd += ["--max-iterations", str(args.max_iterations)]
        print(f"[cap {cap_id}] {len(domains)} domain(s): {domains}")
        start = time.perf_counter()
        proc = subprocess.run(cmd, cwd=UPSTREAM, env={**env, f"CAPABILITY_{cap_id}_DIR": str(data_dir)})
        config["capabilities"][cap_dir] = {
            "domains": domains,
            "returncode": proc.returncode,
            "wall_seconds": round(time.perf_counter() - start, 1),
            **summarize(out_dir),
        }
        (run_dir / "config.json").write_text(json.dumps(config, indent=1) + "\n")

    config["finished"] = datetime.now().isoformat(timespec="seconds")
    (run_dir / "config.json").write_text(json.dumps(config, indent=1) + "\n")
    print(json.dumps(config["capabilities"], indent=1))
    print(f"run dir: {run_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
