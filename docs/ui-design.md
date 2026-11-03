# 配置台视觉与交互设计

本文件是配置台网页的设计系统与页面规格，配合 `src/dr_panda_mcp/web/static/app.css` 使用。技术约束见 [planning.md](planning.md) 4.4：服务端渲染、手写 CSS、无外部字体/CDN；采用服务端优先 + 局部 JS 渐进增强。

## 1. 设计原则

1. **状态优先**：启用/停用、测试成功/失败、密钥可用/不可用，半秒内可辨；信息用「色点 + 徽标 + 文字」三重表达，不依赖颜色。
2. **操作有层级**：每页只有一个主操作（新建/保存/确认删除）；测试与编辑为次级；删除为危险次级。
3. **反馈闭环**：提交后必有结果提示；错误可定位到字段；危险操作先确认。
4. **克制**：中性低饱和 + 单一蓝色强调；系统字体；无外部请求；动效只用于 hover/focus 与状态过渡。
5. **可访问**：键盘可达、焦点可见、对比度达标、错误可被读屏感知；窄屏可用。

## 2. Design tokens

### 2.1 颜色

浅色：

| Token | 值 | 用途 |
|---|---|---|
| `--bg` | `#f5f7fa` | 页面背景 |
| `--surface` | `#ffffff` | 卡片、表格、顶栏 |
| `--surface-subtle` | `#f1f4f8` | 次级表面、表头 |
| `--surface-hover` | `#f7f9fc` | 行/区块悬停 |
| `--border` / `--border-strong` | `#e1e6ed` / `#c8d0db` | 分隔线 / 输入框边 |
| `--text` / `--text-secondary` / `--text-muted` | `#12171f` / `#4e5968` / `#64707f` | 主/次/弱文本 |
| `--accent` / `--accent-hover` / `--accent-soft` | `#2563eb` / `#1d4ed8` / `#eff4ff` | 主操作、选中态 |
| `--success` / `--warning` / `--danger` | `#15803d` / `#b45309` / `#b42318` | 语义色 |
| `--focus` | `#2563eb` | 焦点环 |

深色：

| Token | 值 |
|---|---|
| `--bg` / `--surface` / `--surface-subtle` | `#0c1118` / `#141b24` / `#1a222d` |
| `--border` / `--border-strong` | `#25303e` / `#354354` |
| `--text` / `--text-secondary` / `--text-muted` | `#e7edf4` / `#a8b4c2` / `#7f8b9b` |
| `--accent` / `--accent-hover` / `--accent-soft` | `#4d8dff` / `#6ea0ff` / `#16233a` |
| `--success` / `--warning` / `--danger` | `#3fb950` / `#d29922` / `#f85149` |
| `--focus` | `#6ea0ff` |

语义色的浅底（`--success-soft`、`--warning-soft`、`--danger-soft`、`--accent-soft`）与边框（`--*-border`）成对定义，浅深两套都满足正文 4.5:1。

### 2.2 字体与字号

| 角色 | 值 |
|---|---|
| 正文字体 | `-apple-system, "SF Pro Text", "PingFang SC", "Microsoft YaHei", "Segoe UI", Roboto, sans-serif` |
| 等宽 | `ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace`（目标名、地址、错误详情） |
| 基准 | 14px / 行高 1.55 |
| 页面标题 h1 | 22px / 600 |
| 区块标题 h2 | 16px / 600 |
| 正文强调 | 13px / 500 |
| 辅助文字 | 12px / 400 |
| 数字 | `font-variant-numeric: tabular-nums` |

### 2.3 间距 / 圆角 / 阴影

- 间距：`--space-1..8` = 4/8/12/16/20/24/32/40px；组件内部用 3–4，区块之间用 5–6。
- 圆角：`--radius-sm` 6px（控件）、`--radius-md` 10px（卡片/表格）、`--radius-lg` 14px（错误页）、`--radius-pill` 999px（徽标/开关/筛选）。
- 阴影：`--shadow-sm` 用于卡片，`--shadow-md` 用于悬停/浮层；深色用更低透明度的黑色 + 边框承担层次。
- 焦点：2px 实线 + 2px offset，颜色 `--focus`。

## 3. 组件

