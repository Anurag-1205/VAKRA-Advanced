"""Shared paths, env handling and split materialization for our scripts.

Upstream (third_party/vakra) is never modified: we run its runner/evaluator as
subprocesses and point them at split-specific copies of the data through the
env vars they already read (CAPABILITY_<N>_DIR, API_KEY, JUDGE_BACKEND, ...).
"""
import json
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = REPO_ROOT / "third_party" / "vakra"
TRAIN_DIR = UPSTREAM / "data" / "train"
SPLITS_DIR = REPO_ROOT / "splits"
RUNS_DIR = REPO_ROOT / "runs"

GROQ_OPENAI_BASE_URL = "https://api.groq.com/openai/v1"

# capability id -> (data dir name, evaluator registry name); names verified in
# upstream benchmark/runner_helpers.py and evaluator/evaluator.py.
CAPABILITIES = {
    1: ("capability_1_bi_apis", "capability_bi_apis"),
    2: ("capability_2_dashboard_apis", "capability_dashboard_apis"),
    3: ("capability_3_multihop_reasoning", "capability_multihop_reasoning"),
    4: ("capability_4_multiturn", "capability_multiturn"),
}
SPLIT_NAMES = ("smoke", "dev-seen", "dev-heldout", "train-rest")


def load_dotenv(path: Path = REPO_ROOT / ".env") -> dict:
    env = {}
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.removeprefix("export ").split("=", 1)
            env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def subprocess_env(extra: dict | None = None) -> dict:
    """Environment for upstream subprocesses.

    Agent: upstream create_llm(provider="openai") builds langchain ChatOpenAI,
    which reads OPENAI_API_KEY and OPENAI_BASE_URL; we point both at Groq.
    Judge: upstream evaluator/judge.py ChatGroq reads API_KEY and is selected
    with JUDGE_BACKEND=groq (default backend is IBM-internal RITS).
    Values only live in the child process env; nothing is written to disk.
    """
    env = dict(os.environ)
    dot = load_dotenv()
    for key, value in dot.items():
        env.setdefault(key, value)
    if not env.get("API_KEY"):
        raise SystemExit("API_KEY missing: add it to .env (see .env.example)")
    env["OPENAI_API_KEY"] = env["API_KEY"]
    env["OPENAI_BASE_URL"] = env.get("OPENAI_BASE_URL") or GROQ_OPENAI_BASE_URL
    env["JUDGE_BACKEND"] = env.get("JUDGE_BACKEND") or "groq"
    env["PYTHONPATH"] = os.pathsep.join(p for p in (str(UPSTREAM), env.get("PYTHONPATH")) if p)
    env.update(extra or {})
    return env


def load_split(name: str) -> dict[str, list[str]]:
    """Return {capability_dir: [uuid, ...]} for a committed split."""
    return json.loads((SPLITS_DIR / f"{name}.json").read_text())


def materialize_split(name: str, cap_id: int, dest: Path, max_per_domain: int | None = None) -> list[str]:
    """Write <dest>/{input,output}/<domain>.json holding only the split's items.

    Returns the domains written. `input/` feeds upstream benchmark_runner.py via
    CAPABILITY_<N>_DIR; `output/` is the ground truth for evaluator.py --gt_root.
    """
    cap_dir, _ = CAPABILITIES[cap_id]
    keep = set(load_split(name).get(cap_dir, []))
    domains = []
    for kind in ("input", "output"):
        (dest / kind).mkdir(parents=True, exist_ok=True)
    for in_file in sorted((TRAIN_DIR / cap_dir / "input").glob("*.json")):
        items = [x for x in json.loads(in_file.read_text()) if x["uuid"] in keep]
        if max_per_domain:
            items = items[:max_per_domain]
        if not items:
            continue
        uuids = {x["uuid"] for x in items}
        gt = json.loads((TRAIN_DIR / cap_dir / "output" / in_file.name).read_text())
        gt = [x for x in gt if x["uuid"] in uuids]
        (dest / "input" / in_file.name).write_text(json.dumps(items, indent=1))
        (dest / "output" / in_file.name).write_text(json.dumps(gt, indent=1))
        domains.append(in_file.stem)
    return domains
