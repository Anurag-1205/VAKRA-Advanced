"""Selective, public-only download of the VAKRA training data.

Upstream `make download` pulls everything (~35 GB) and first tries the gated test
repo whenever a Hugging Face token is found. This script instead:
  * only ever touches the PUBLIC repo `ibm-research/VAKRA`, anonymously (token=False);
  * downloads the small train JSON files, plus databases only for chosen domains;
  * writes into third_party/vakra/data/ using upstream's layout, so docker-compose
    mounts and the upstream runner/evaluator work unchanged.

Usage:
    python scripts/download_data.py --train                      # train inputs/outputs only
    python scripts/download_data.py --domains hockey superhero   # + those databases
    python scripts/download_data.py --domains-from splits/domains_needed.txt
    python scripts/download_data.py --indexed-documents          # Cap 4 ChromaDB (~7.8 GB)
    python scripts/download_data.py --list-db-sizes              # print per-domain DB sizes
"""
import argparse
import collections
import sys
from pathlib import Path

from huggingface_hub import HfApi, hf_hub_download
from huggingface_hub.hf_api import RepoFile

PUBLIC_REPO = "ibm-research/VAKRA"
REPO_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "third_party" / "vakra" / "data"


def list_files(api: HfApi) -> list[RepoFile]:
    return [
        f
        for f in api.list_repo_tree(PUBLIC_REPO, repo_type="dataset", recursive=True, token=False)
        if isinstance(f, RepoFile)
    ]


def size_of(f: RepoFile) -> int:
    return f.lfs.size if f.lfs else f.size


def db_sizes(files: list[RepoFile]) -> dict[str, int]:
    sizes = collections.Counter()
    for f in files:
        parts = f.path.split("/")
        if parts[0] == "databases" and len(parts) > 2:
            sizes[parts[1]] += size_of(f)
    return dict(sizes)


def wanted(path: str, args, domains: set[str]) -> bool:
    parts = path.split("/")
    if parts[0] == "train":
        return args.train
    if parts[0] == "databases":
        # Top-level helper files (domains.json, ...) are tiny; always keep them.
        return len(parts) == 2 or parts[1] in domains
    if parts[0] == "indexed_documents":
        return args.indexed_documents
    return False


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--train", action="store_true", help="Download train/ inputs and outputs")
    ap.add_argument("--domains", nargs="*", default=[], help="Domains whose databases to download")
    ap.add_argument("--domains-from", type=Path, help="File with one domain name per line")
    ap.add_argument("--indexed-documents", action="store_true", help="Download Cap 4 ChromaDB index")
    ap.add_argument("--list-db-sizes", action="store_true", help="Print per-domain database sizes and exit")
    ap.add_argument("--dry-run", action="store_true", help="Show what would be downloaded")
    args = ap.parse_args()

    api = HfApi()
    files = list_files(api)

    if args.list_db_sizes:
        for name, size in sorted(db_sizes(files).items(), key=lambda kv: -kv[1]):
            print(f"{size / 1e9:7.2f} GB  {name}")
        return 0

    domains = set(args.domains)
    if args.domains_from:
        domains |= {l.strip() for l in args.domains_from.read_text().splitlines() if l.strip()}
    unknown = domains - set(db_sizes(files))
    if unknown:
        print(f"Unknown database domains: {sorted(unknown)}")
        return 1

    todo = [f for f in files if wanted(f.path, args, domains)]
    todo = [f for f in todo if not (DATA_DIR / f.path).exists() or (DATA_DIR / f.path).stat().st_size != size_of(f)]
    total = sum(size_of(f) for f in todo)
    print(f"{len(todo)} file(s) to download, {total / 1e9:.2f} GB -> {DATA_DIR}")
    if args.dry_run or not todo:
        return 0

    for i, f in enumerate(todo, 1):
        hf_hub_download(PUBLIC_REPO, f.path, repo_type="dataset", local_dir=DATA_DIR, token=False)
        print(f"  [{i}/{len(todo)}] {f.path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
