"""Minimal Groq connectivity + tool-calling check (stdlib only).

Reads API_KEY from the repo-root .env (or the environment), never prints it.
Reports: model availability, whether a tool call is returned, token usage,
and Groq's rate-limit headers (to confirm free-tier limits before any run).

Usage:
    python3 scripts/check_llm.py [--model openai/gpt-oss-120b]
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
REPO_ROOT = Path(__file__).resolve().parents[1]

SAMPLE_TOOL = {
    "type": "function",
    "function": {
        "name": "get_team_count",
        "description": "Return the number of teams that played in a given season.",
        "parameters": {
            "type": "object",
            "properties": {"season": {"type": "integer", "description": "Season year"}},
            "required": ["season"],
        },
    },
}


def load_env(path: Path) -> dict:
    """Parse KEY=VALUE lines; ignores comments and blank lines."""
    env = {}
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.removeprefix("export ").split("=", 1)
            env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def request(method: str, url: str, api_key: str, body: dict | None = None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {api_key}")
    req.add_header("Content-Type", "application/json")
    # Groq sits behind Cloudflare, which rejects urllib's default User-Agent.
    req.add_header("User-Agent", "vakra-advanced-check/0.1")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, dict(resp.headers), json.loads(resp.read())
    except urllib.error.HTTPError as e:
        payload = e.read().decode(errors="replace")[:500]
        return e.code, dict(e.headers), {"error": payload}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="openai/gpt-oss-120b")
    args = ap.parse_args()

    api_key = os.environ.get("API_KEY") or load_env(REPO_ROOT / ".env").get("API_KEY")
    if not api_key:
        print("FAIL: API_KEY not found in environment or .env")
        return 1

    status, _, models = request("GET", f"{GROQ_BASE_URL}/models", api_key)
    if status != 200:
        print(f"FAIL: /models returned HTTP {status}: {models.get('error')}")
        return 1
    ids = sorted(m["id"] for m in models.get("data", []))
    print(f"models endpoint: OK ({len(ids)} models); {args.model} available: {args.model in ids}")

    body = {
        "model": args.model,
        "temperature": 0,
        "max_completion_tokens": 300,
        "messages": [
            {"role": "user", "content": "How many teams played in the 2018 season? Use the tool."}
        ],
        "tools": [SAMPLE_TOOL],
    }
    status, headers, resp = request("POST", f"{GROQ_BASE_URL}/chat/completions", api_key, body)
    if status != 200:
        print(f"FAIL: chat/completions returned HTTP {status}: {resp.get('error')}")
        return 1

    msg = resp["choices"][0]["message"]
    calls = msg.get("tool_calls") or []
    print(f"chat/completions: OK; finish_reason={resp['choices'][0].get('finish_reason')}")
    for c in calls:
        print(f"  tool_call: {c['function']['name']}({c['function']['arguments']})")
    print(f"tool calling supported: {bool(calls)}")
    print(f"usage: {resp.get('usage')}")

    print("rate-limit headers:")
    for k, v in sorted(headers.items()):
        if k.lower().startswith("x-ratelimit"):
            print(f"  {k}: {v}")
    return 0 if calls else 2


if __name__ == "__main__":
    sys.exit(main())
