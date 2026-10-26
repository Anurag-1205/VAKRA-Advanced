"""Connect to running capability containers via upstream's MCP client and report,
per domain: tool count, upstream checksum verification, and the token size of the
tool definitions an agent would send (OpenAI tool format, o200k tokenizer).

The token size matters for Groq's free tier (8,000 tokens/minute): one request
carrying more tool schema than that cannot succeed at all.

Usage:
    python scripts/inspect_tools.py --cap 2 --domains hockey authors
    python scripts/inspect_tools.py --cap 1 --domains authors --json out.json
"""
import argparse
import asyncio
import json
import sys

import tiktoken
from langchain_core.utils.function_calling import convert_to_openai_tool

from common import UPSTREAM

sys.path.insert(0, str(UPSTREAM))
from agents.mcp_tool_wrapper import MCPToolWrapper  # noqa: E402
from benchmark.mcp_client import create_client_and_connect, load_mcp_config  # noqa: E402
from environment.tool_checksums import verify_checksum  # noqa: E402

ENC = tiktoken.get_encoding("o200k_base")


async def inspect(cap_id: int, domain: str, top_k: int) -> dict:
    cfg = load_mcp_config(str(UPSTREAM / "benchmark" / "mcp_connection_config.yaml"))[cap_id]
    async with create_client_and_connect(cfg, domain) as session:
        raw = (await session.list_tools()).tools
        try:
            verify_checksum(cap_id, domain, raw)
            checksum = "ok"
        except Exception as e:  # report, don't abort the survey
            checksum = f"FAILED: {e}"[:120]
        tools = await MCPToolWrapper(session).get_tools()
    sizes = [len(ENC.encode(json.dumps(convert_to_openai_tool(t)))) for t in tools]
    return {
        "capability": cap_id,
        "domain": domain,
        "n_tools": len(tools),
        "checksum": checksum,
        "schema_tokens_all": sum(sizes),
        f"schema_tokens_top{top_k}_upper_bound": sum(sorted(sizes, reverse=True)[:top_k]),
        "schema_tokens_mean_per_tool": round(sum(sizes) / max(len(sizes), 1)),
    }


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cap", type=int, required=True, choices=[1, 2, 3, 4])
    ap.add_argument("--domains", nargs="+", required=True)
    ap.add_argument("--top-k", type=int, default=128, help="upstream --top-k-tools default")
    ap.add_argument("--json", help="also write results to this file")
    args = ap.parse_args()

    rows = [await inspect(args.cap, d, args.top_k) for d in args.domains]
    for r in rows:
        print(json.dumps(r))
    if args.json:
        with open(args.json, "w") as f:
            json.dump(rows, f, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
