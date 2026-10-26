#!/usr/bin/env bash
# Build the upstream benchmark image (tag: benchmark_environ) with CPU-only PyTorch.
#
# Reads third_party/vakra/docker/Dockerfile.unified unchanged and injects, after the
# apt-get step:
#   * pip network settings (longer timeout, more retries) for slow/unstable links;
#     a single read timeout otherwise fails the whole multi-package install layer;
#   * a layer that installs torch from the PyTorch CPU index. pip then treats torch
#     as satisfied and skips the ~3 GB of CUDA wheels sentence-transformers would
#     otherwise pull from PyPI. The containers get no GPU (no --gpus in compose),
#     so CUDA torch would run on CPU anyway; server code and behaviour are identical.
#
# Usage: scripts/build_image.sh            (equivalent of upstream `make build`)
#        UPSTREAM_BUILD=1 scripts/build_image.sh   (plain upstream Dockerfile)
set -euo pipefail

UPSTREAM="$(cd "$(dirname "$0")/../third_party/vakra" && pwd)"
DOCKERFILE="$UPSTREAM/docker/Dockerfile.unified"
PIP_ENV='ENV PIP_DEFAULT_TIMEOUT=120 PIP_RETRIES=10'
TORCH_LAYER='RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu'

if [[ "${UPSTREAM_BUILD:-0}" == 1 ]]; then
  exec docker build -t benchmark_environ -f "$DOCKERFILE" "$UPSTREAM"
fi

# Insert both right after the (cacheable) system-dependencies RUN block,
# i.e. before the first COPY of requirements files.
patched="$(awk -v env="$PIP_ENV" -v layer="$TORCH_LAYER" '
  !done && /^COPY environment\/m3\/rest\/requirements.txt/ { print env; print layer; print ""; done=1 }
  { print }
  END { if (!done) exit 1 }
' "$DOCKERFILE")" || { echo "Dockerfile layout changed; cannot place torch layer" >&2; exit 1; }

docker build -t benchmark_environ -f - "$UPSTREAM" <<< "$patched"
