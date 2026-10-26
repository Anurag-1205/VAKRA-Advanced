"""Score a run with the unmodified upstream evaluator (third_party/vakra/evaluator).

For each capability in runs/<run_id>/output/, call
    evaluator/evaluator.py --capability_name <registry name>
        --gt_root runs/<run_id>/data/<cap_dir>/output      (split ground truth)
        --pred_root runs/<run_id>/output/<cap_dir>
        --output runs/<run_id>/eval/<cap_dir>.json
with JUDGE_BACKEND=groq + API_KEY (upstream judge.py ChatGroq, openai/gpt-oss-120b).
The evaluator replays both predicted and ground-truth tool calls over MCP, so the
capability containers must be running. It resumes per domain if re-run.

Usage:
    python scripts/evaluate.py --run-id 20261027-1200-v0-smoke [--caps 2 3]
"""
import argparse
import json
import subprocess
import sys

from common import CAPABILITIES, RUNS_DIR, UPSTREAM, subprocess_env


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--caps", type=int, nargs="*", default=None, choices=sorted(CAPABILITIES))
    ap.add_argument("--policy-judge-path", default=None, help="private PolicyJudge file, if granted")
    args = ap.parse_args()

    run_dir = RUNS_DIR / args.run_id
    env = subprocess_env()
    summary = {}
    for cap_id, (cap_dir, registry_name) in CAPABILITIES.items():
        if args.caps and cap_id not in args.caps:
            continue
        gt_dir = run_dir / "data" / cap_dir / "output"
        pred_dir = run_dir / "output" / cap_dir
        if not pred_dir.exists():
            continue
        # Only score domains that produced predictions (a run may stop early).
        domains = sorted(p.stem for p in pred_dir.glob("*.json") if not p.stem.endswith("_tools"))
        if not domains:
            continue
        out = run_dir / "eval" / f"{cap_dir}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            sys.executable, "evaluator/evaluator.py",
            "--capability_name", registry_name,
            "--gt_root", str(gt_dir),
            "--pred_root", str(pred_dir),
            "--output", str(out),
            "--domains", *domains,
        ]
        if args.policy_judge_path:
            cmd += ["--policy-judge-path", args.policy_judge_path]
        print(f"[cap {cap_id}] evaluating {len(domains)} domain(s)")
        proc = subprocess.run(cmd, cwd=UPSTREAM, env=env)
        if proc.returncode != 0 or not out.exists():
            summary[cap_dir] = {"error": f"evaluator exited with {proc.returncode}"}
            continue
        res = json.loads(out.read_text())["summary"]
        summary[cap_dir] = {
            "n_samples": res.get("n_samples"),
            "n_correct": res.get("n_correct"),
            "mean_dialogue_score": res.get("mean_dialogue_score"),
            "n_missing_predictions": res.get("n_missing_predictions"),
        }

    scores = [s["mean_dialogue_score"] for s in summary.values() if s.get("mean_dialogue_score") is not None]
    summary["macro_avg_over_scored_caps"] = round(sum(scores) / len(scores), 4) if scores else None
    (run_dir / "eval").mkdir(parents=True, exist_ok=True)
    (run_dir / "eval" / "summary.json").write_text(json.dumps(summary, indent=1) + "\n")
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
