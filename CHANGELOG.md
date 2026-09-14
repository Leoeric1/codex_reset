# Changelog

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
