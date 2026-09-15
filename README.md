# Codex Reset Monitor

面向个人使用的 Codex 重置状态页，部署目标为 US 独立 VPS，域名 `codex.leohub.cc`。Python / FastAPI / SQLite / asyncio，单容器运行，与量化系统无代码、网络或数据库依赖。

**当前应用版本 1.1.0。** 最初的 V1 本地验收记录保留在 `ACCEPTANCE.md`；其中“尚未部署”是当时状态，不代表当前 VPS 状态。仓库现提供 GitHub Actions 镜像构建，成功后在 Portainer 手动更新容器；不会自动连接 VPS、调用 Portainer 或修改 Cloudflare。代码提交不等于实例升级。

## 已实现

- 固定读取 AIHOT 官方 `GET https://aihot.news/api/v1/codex-resets`，正常间隔 300 秒。
- ETag 条件请求。304 更新本地连接成功时间，不篡改源站 `checkedAt`；200 校验完整快照后事务同步。
- 新增、修订、撤回同步，SQLite WAL；仅缓存当前快照，不累计已撤回原文或历史快照副本。
- 错误/损坏/不完整快照保留最后成功缓存；未知 schema/type/status 拒绝整批写入，不会误清空数据。
- 429/503 遵循 Retry-After（秒或 HTTP 日期），其他失败指数退避至 1 小时；等待状态持久化，重启不突破等待期。
- 首页预告、最近全员重置、最近重置卡、历史时间线、类型筛选、中文原帖与原帖链接。前端历史默认 10 条，可加载更多；原 API 默认 limit=30 保持兼容。
- 明确标注确认帖时间、核验日期、原帖时间。原有 schedule 始终只是预告，未知执行时间保持未知。
- 已过时间区间的预告留在历史；无明确时间且已超过 24 小时的预告不占用首页。此规则仅决定展示位置，不改变上游 announced 状态，也不推断是否已重置。
- 本地 API 仅提供页面需要的整理字段，不提供原始快照、ETag、英文原文导出。
- 通知去重记录预留；V1 无外发渠道、不发送消息。首次历史同步标记 `initial_suppressed`，后续变化标记 `disabled`；没有 `sent_at` 就不算已发送。未来接渠道时不能直接扫旧记录补发。

## US VPS 更新：GitHub 构建 + Portainer 一键更新（推荐）

`.github/workflows/publish-container.yml` 在 `main` 提交后自动运行，也支持 Actions 页手动运行。先校验文件、运行 Python 行为测试，再在 GitHub runner 构建并用无网络、非 root、只读文件系统及 0.25 CPU / 128 MiB 条件检查 amd64 镜像，最后发布 amd64 / arm64 镜像。ARM 镜像通过构建，运行检查在 amd64 执行。无需在 VPS 安装构建工具，也无需在仓库保存 PAT。

- 日常更新镜像：`ghcr.io/leoeric1/codex-reset-monitor:main`，指向最近成功发布的版本。
- 提交定位镜像：`ghcr.io/leoeric1/codex-reset-monitor:sha-<完整提交 SHA>`。需要固定构建产物时使用发布结果中的 digest。
- 发布权限只用临时 `GITHUB_TOKEN` 的 `contents:read` / `packages:write`。首次发布默认私有，不自动改变仓库或镜像可见性。
- Actions 成功只表示镜像发布成功，VPS 更新仍由你在 Portainer 点击执行。失败时保留现有运行容器，修复构建后再更新。

### 首次设置：保留当前可编辑的 codex-reset Stack

