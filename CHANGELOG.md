# Changelog

## 1.0.1 - 2026-09-10

Rathole-Bt 首个正式基线版本。

- 宝塔 Linux 面板 Rathole 服务端 / 客户端可视化管理。
- 支持 TCP / UDP 穿透规则与 Noise 加密。
- 支持官方 Rathole Release 稳定版 / 开发版安装与升级。
- 支持 systemd 启停、重启和开机自启。
- 支持配置校验、运行日志和状态展示。
- 插件在线更新仅使用 GitHub Releases：检查最新 Release，下载完整 ZIP，执行 SHA256、Python、Shell 与版本一致性校验，再原子替换并支持失败回滚。
- 不依赖 raw.githubusercontent.com，不使用第三方镜像或国内中转。
