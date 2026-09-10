# Rathole Manager - Modern UI Baseline

本版本不是凭视觉猜测，而是按当前公开 aaPanel/宝塔同源前端中的 Modern UI 几何和主题变量制作第三方插件适配层。

## 对齐的官方结构

- `BtTabsModal`：左侧 card tabs，Modern 模式。
- `BtModal`：标题栏、关闭按钮、内容区、底部操作区。
- `BtMessage`：居中消息、状态图标、loading。
- Form / Input / Select / Button / Switch / DataTable：采用当前主题 token 尺寸。

## 固定几何

- 左侧 Modern Tab：32px 高、6px 圆角、`0 10px` 内边距。
- Pane：8px 圆角。
- Modal：10px 圆角。
- Modal Header：53px 高、14px 标题、关闭按钮 24x24、右侧 20px。
- Button medium：32px；small：26px；圆角 6px。
- Input medium：32px。
- Form label：12px。
- Switch small：28x16；滑块 12x12。
- Table th：8px padding；td：6px 8px padding。
- Message：最大 360px；padding `16px 20px 16px 15px`；图标 30px。

## 主题变量

优先直接读取面板现有变量，缺失时才使用兼容 fallback，包括：

- `--color-primary`
- `--color-bg-1` / `--color-bg-2`
- `--color-border`
- `--color-text-1` / `--color-text-2` / `--color-text-3`
- `--color-modal`
- `--color-table-th` / `--color-table-td`
- `--input-text-color`
- `--button-bg-hover`
- `--bt-tabs-modal-modern-active-bg`
- `--bt-tabs-modal-modern-hover-bg`

## 兼容策略

宝塔当前真正的 Vue/Naive UI 软件配置 View 由面板内部路由/编译模块维护，普通第三方插件仍经 `index.html + *_main.py` 兼容入口加载。因此本插件不修改面板源码、不注册私有 Vue 组件、不依赖带构建版本号的 Vite chunk，而是在官方第三方入口中复刻 Modern UI 的布局与 token。