1. 打开仓库 **Actions → Publish container**，等待对应最新提交显示绿色成功。如果 Actions 被账户策略关闭，先在 GitHub 启用；不要提前使用尚未发布的镜像。
2. 私有镜像需要在 Portainer **Registries → Add registry → Custom registry** 配置：名称 `GitHub GHCR`，Registry URL `ghcr.io`，Authentication 开启，Username `Leoeric1`，Password 填有该镜像读取权限的 GitHub **PAT (classic)**，仅需 `read:packages`。凭据只输入 Portainer，不贴进 Compose、仓库或聊天。已有适用的 GHCR registry 可复用；Git 仓库的读取凭据与镜像 registry 凭据不是同一个设置。
3. 打开现有 **Stacks → codex-reset → Editor**，只修改两行：

   ```yaml
   image: ghcr.io/leoeric1/codex-reset-monitor:main
   pull_policy: always
   ```

   原有 `127.0.0.1:18080:8080`、`codex-reset-data:/data`、`leohub-monitor` 及所有资源限制均保持不变。外发 provider 缺省仍为 disabled，可明确增加 `NOTIFICATION_PROVIDER: disabled`。
4. 点击 **Update the stack**，若弹窗提供 **Re-pull image / Pull latest image**，开启；若有 registry 选择框，选择刚配置的 `GitHub GHCR`。不要删除 Stack、容器数据卷或修改 Cloudflare Tunnel。
5. 等待容器恢复 `healthy`，打开 `codex.leohub.cc` 确认蓝色界面与原有历史。如果拉取返回 `unauthorized/denied`，检查 registry 凭据及镜像权限；不要改为公开镜像来绕过认证。

以后等 Actions 绿色成功，再在同一 Editor 点 **Update the stack** 并重新拉取即可。这个按钮与 Git 来源 Stack 的 **Pull and redeploy** 名称不同，都可以拉取新镜像更新容器。当前 Stack 无需迁移，也无需每次改镜像版本号。

### 仓库 Compose 与回退

`compose.ghcr.yaml` 是按已确认的 US VPS 配置提供的完整独立文件；不要与 `compose.yaml` 合并使用。它保留回环端口、网络、数据卷、CPU/内存/日志限制，并把**现有** `codex-reset-data` 声明为 external；卷缺失时直接失败，不静默创建空历史库。用于已有 Git 来源 Stack 时，Repository URL 为 `https://github.com/Leoeric1/codex_reset`，Reference 为 `refs/heads/main`，Compose path 为 `compose.ghcr.yaml`。关闭 GitOps 自动更新，手动 **Pull and redeploy** 并开启重新拉取镜像。不要在当前同名容器运行时另建第二个 Stack；当前 Editor 方式无需设置 Git 仓库读取权限。

首次从本地镜像升级失败，可把原 Stack 两行恢复为 `image: codex-reset-monitor:1.0.0` / `pull_policy: never`，关闭重新拉取后更新；须保留该本地镜像和原卷。以后可固定到已验证的 GHCR digest 或提交镜像回退。回退镜像不会恢复数据库时间点，涉及未来破坏性 schema 变更时需单独制定数据恢复方案。本次通知升级只新增表。

GHCR 发布流程只负责镜像，不启用微信推送，也不替代后文的 LeoHub Service Auth 配置。

