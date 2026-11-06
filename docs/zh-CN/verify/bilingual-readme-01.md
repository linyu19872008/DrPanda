# 双语 README 语言一致性 01 · 验证记录

背景：要求中文 README 只展示中文软件截图、只链接中文文档；英文 README 只展示英文软件截图、只链接英文文档。

## 变更

### 中文 README

- 截图改为 `docs/zh-CN/assets/screenshot-zh.png`（中文界面、1440×900）；
- 文档章节继续链接中文设计/验证文档（`docs/planning.md`、`docs/milestones.md`、`docs/ui-design.md`、`docs/zh-CN/verify/*`）；
- 顶部只保留语言切换链接到英文 README。

### 英文 README

- 截图改为 `docs/assets/screenshot-en.png`（英文界面、1440×900）；
- 文档章节不再链接中文 `docs/`，改为英文文档：
  - `docs/README.md`：英文文档索引；
  - `docs/architecture.md`：组件、请求流程、数据模型与部署；
  - `docs/security.md`：安全模型、认证、密钥与远程访问；
  - `docs/ui-design.md`：服务端渲染配置台、设计系统与页面行为；
  - `docs/verification.md`：测试策略、已验证/未验证边界；
- 英文文档内只链接英文 README/治理文档，不链接中文 `*.zh-CN.md` 或中文 `docs/`。

### 截图生成

用真实页面（`/targets`，当前 1.0.0 UI）分别以 `drpanda_lang=zh-Hans` 和 `drpanda_lang=en` 渲染，再经无头 Chrome 截图；数据为临时 SQLite 中的 3 个示例 target，不触碰真实配置库。

## 验证

- `python scripts/check_docs_links.py`：**OK，共 15 个 Markdown 文件**（README、治理文档、5 个英文文档）；
- `ruff check .`：通过；
- 英文 README 与 `docs/*.md` 中文扫描：除语言切换标签“简体中文”外，无中文内容；
- 中文 README 的文档链接仍全部指向中文文档，英文 README 的文档链接全部指向 `docs/`。

## 边界

- `docs/` 是面向英文读者的当前设计摘要，不是历史中文验证记录（`docs/zh-CN/verify/`）的逐篇翻译；
- 历史验证记录保持中文，英文 README 不链接它们；
- README 图片仍使用相对路径以保证 GitHub 页面渲染；PyPI 的绝对图片问题另行处理。
