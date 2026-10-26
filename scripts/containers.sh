#!/usr/bin/env bash
# Start/stop the VAKRA capability containers with plain `docker run`.
#
# Mirrors third_party/vakra/docker-compose.yml (image, container names, env,
# mounts, Cap 4 mem_limit) for machines without the Compose v2 plugin: that file
# uses the top-level `name:` key, which docker-compose v1.29 rejects. The runner
# and evaluator reach containers via `docker exec <name>`, so names must match
# benchmark/mcp_connection_config.yaml. Prefer `docker compose up -d` when available.
#
# Usage: scripts/containers.sh start [1 2 3 4] | stop [..] | status
#   CONFIGS_DIR=generated/configs scripts/containers.sh start 1
#     mounts an alternative environment/configs (see scripts/make_cap1_mapping.py)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
UPSTREAM="$ROOT/third_party/vakra"
CONFIGS_DIR="$(cd "$ROOT" && realpath "${CONFIGS_DIR:-third_party/vakra/environment/configs}")"
IMAGE=benchmark_environ
declare -A NAMES=(
  [1]=capability_1_bi_apis
  [2]=capability_2_dashboard_apis
  [3]=capability_3_multihop_reasoning
  [4]=capability_4_multiturn
)

cmd="${1:-status}"; shift || true
caps=("${@:-1 2 3 4}")
read -r -a caps <<< "${caps[*]}"

case "$cmd" in
  start)
    for c in "${caps[@]}"; do
      name="${NAMES[$c]}"
      docker rm -f "$name" >/dev/null 2>&1 || true
      args=(-d --name "$name" -e MCP_VERIFY_CHECKSUMS=1
            -v "$UPSTREAM/data/databases:/app/db:ro"
            -v "$CONFIGS_DIR:/app/environment/configs:ro")
      if [[ "$c" == 4 ]]; then
        mkdir -p "$UPSTREAM/data/indexed_documents" "$UPSTREAM/data/queries"
        args+=(--memory 8g
               -v "$UPSTREAM/data/indexed_documents:/app/retrievers/chroma_data"
               -v "$UPSTREAM/data/queries:/app/retrievers/queries:ro")
      fi
      docker run "${args[@]}" "$IMAGE" >/dev/null
      echo "started $name"
    done
    ;;
  stop)
    for c in "${caps[@]}"; do docker rm -f "${NAMES[$c]}" >/dev/null 2>&1 && echo "stopped ${NAMES[$c]}" || true; done
    ;;
  status)
    docker ps -a --filter "name=capability_" --format 'table {{.Names}}\t{{.Status}}'
    ;;
  *)
    echo "usage: $0 start|stop [caps...] | status" >&2; exit 2
    ;;
esac