| 组件 | 类 | 规则 |
|---|---|---|
| 顶栏 | `.topbar` | sticky，含品牌、主导航、版本 chip、语言切换（EN / 中文）、主题切换；窄屏换行 |
| 导航项 | `.tab` | 选中态用 accent-soft 底 + accent 文字 + `aria-current` |
| 按钮 | `.btn` + `--primary/--secondary/--ghost/--danger/--danger-ghost` | 高度 34（sm 28）；每页最多一个 primary；危险操作用 danger |
| 输入框 | `.input` | 高 34、1px 边框、focus 环；错误态 `.field--invalid` 红边 |
| 字段 | `.field` | 标签 + 控件 + 帮助 + 错误；`scroll-margin-top` 避开 sticky 顶栏 |
| 开关 | `.switch` / `.switch-row` | 表格内用 button 开关（aria-pressed）；表单内用 checkbox 伪元素 |
| 徽标 | `.badge` + `--type/--success/--warning/--danger/--muted` | 11.5px，胶囊形 |
| 状态点 | `.status` + `--ok/--error/--none` | 色点 7px + 文字 |
| 提示条 | `.alert` + `--success/--warning/--danger/--info` | 图标 + 标题 + 说明；用于 flash、表单错误摘要、异步结果（`role=status`/`alert`） |
| 行内动作 | `[data-row-action]` | 列表测试/启停走同源 fetch，只更新当前行与统计，不整页刷新；无 JS 时仍是普通表单 |
| 表格 | `.table` / `.table--responsive` | 表头 sticky 无需；行悬停；≤900px 转卡片（`data-label`） |
| 统计 | `.stats` + `.stat` | 4 项概览；数字 22px semibold |
| 筛选 | `.filter-chips` / `.chip-link` | 链接形式，保留搜索词；当前项 accent |
| 类型卡片 | `.type-card` / `.type-grid` | 2/3/4 列自适应；hover 抬升 |
| 空状态 | `.empty` | 标题 + 说明 + 入口；无目标时给八类型卡片 |
| 详情折叠 | `.details` | `<details>` 展示失败原因等长文本 |
| 危险区 | `.card--danger` | danger-soft 底 + danger 边；确认页使用 |

## 3.5 首次安装与登录

- `/setup`：两步卡片式向导，第 1 步管理员密码，第 2 步配置库选择/连接测试；不显示主导航，保留品牌与语言切换。
- 数据库类型用链接切换 SQLite / MySQL / PostgreSQL，零 JS；测试成功后才启用“完成安装”。
- 安装完成页显示 MCP URL 与 Token；完整 Token 不在后续页面回显。Token 结果弹窗提供复制按钮（自托管 `copy-token.js`，JS 失败时隐藏按钮并显示手动复制提示）。
- “我的”页面用原生 `<dialog>` + 自托管 `app.js` 创建/删除 Token，JS 可用时不跳页；无 JS 回退到独立表单/确认页；创建成功弹窗显示一次 Token。
- `/login`：单列登录卡片，用户名/密码 + CSRF；不显示管理导航的可操作入口。
- 安装/登录页均已接入 `t()` 中英文文案。

## 4. 语言与主题机制

- 语言：默认英文，Cookie `drpanda_lang` 持久化；`en` / `zh-Hans`；顶部 POST `/language` 切换，保留当前路径与设置页 section；零 JS。
- 主题：

```
无 Cookie                 → <html> 无 data-theme；CSS prefers-color-scheme 跟随系统
Cookie=light / dark       → <html data-theme="light|dark">；服务端渲染，无闪烁
POST /theme mode=system   → 清除 Cookie，回到跟随系统
```

- Cookie 名 `drpanda_theme`，`Path=/; Max-Age=1y; HttpOnly; SameSite=Lax`；`next` 只接受站内路径（拒绝 `//`、协议、主机）。
- 切换是普通表单 POST + 303 回原页；不需要 JS，也不会有首屏闪烁。
- 原生控件颜色由 `color-scheme` 跟随主题。

## 5. 页面规格

### 5.1 目标列表 `/`

- 页面头：h1「排查目标」+ 说明 +「管理环境」+ 主按钮「新建目标」。新建目标带上当前环境。
- 环境切换在统计之前：每张卡片是展示名、调用标识和目标数。当前环境用强调色左边线。最后一张虚线卡片去新建环境。
- 只有「默认」环境时，提示展示名可以改，但调用仍传 `default`；要分开乐畅生产和测试，需要新建环境再登记目标。
- 当前环境停用时，说明模型不能查询，配置仍保留。
- 空状态：当前环境没有目标时给出类型入口，并说明同类型多台靠名称区分。别的环境已有目标时，标题是「这个环境还没有目标」。
- 统计：目标总数 / 已启用 / 最近测试失败 / 密钥异常（异常项标红/标黄）。
- 密钥异常时显示全局警告条。
- 工具栏：搜索（`q`，GET）+ 类型筛选（带计数）+ 清除筛选。
- 单表列：名称（链接，密钥异常加徽标）｜类型徽标｜端点（等宽，截断 + title）｜授权范围摘要｜状态开关｜最近测试（状态点 + 绝对 UTC 时间 + 失败详情折叠）｜操作（测试/编辑/删除）。
- 失败详情在「客户端未安装」时只提供「安装」。确认后由服务在当前项目执行 `uv sync --extra <name> --inexact`，不会卸掉其他已装客户端，装完立刻再测。页面不展示、也不复制这条命令。
- 空状态：无目标时显示八类型入口；搜索无结果时显示「没有匹配的目标」+ 清除筛选。

