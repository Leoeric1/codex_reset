# Changelog

## 桌面日历布局

- 首页改为最近重置及原帖 / 最近重置卡概览，下方月历与日期详情分栏；保留 LeoHub 蓝色深浅主题，有效预告成条，无预告时隐藏。
- 月历替代原长时间线，支持跨月、回到最近、当月分类数量、同日多事件与原帖分组，长详情独立滚动；本次仅覆盖桌面，不新增日历库或预测模型。
- 新增只读 `/api/calendar`，完整月份摘要与当日详情分页分离，避免历史 10/30 条限制漏记录。保留北京日期、确认帖与实际执行时间的区别，预告按发帖日归档。
- 保留选中日期、请求失败时的原内容、迟到请求保护及快照变化时的分页重置。原始帖子内容只作为文本显示。
- Python 59/59 通过，1280 / 1440 桌面深浅主题与交互检查通过；发布前容器冒烟增加 calendar API 检查。
- 不修改 AIHOT 同步、Hub 通知与已读、数据库 schema、镜像发布方式或资源上限；保留远端新加入的默认 `docker-compose.yml`。未操作 VPS / Cloudflare。

## 部署流程更新 — 2026-09-15

- 新增 GitHub Actions：main 提交后测试、构建并发布 GHCR amd64 / arm64 镜像，提供 main 和完整提交 SHA 标签。amd64 镜像发布前执行断网、非 root、只读、0.25 CPU / 128 MiB 冒烟检查；VPS 不参与构建。
- 使用 GitHub 临时 GITHUB_TOKEN 发布，不保存 PAT、不改变镜像可见性，不触发 VPS 自动更新或 Cloudflare 配置修改。
- 新增独立 compose.ghcr.yaml，按当前 VPS 保留 127.0.0.1:18080、leohub-monitor、codex-reset-data 和资源上限；现有数据卷声明 external，缺失时停止部署。
- 文档优先复用现有 Portainer Editor：配置私有 GHCR 凭据后改两行，日后手动拉取更新；补充 Git 来源参数和回退说明。本地构建仍可备用。
- 应用仍为 1.1.0；不改变 AIHOT 300 秒轮询、通知判断、UI 或外发默认 disabled。

## 1.1.0 — 2026-09-15

- 页面统一为 LeoHub 蓝色深浅主题，复用独立 Logo，收起状态详情、压缩空预告、历史默认展示 10 条。
- 在旧通知去重表基础上新增 Hub 有效提醒、连续变化游标及数据库通知流标识；提供 latest / changes 私有 API。
- 保留首次历史抑制、旧库不补报、预告转确认独立提醒、文字更新不重置已读及撤回取消。
- 外发 sender 接口默认 disabled，无实际发送、发送后台任务或新增生产依赖；不改变 AIHOT 同步、ETag、退避和时间语义。
- 保持 0.25 CPU / 128 MiB / 单 worker，镜像标签更新到 1.1.0。
- 40 项行为测试及桌面、375/390/430px Chromium 检查通过；跨仓库合成通知协议验证通过。VPS、真实 Safari 与 Cloudflare Service Auth 尚待线上验收。

## 1.0.0 — 2026-09-14（北京时间）

- 新建独立 Codex Reset Monitor，不依赖量化系统。
- 接入 AIHOT v1 实际事件结构、完整快照与 ETag，持久化限流等待。
- 实现 SQLite 缓存、全批校验、撤回同步、故障降级和通知去重预留。
- 实现中文响应式首页、预告与确认时间语义、30 条默认时间线和类型筛选。
- 增加 Docker/Compose、Portainer 部署脚本、Cloudflare Access/Tunnel 与 Kuma 接入说明。
- 本地代码验收已执行；远程部署等待 US SSH 与 Cloudflare 管理入口。

## GitHub 源码交付 — 2026-09-14

- 发布到 `Leoeric1/codex_reset` 的 `main`，增加克隆部署入口。
- 公开仓库包含源码、配置、测试及说明；真实缓存、原始响应和含原帖内容的截图保留在个人环境。
- 已完成源码上传不代表 US VPS 或域名已经上线。
