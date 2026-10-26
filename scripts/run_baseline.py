"""Run the unmodified upstream V0 baseline (LangGraphReActAgent) on one of our splits.

For each capability: copy the split's items into runs/<run_id>/data/<cap_dir>/,
point upstream's CAPABILITY_<N>_DIR at it, and invoke third_party/vakra/benchmark_runner.py.
Predictions land in runs/<run_id>/output/<cap_dir>/<domain>.json (official format).

Usage:
    python scripts/run_baseline.py --split smoke --caps 1 2 3
    python scripts/run_baseline.py --split dev-heldout --caps 2 --max-per-domain 3
"""
import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from common import AGENT_BACKENDS, CAPABILITIES, REPO_ROOT, RUNS_DIR, UPSTREAM, materialize_split, subprocess_env

DEFAULT_MODELS = {"groq": "openai/gpt-oss-120b", "gemini": "gemini-3.8-flash"}


def git_sha(path: Path) -> str:
    out = subprocess.run(["git", "-C", str(path), "rev-parse", "--short", "HEAD"], capture_output=True, text=True)
    return out.stdout.strip() or "unknown"


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
    ap.add_argument("--max-iterations", type=int, default=None)
    ap.add_argument("--run-id", default=None, help="reuse to resume a run")
    args = ap.parse_args()

    # The backend is part of the run id: results from different agent models are
    # separate experiment series and must never be pooled (SPEC §7.3).
    run_id = args.run_id or f"{datetime.now():%Y%m%d-%H%M}-v0-{args.agent_backend}-{args.split}"
    run_dir = RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    env = subprocess_env(agent_backend=args.agent_backend)
    args.model = args.model or DEFAULT_MODELS[args.agent_backend]

    config = {
        "run_id": run_id,
        "variant": "V0 upstream LangGraphReActAgent",
        "split": args.split,
        "caps": args.caps,
        "max_per_domain": args.max_per_domain,
        "agent_backend": args.agent_backend,
        "provider": args.provider,
        "model": args.model,
        "base_url": env["OPENAI_BASE_URL"],
        "top_k_tools": args.top_k_tools,
        "max_iterations": args.max_iterations,
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
        cmd = [
            sys.executable, "benchmark_runner.py",
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
