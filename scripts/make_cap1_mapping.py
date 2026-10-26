"""Build a Cap 1 tool-universe mapping that also covers TRAIN-split uuids.

Cap 1 items start with get_data(tool_universe_id=<uuid>); the MCP server resolves
the uuid via environment/configs/mcp_tool_universe_id_mapping.yaml. Upstream ships
that file generated from the gated TEST split only, so every train uuid fails with
"Unknown universe ID". This script keeps all upstream entries and adds train entries
built with upstream's own generator rules (imported, not copied), then writes
generated/configs/ for scripts/containers.sh to mount instead of the upstream dir:

    python scripts/make_cap1_mapping.py                  # held-out domains (dev splits)
    python scripts/make_cap1_mapping.py --domains hockey world
    CONFIGS_DIR=generated/configs scripts/containers.sh start 1

Output is derived from CC BY-NC-SA data and is gitignored.
"""
import argparse
import importlib.util
import json
import shutil
import sys

import yaml

from common import REPO_ROOT, SPLITS_DIR, TRAIN_DIR, UPSTREAM

CAP_DIR = "capability_1_bi_apis"
UPSTREAM_CONFIGS = UPSTREAM / "environment" / "configs"
OUT_DIR = REPO_ROOT / "generated" / "configs"
MAPPING = "mcp_tool_universe_id_mapping.yaml"


def upstream_generator():
    # Importing would otherwise drop a __pycache__/ into the upstream submodule.
    sys.dont_write_bytecode = True
    path = UPSTREAM_CONFIGS / "generate_task_1_tool_universe_mapping.py"
    spec = importlib.util.spec_from_file_location("upstream_cap1_mapping", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def entry_for(record: dict, gen) -> dict | None:
    """Same rules as upstream generate_mapping(); also accepts the list-shaped
    `sequence` seen in sample_data (upstream assumes a dict)."""
    turns = record.get("output") or []
    if not turns:
        return None
    seq = turns[0].get("sequence") or {}
    if isinstance(seq, list):
        seq = seq[0] if seq else {}
    calls = seq.get("tool_call") or []
    init = next((c for c in calls if c["name"] == "initialize_active_data"), None)
    if init is None:
        return None
    server_type = "slot_filling"
    for call in calls:
        if call["name"] in gen.SELECTION_ONLY_TOOLS:
            server_type = "selection"
            break
        if call["name"] in gen.SLOT_FILLING_ONLY_TOOLS:
            break
    return {
        "domain": record["domain"],
        "server_type": server_type,
        "init_args": init["arguments"],
        "query": turns[0]["query"],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--domains", nargs="*", help="train domains to add (default: held-out domains)")
    args = ap.parse_args()

    domains = args.domains or json.loads((SPLITS_DIR / "manifest.json").read_text())["heldout_domains"]
    gen = upstream_generator()
    mapping = yaml.safe_load((UPSTREAM_CONFIGS / MAPPING).read_text())
    n_upstream, added, skipped = len(mapping), 0, 0

    for domain in sorted(domains):
        path = TRAIN_DIR / CAP_DIR / "output" / f"{domain}.json"
        if not path.exists():
            continue  # domain has no Cap 1 items
        for record in json.loads(path.read_text()):
            if record["uuid"] in mapping:
                continue
            entry = entry_for(record, gen)
            if entry is None:
                skipped += 1
                continue
            mapping[record["uuid"]] = entry
            added += 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    # Keep every other upstream config file identical; only the mapping differs.
    for f in UPSTREAM_CONFIGS.iterdir():
        if f.is_file() and f.name != MAPPING:
            shutil.copy2(f, OUT_DIR / f.name)
    with open(OUT_DIR / MAPPING, "w") as fh:
        yaml.dump(mapping, fh, default_flow_style=False, allow_unicode=True)
    print(f"upstream entries: {n_upstream}; added train entries: {added}; skipped (no init call): {skipped}")
    print(f"wrote {OUT_DIR / MAPPING}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