参考：[GitHub GHCR 权限与认证](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry)、[Portainer 更新现有 Stack](https://docs.portainer.io/user/docker/stacks/edit)。

## US VPS 本地构建：备用部署方式

在 US VPS 克隆本仓库并准备镜像：

```bash
git clone https://github.com/Leoeric1/codex_reset.git /opt/codex-reset-monitor
cd /opt/codex-reset-monitor
bash scripts/prepare.sh
```

脚本在当前 VPS 构建 `codex-reset-monitor:1.1.0` 本地镜像，创建独立 bridge 网络 `leohub-monitor`，并将现有 `cloudflared`、`uptime-kuma` 容器附加到该网络。它不会移除这些容器的原有网络，不重启已有服务，不操作防火墙、3x-ui 或量化系统。发现 host/none 网络或容器不存在时，会提示而不会强行重建。实际名字不同时可设置 `CLOUDFLARED_CONTAINER` 和 `KUMA_CONTAINER`。

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

## 1.1 LeoHub UI 与通知联动

页面复用 LeoHub Logo 的独立副本及蓝色变量体系，支持设备本地深浅主题；无预告时压缩成一行，状态详情默认收起、异常时展开。手动刷新只读取本地数据，不触发 AIHOT 抓取。正常 AIHOT 间隔仍为 300 秒，退避、ETag、确认帖时间和日期精度语义均不变。

### 私有通知协议 v1

| 接口 | 用途 |
| --- | --- |
| `GET /api/notifications/latest` | 默认/最多 10 条，附带 `schema_version`、`initialized`、`epoch`、`cursor`、`updated_at` |
| `GET /api/notifications/changes?after=0&limit=100` | 按连续序号分页，默认/最多 100 条；返回 `next_cursor`、`has_more` |

`cursor` 是通知变化序号，不是源站时间戳。`epoch` 标识当前数据库通知流；正常重启保持不变。数据库被替换后 Hub 会安全停止同步，不自动重新基线或重放历史。`initialized=false` 时 Hub 不得建立基线；正常空快照完成后可以初始化。

每条变化仅包含 `seq`、`operation`（`upsert` / `cancel`）、`notification_id` 和整理后的 `item`。ID 沿用 `event_id:notification_type`。预告转确认使用新的通知 ID；文字修订使用原 ID，Hub 更新内容而保留已读。

通知正文含 `type/status/kind/title/time/time_precision/time_label/created_at/expires_at/source_url` 及事件/通知 ID。不含原始快照、英文全文、ETag、内部发送状态或配置。变化日志只保存序号、标识和操作，正文实时从当前有效事件投影；撤回后不会通过旧增量页泄露或恢复原文。

升级自动新增 `hub_events`、`notification_changes`、`notification_stream`，不改旧 `notifications` 表的复合主键和 disposition 语义。旧库 `disabled` 记录不回填到 Hub；首次历史仍抑制。Hub 首次成功读取 cursor 时再建立共享基线，已有通知不补报。撤回通过完整快照移除检测；有效预告到期只停止提醒，不推断重置已经发生。

### 认证及部署顺序

1. 更新 Codex 容器，保留原数据卷，确认新接口可以通过个人邮箱 Access 登录访问。
2. 为 LeoHub 创建专用 Service Token；在 Codex Access 中配置 Service Auth。建议将服务授权限定到 `/api/notifications/*`，若建立更具体路径的 Access application，必须同时保留该路径的个人邮箱 Allow 策略。整个站点现有邮箱登录继续保留，无 Bypass。
3. 在 LeoHub Pages 生产环境配置 `CODEX_API_URL=https://codex.leohub.cc/api/notifications/latest` 与 `CODEX_SERVICE_CLIENT_ID`、`CODEX_SERVICE_CLIENT_SECRET` 两项 Secrets，然后重新部署 Pages。
4. Hub 第一次有效读取只建立基线。后续新确认/预告才出现提醒；电脑已读后，手机下一轮检查或切回前台同步消失。

配置未完成时 Hub 会显示“提醒不可用”，不影响服务卡片和编辑。

### 外发通知保持关闭

`NOTIFICATION_PROVIDER=disabled` 为默认和当前唯一实现。`NotificationSender` / `DisabledNotificationSender` 仅预留扩展边界。未来可使用 `pushplus` provider 与 `PUSHPLUS_TOKEN`，但当前即使配置它们也不会发送；不支持的 provider 会记录一条不含配置值的提醒并继续禁用外发，不阻塞监控启动。Hub 提醒不受外发禁用影响。

本版没有发送后台循环、重试任务或第三方推送依赖，也不更新 `sent_at`。未来 sender 必须在快照事务完成后独立运行，失败不得回滚快照；启用渠道时必须建立独立启用基线，不能扫描旧记录补发。

### 验收边界

本次执行 40 项 Python 行为测试；Chromium 检查桌面及 375/390/430px，覆盖双主题、原 Logo、分页筛选和失败保留。跨仓库测试使用合成数据，无生产写入。真实 iPhone Safari、线上 Service Auth、VPS 容器资源占用留待部署验收。

运行资源限制仍为 0.25 CPU / 128 MiB、单 worker。推荐使用前文的 GitHub 构建，VPS 仅拉取运行。本地备用构建不受容器运行配额约束，在 1 核 VPS 上应选空闲时段执行并观察其他应用。本地镜像标签 `1.1.0`，保留旧镜像以便回退；不要删除数据卷。
