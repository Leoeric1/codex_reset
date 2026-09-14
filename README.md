# Codex Reset Monitor

面向个人使用的 Codex 重置状态页，部署目标为 US 独立 VPS，域名 `codex.leohub.cc`。Python / FastAPI / SQLite / asyncio，单容器运行，与量化系统无代码、网络或数据库依赖。

**本包已完成代码和本地测试；US VPS、Portainer Stack、Cloudflare 路由与 Access、Uptime Kuma 尚未实际配置。** 当前工作环境没有 US SSH 凭据或 Cloudflare 管理会话，也没有 Docker 引擎。不要把交付包完成理解成域名已经上线。验收详情见 `ACCEPTANCE.md`。

## 已实现

- 固定读取 AIHOT 官方 `GET https://aihot.news/api/v1/codex-resets`，正常间隔 300 秒。
- ETag 条件请求。304 更新本地连接成功时间，不篡改源站 `checkedAt`；200 校验完整快照后事务同步。
- 新增、修订、撤回同步，SQLite WAL；仅缓存当前快照，不累计已撤回原文或历史快照副本。
- 错误/损坏/不完整快照保留最后成功缓存；未知 schema/type/status 拒绝整批写入，不会误清空数据。
- 429/503 遵循 Retry-After（秒或 HTTP 日期），其他失败指数退避至 1 小时；等待状态持久化，重启不突破等待期。
- 首页预告、最近全员重置、最近重置卡、历史时间线、类型筛选、中文原帖与原帖链接。历史默认 30 条，可加载更多。
- 明确标注确认帖时间、核验日期、原帖时间。原有 schedule 始终只是预告，未知执行时间保持未知。
- 已过时间区间的预告留在历史；无明确时间且已超过 24 小时的预告不占用首页。此规则仅决定展示位置，不改变上游 announced 状态，也不推断是否已重置。
- 本地 API 仅提供页面需要的整理字段，不提供原始快照、ETag、英文原文导出。
- 通知去重记录预留；V1 无外发渠道、不发送消息。首次历史同步标记 `initial_suppressed`，后续变化标记 `disabled`；没有 `sent_at` 就不算已发送。未来接渠道时不能直接扫旧记录补发。

## US VPS 部署：Portainer Stack

在 US VPS 克隆本仓库并准备镜像：

```bash
git clone https://github.com/Leoeric1/codex_reset.git /opt/codex-reset-monitor
cd /opt/codex-reset-monitor
bash scripts/prepare.sh
```

脚本在当前 VPS 构建 `codex-reset-monitor:1.0.0` 本地镜像，创建独立 bridge 网络 `leohub-monitor`，并将现有 `cloudflared`、`uptime-kuma` 容器附加到该网络。它不会移除这些容器的原有网络，不重启已有服务，不操作防火墙、3x-ui 或量化系统。发现 host/none 网络或容器不存在时，会提示而不会强行重建。实际名字不同时可设置 `CLOUDFLARED_CONTAINER` 和 `KUMA_CONTAINER`。

Portainer 在该 US Docker 环境中选择 **Stacks → Add stack → Web editor**：

1. Stack 名称：`codex-reset-monitor`。
2. 粘贴根目录 `compose.yaml` 的完整内容。
3. 使用本地已构建镜像，关闭重新拉取镜像选项（若界面提供）。
4. Deploy the stack。

不要给服务增加公网端口。Compose 只挂载数据卷 `codex-reset-data:/data`，并加入 `leohub-monitor` 网络。128 MiB 内存、0.25 CPU 是配置上限，实际占用需部署后查看 `docker stats`；本地未做容器资源上限实测。

如果使用 CLI 部署，可运行 `bash scripts/deploy.sh`。**此方式创建的 Compose 项目在 Portainer 中通常属于外部 Stack，管理权限有限；需要完整 Stack 编辑/更新功能时使用上面的 Portainer 创建流程。二选一，勿重复创建同名容器。**

`docker network connect` 在容器重启后保留，但在容器重建后可能丢失。因此需要在 cloudflared 和 Kuma **各自现有 Compose/Stack** 中，将 `leohub-monitor` 声明为 external 网络并附加到对应服务，保留它们原有网络。后续更新这些容器时检查网络仍在；不要用本项目 Compose 替换它们原来的定义。

## Cloudflare：先配置 Access，再发布路由

在现有 Cloudflare One 账户下，创建 Self-hosted Access application：

| 配置 | 值 |
|---|---|
| 应用名称 | Codex Reset Monitor |
| 域名 | `codex.leohub.cc` |
| 路径 | 留空，保护整个主机名 |
| Allow 策略 | 复用你已有邮箱登录策略，仅允许已授权的个人邮箱 |
| 登录方式 | 复用现有邮箱验证登录 |

随后在现有 **leohub** Tunnel 添加 Published application route（部分界面称 Public hostname）：