### 5.2 类型选择 `/targets/new`

八张卡片（类型徽标 + 只读要点摘要 + 箭头），点击进入对应表单；页面头提供返回列表。

### 5.3 新建 / 编辑表单

- 面包屑：排查目标 / 类型（编辑时附名称）。
- 两栏：主表单 + 帮助侧栏。
- 分区：基本信息 → 连接 → 授权范围 → 高级设置（TLS、证书、运行限制，默认折叠）。
- 基本信息第一项是所属环境。只有一个环境时只读展示，并链到新建环境。多个环境时用下拉，选中「展示名 · 调用标识」。编辑时环境只读，并说明创建后不能更换。类型选择页同样标明目标会落在哪个环境。
- 错误留在本页：字段级错误 + `aria-invalid`；结果区在操作按钮上方，不在页顶重复。
- 密钥：密码框 + 已设置徽标；留空表示不改。
- 操作：取消是链接；测试连接是独立按钮；保存是唯一提交按钮。新建时保存先禁用，测试通过后启用。编辑时连接未改可以直接保存。
- Mongo 只显示当前认证方式的字段。TLS/证书只在启用 TLS 或 SSL/SASL_SSL 时显示。
- 运行上限的说明是「这些上限作用于之后的工具调用」。

### 5.4 系统配置 `/settings`

左侧子菜单是真实链接。未保存时离开分组或页面会确认。保存留在当前分组并显示页内提示。非 SQLite 配置库不显示备份份数输入，只说明该项不适用。恢复单项列出当前值 → 默认值；恢复全部列出每一项，并说明目标、密钥和只读边界不受影响。

### 5.5 环境 `/environments`

导航「环境」。列表说明展示名和调用标识的差别，并给出乐畅生产 → `lechang-prod`、畅聊生产 → `changliao-prod`、测试 → `test`。列：展示名、调用标识、目标数、状态、操作（查看目标 / 编辑 / 删除）。有目标时不提供删除，说明原因。删除空环境走确认弹窗。新建后回到该环境的目标列表，空状态可以直接选类型。调用标识创建后只读；展示名和启停可以改。

### 5.6 删除确认

列表页 dialog：所属环境、目标名、类型、端点、授权范围、最近测试。取消与确认删除。

### 5.7 错误页

400/404/500 统一：大号状态码、标题、人话说明、返回列表/系统配置。登录失败留在登录卡片里。用户名显示为固定文本 admin。

## 6. 响应式与可访问性

- 断点：1180 容器；≤1024 表单变单栏、侧栏两列；≤900 表格转卡片、统计两列；≤640 顶栏换行、表单/卡片单列、按钮拉通。
- 键盘：跳转链接、焦点可见、逻辑 Tab 顺序、无陷阱；删除与保存都通过表单可达。
- 语义：`header/nav/main`、每页一个 h1、`aria-current`、表格 `scope`、`aria-pressed`、`aria-live` 提示、`aria-invalid`。
- 对比度：正文/次级/语义色 ≥4.5:1，大字与图标 ≥3:1；`tests/test_ui_contrast.py` 自动校验两套 token。
- 动效：120–180ms ease-out；`prefers-reduced-motion` 下全部关闭。

## 7. 验收

- 浅/深两套、1440/1024/390 三宽度：无横向滚动、无文字截断、无重叠（用 DevTools 协议检查 `scrollWidth == innerWidth`）。
- 主题：默认跟随系统；手选后立即换色并保持；清除后回到系统；首屏由服务端渲染，无闪烁。
- 键盘走查全部页面；对比度自动测试通过；`pytest` 全绿；CSS < 44KB；除自托管渐进增强脚本外无外部请求。

视觉基线截图在 `docs/verify/assets/ui/`，验证记录见 `docs/verify/M3.5.md`。

### 目标表单补充

- TLS/CA/mTLS 仅在启用 TLS（Kafka 为 SSL / SASL_SSL）时显示；
- PEM 字段独占整行；
- 数字输入带 min/max；
- 底部操作为取消 / 测试连接 / 保存，测试连接不写库；
- 新建：保存先禁用，测试通过后启用。编辑：连接快照与已保存值一致时保存可用，提示「连接未修改，可以直接保存。」；
- 结果区在操作条上方；失败展示脱敏原因与时间、耗时；
- 主机、账号、密钥、TLS 或超时变化后需要重新测试。名称、启停、授权范围、行数和字节上限不参与这道门槛。
