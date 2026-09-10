# Rathole-Bt

Rathole-Bt 是一个面向 **宝塔 Linux 面板** 的 Rathole 可视化管理插件，用于在网页中完成 Rathole 服务端/客户端的安装、配置、运行维护和版本更新。

插件不修改 Rathole 协议，也不自带魔改核心。Rathole 核心程序由插件从官方 Release 获取并安装；本项目主要负责宝塔面板侧的管理体验。

> 本项目为第三方插件，并非宝塔官方插件，也不是 Rathole 官方项目。

## 功能

- 支持 **Server / Client** 两种运行模式
- 支持 **TCP / UDP** 穿透规则
- 支持多条隧道规则统一管理
- 支持 **Noise 加密**，服务端可直接生成密钥
- 支持 Rathole 官方稳定版安装与升级
- 支持 systemd 启动、停止、重启和开机自启
- 支持配置生成、保存、备份和启动前校验
- 支持实时查看 Rathole 运行日志
- 支持查看安装状态、运行状态、配置状态、核心版本和系统架构
- 支持插件自身通过 GitHub 检查并在线更新
- 更新插件时保留 `/etc/rathole` 等用户配置数据

## 界面

2.2 起重新按照当前宝塔 Modern 软件设置窗口的视觉规范设计，采用左侧设置导航，统一按钮、表单、选择器、开关、表格、弹窗、状态和日志区域的尺寸与交互。

插件继续使用宝塔第三方插件标准兼容入口，不修改宝塔核心文件，也不依赖宝塔私有 Vite/Vue 模块，从而降低面板升级后的兼容风险。

主要页面：

- 服务管理
- 连接配置
- 穿透规则
- 运行日志
- 版本管理

## 典型部署

```text
Internet
   |
   v
公网服务器
Nginx / HTTPS / WAF
   |
   v
Rathole Server
   |
   |  Noise 加密隧道
   v
Rathole Client
家庭 NAS / 内网服务器
   |
   v
Nginx / Go / PHP / WordPress / 其他服务
```

家庭宽带无需固定公网 IP。Client 主动连接公网 Rathole Server，因此家庭公网 IP 变化后只需客户端重新建立连接。

## 安装

从 GitHub Releases 下载最新的 `rathole_manager_v*.zip`，然后通过宝塔面板的第三方插件导入功能安装。

安装后插件会创建 Rathole 所需的 systemd 服务与配置目录，但在保存有效的 Server 或 Client 配置之前不会启动 Rathole，避免空配置导致 systemd 反复重启。

### 公网服务器

选择 **服务端**：

```text
监听地址：0.0.0.0
隧道端口：2333
传输加密：Noise
```

Web 转发场景可创建一条规则，例如：

```text
名称：web
协议：TCP
转发地址：127.0.0.1
转发端口：18080
Token：服务端与客户端保持一致
```

公网服务器安全组只需要允许客户端访问 Rathole 隧道端口，例如 TCP `2333`。

### 家庭 NAS / 内网服务器

选择 **客户端**：

```text
公网服务器：公网服务器 IP 或域名
隧道端口：2333
传输加密：Noise
服务端公钥：粘贴服务端生成的 Noise 公钥
```

对应 Web 规则：

```text
名称：web
协议：TCP
本地地址：127.0.0.1
本地端口：80
Token：与服务端完全一致
```

公网 Nginx 再反向代理到：

```text
http://127.0.0.1:18080
```

即可让公网流量通过 Rathole 隧道进入家庭 NAS。

## 文件位置

```text
Rathole 核心        /usr/local/bin/rathole
Rathole 配置        /etc/rathole/rathole.toml
配置备份            /etc/rathole/rathole.toml.bak
插件状态            /var/lib/rathole-manager/state.json
有效配置标记        /var/lib/rathole-manager/configured
systemd 服务        /etc/systemd/system/rathole.service
宝塔插件目录        /www/server/panel/plugin/rathole_manager
```

卸载插件时默认保留 Rathole 核心、配置和状态文件，避免误删已有隧道配置。

## 在线更新

插件会读取本仓库的 `update.json` 检查新版本。检测到更新后可直接在插件内执行在线更新。

发布流程由 GitHub Actions 完成：

```text
更新 main 源码
      |
      v
读取 info.json 版本
      |
      v
代码检查
      |
      v
生成插件 ZIP
      |
      v
创建对应 Git Tag / GitHub Release
```

因此仓库根目录始终保存**完整、可发布的插件源码**，Release 安装包直接由这些源码生成。

## 兼容性

当前主要面向：

- 宝塔 Linux 面板 11.x
- Debian / Ubuntu 等 systemd Linux 发行版
- x86_64 / amd64
- aarch64 / arm64

## 上游项目

Rathole 核心项目：`rathole-org/rathole`

Rathole-Bt 仅提供宝塔面板集成和可视化管理能力。Rathole 本身的协议、核心能力与许可证以其上游项目为准。
