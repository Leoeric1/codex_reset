#!/usr/bin/env bash
# Build on the VPS before deploying compose.yaml through Portainer.
set -euo pipefail
cd "$(dirname "$0")/.."
command -v docker >/dev/null
docker info >/dev/null
docker compose version
docker build --pull --tag codex-reset-monitor:1.0.0 .
if ! docker network inspect leohub-monitor >/dev/null 2>&1; then
  docker network create leohub-monitor
fi
for monitor_peer in "${CLOUDFLARED_CONTAINER:-cloudflared}" "${KUMA_CONTAINER:-uptime-kuma}"; do
  if ! docker container inspect "$monitor_peer" >/dev/null 2>&1; then
    echo "未找到容器 $monitor_peer；稍后把实际容器接入 leohub-monitor 网络。"
    continue
  fi
  monitor_mode=$(docker inspect --format '{{.HostConfig.NetworkMode}}' "$monitor_peer")
  if [ "$monitor_mode" = host ] || [ "$monitor_mode" = none ]; then
    echo "$monitor_peer 使用 $monitor_mode 网络；请按 README 的 host 网络说明接入。"
    continue
  fi
  monitor_link=$(docker inspect --format '{{if index .NetworkSettings.Networks "leohub-monitor"}}yes{{end}}' "$monitor_peer")
  if [ "$monitor_link" != yes ]; then
    docker network connect leohub-monitor "$monitor_peer"
  fi
done
echo '准备完成。Portainer 新建 codex-reset-monitor Stack，粘贴 compose.yaml；镜像拉取选项关闭。'
echo 'Cloudflare Access 保护整个 codex.leohub.cc，再添加 Tunnel 路由。'
