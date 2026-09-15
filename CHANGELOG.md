# Changelog

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
