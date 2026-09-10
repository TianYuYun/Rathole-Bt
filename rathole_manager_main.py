# Rathole Manager for BT Panel 2.2

宝塔 Linux 面板自定义插件，用于可视化管理官方 Rathole 服务端与客户端。

## 2.2 核心变化

2.2 将界面完整重构为当前宝塔/aaPanel Modern 软件设置窗口的视觉结构：左侧设置导航、紧凑服务页、原生尺寸表单/按钮/表格、Modern 弹窗与消息提示。插件仍使用宝塔为第三方插件保留的兼容入口，不修改面板源码，也不依赖私有 Vue/Vite chunk。

主要特性：

- 左侧：服务管理 / 连接配置 / 穿透规则 / 运行日志 / 版本管理。
- 服务管理集中显示运行状态、Rathole 版本、当前模式、配置状态、开机自启、系统架构。
- 地址与端口分别输入，客户端/服务端字段独立。
- 支持 Noise（推荐）和 TCP；服务端可生成 Noise 密钥，私钥不在页面显示。
- 未保存有效配置时拒绝启动/重启。
- systemd `ConditionPathExists` 防止空配置无限重启。
- x86_64 / arm64 自动选择官方 Rathole Release 安装包。
- 稳定版/开发版信息动态读取官方 GitHub Release。
- Modern Confirm、Toast、Loading 不依赖第三方 UI 库。
- 读取宝塔当前主题 CSS 变量，支持面板主题切换和深色主题。
- 插件自身在线更新：从 `TianYuYun/Rathole-Bt` 检查新版本，更新前自动备份插件文件，不覆盖 `/etc/rathole`。

详细 UI 对齐参数见 `UI_BASELINE.md`。

## 推荐部署结构

```text
用户
  -> 公网服务器 Nginx / 宝塔 / WAF / HTTPS
  -> 127.0.0.1:18080
  -> Rathole Server
  -> Noise 加密隧道
  -> Rathole Client（家庭 NAS）
  -> 127.0.0.1:80
  -> 本地宝塔 Nginx
  -> Go / PHP / WordPress
```

## 安装

将 ZIP 作为宝塔自定义插件导入，插件目录名保持 `rathole_manager`。

建议两端都安装相同版本：

- 公网服务器：选择「服务端（公网服务器）」
- 家庭 NAS：选择「客户端（家庭 / NAS）」

## 最小 Web 配置

### 公网服务器

- 模式：服务端
- 隧道监听：`0.0.0.0` + `2333`
- 加密：Noise
- 规则：`web` / TCP
- 公网机转发入口：`127.0.0.1` + `18080`
- Token：至少 8 位

公网安全组允许 NAS 连接 TCP 2333。`127.0.0.1:18080` 不需要公网开放。

### 家庭 NAS

- 模式：客户端
- 公网服务器：公网服务器 IP/域名 + `2333`
- 加密：Noise
- 服务端公钥：复制服务端插件显示的 Noise 公钥
- 规则：`web` / TCP
- 本地服务：`127.0.0.1` + `80`
- Token：与服务端 `web` 规则完全一致

### 公网 Nginx

反向代理目标：

```text
http://127.0.0.1:18080
```

## 文件位置

- Rathole：`/usr/local/bin/rathole`
- 配置：`/etc/rathole/rathole.toml`
- 配置备份：`/etc/rathole/rathole.toml.bak`
- 插件状态：`/var/lib/rathole-manager/state.json`
- 有效配置标记：`/var/lib/rathole-manager/configured`
- systemd：`/etc/systemd/system/rathole.service`

## 兼容目标

- Debian 11 / 12 / 13
- 常见 Ubuntu Server
- systemd
- 宝塔 Linux 面板 11.x 第三方插件兼容入口