| 配置 | 值 |
|---|---|
| Subdomain | `codex` |
| Domain | `leohub.cc` |
| Path | 留空 |
| Service type | HTTP |
| Service URL | `codex-reset-monitor:8080` |

由 Tunnel 发布流程关联 DNS。已有同名 DNS 记录时应先核对用途，不覆盖其他服务。容器入口是 HTTP，浏览器到 Cloudflare 使用 HTTPS。Access 必须覆盖 `/api/*`，不要为状态接口或 `/health` 建公开绕过规则。

应用本身依赖 Access 作为登录边界，没有实现独立用户系统。它不开放宿主机端口、不配置 CORS。将 JSON 改成整理字段不等于获得公开转发授权；本服务按个人受保护后台使用。

### 若 cloudflared 使用 host 网络

只有实机检查确认 host 模式后，才在该服务的 Compose 中增加下面的**回环端口**；其余配置保持一致：

```yaml
    ports:
      - "127.0.0.1:18080:8080"
```

Tunnel 服务地址相应改为 `http://127.0.0.1:18080`。若端口已占用，先选择空闲的回环端口再统一更新。不要改成 `0.0.0.0`。bridge 模式的 Kuma 仍通过共享网络访问容器名；host 模式的 Kuma 则使用上述回环地址。

## Uptime Kuma

添加 HTTP(s) 监控：

| 配置 | 值 |
|---|---|
| 名称 | Codex Reset Monitor |
| URL | `http://codex-reset-monitor:8080/health` |
| 检查间隔 | 60 秒 |
| 接受状态码 | 200–299，勿包含 503 |
| 重试次数 | 2 |

`/health` 不仅检查 Web：源站核验或本地连接超过 30 分钟、连续失败达到 3 次、首次尚无数据时返回 HTTP 503。连续失败 6 次页面转红。前 1–2 次失败且数据仍新鲜时保持绿色。正常返回 200。返回字段含 `status`、`source`、`last_sync`、`checked_at`、`data_age_seconds`。

`/live` 专供 Docker 存活检查：AIHOT 故障不改变它，避免因上游异常诱发容器重启。首次启动可短暂处于 degraded，等待第一个快照。若上游核验本身过期，即使连接成功也会保持 degraded，属于预期行为。

## 本地 API

| 路径 | 用途 |
|---|---|
| `GET /api/status` | 健康状态、源站核验/本地连接/下次检查时间，以及最近事件 |
| `GET /api/events` | 分页整理后的时间线；limit 默认 30、最多 100，offset ≥ 0 |
| `GET /api/events?type=reset_credit` | 类型筛选；也支持 `direct_reset` |
| `GET /api/events?status=announced` | 状态筛选；也支持 `confirmed` |
| `GET /api/events/latest` | 最近重置、最近重置卡、当前有效预告 |
| `GET /health` | 数据源与本地同步健康；200 / 503 |
| `GET /live` | 进程存活 |

刷新页面只读取本地 API，绝不触发上游轮询。其他 Agent 通过域名读取时也需使用 Access 认证；本版本未创建或发放服务令牌。首页可点击 AIHOT 和各原帖链接。

## 验收与维护

在 VPS 上运行：

```bash
cd /opt/codex-reset-monitor
bash scripts/verify.sh
docker stats --no-stream codex-reset-monitor
docker logs --tail 30 codex-reset-monitor
```

确认手机浏览器未登录时出现 Access 登录页、授权后展示页面；未登录请求 `/api/status` 同样被保护；Kuma 应显示正常或解释得通的源站 degraded。按顺序核对桌面/手机页面、数据时间、原帖链接、共享网络以及卷挂载，再记录实机验收结果。

更新：保留镜像旧标签用于回退，在 VPS 构建新版本镜像，再于 Portainer 修改 Stack 镜像标签并重新部署。数据卷保留。不要运行 `docker compose down -v`、删除该数据卷或将本地测试数据库上传到 VPS。当前缓存会随上游撤回同步清理，不把它另存为可再分发数据集。容器日志自动限制为 3 个文件、每个 2 MiB。

开发与测试（Linux，Python 3.12）：

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
DB_PATH=/tmp/codex-reset-dev.db .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8080 --workers 1
```

依赖版本已锁定在 `requirements.lock`。单 Worker 是强制约束，数据库旁的文件锁阻止同卷多进程重复轮询。跨容器共享同一卷运行多个副本不受支持。

## 依据

- [AIHOT OpenAPI v1](https://aihot.news/openapi-v1.json)：实际核对了 codexResets 定义、空值、确认时间含义、快照替换和轮询约定。
- [AIHOT 使用规则](https://aihot.news/terms)：个人使用与缓存/再分发边界。
- [Cloudflare 自托管应用](https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/self-hosted-public-app/) 与 [Tunnel 发布应用](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/routing-to-tunnel/)。
- [Portainer 创建 Stack](https://docs.portainer.io/user/docker/stacks/add)。
