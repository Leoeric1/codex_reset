#!/usr/bin/env bash
# CLI alternative. For full Portainer Stack control, use prepare.sh + its Stack UI.
set -euo pipefail
cd "$(dirname "$0")/.."
bash scripts/prepare.sh
docker compose -p codex-reset-monitor up -d --pull never
docker compose -p codex-reset-monitor ps
echo '容器已启动。运行 bash scripts/verify.sh 验收内部服务；域名/Access 仍需接入。'
