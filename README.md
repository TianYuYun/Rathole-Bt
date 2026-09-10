# Rathole-Bt

宝塔 Linux 面板的 Rathole 可视化管理插件。底层直接使用官方 Rathole 二进制，插件只负责安装、配置、systemd 服务和可视化管理。

## 功能

- Server / Client 双模式
- TCP / UDP 穿透规则
- Noise 加密
- Rathole 官方稳定版一键安装/升级
- systemd 启动、停止、重启和开机自启
- 运行日志
- 有效配置校验，避免空配置反复重启
- 插件自身 GitHub 在线更新

## 典型架构

`域名 -> 公网服务器宝塔/Nginx -> Rathole -> 家庭 NAS 宝塔/Nginx -> Go/PHP/WordPress`

家庭 NAS 不需要固定公网 IP，也不需要开放 80/443；客户端会主动连接公网 Rathole 服务端。

## 推荐的 Web 穿透规则

公网服务端：监听 `0.0.0.0:2333`，`web` 规则绑定 `127.0.0.1:18080`。

家庭客户端：连接 `公网服务器IP:2333`，同名 `web` 规则指向 `127.0.0.1:80`。

然后在公网服务器宝塔中把域名反向代理到 `http://127.0.0.1:18080`。

## 在线更新

插件从仓库根目录 `update.json` 检查新版本。更新文件从对应 Git tag 下载，用户的 Rathole 配置存放在 `/etc/rathole` 和 `/var/lib/rathole-manager`，不会被插件文件更新覆盖。

仓库内的 GitHub Actions 会在 `main` 中出现新版本号时自动校验代码、打包宝塔插件 ZIP，并创建对应 GitHub Release。

## Rathole

上游项目：`rathole-org/rathole`。插件安装 Rathole 核心时实时读取官方 GitHub 最新稳定 Release，而不是把核心版本写死在插件代码中。
