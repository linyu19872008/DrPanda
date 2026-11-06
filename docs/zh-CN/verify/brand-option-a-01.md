# 品牌区方案 A 01 · 验证记录

背景：从三版视觉稿中选定方案 A（精细化侧栏品牌），目标是让 32px 竖版插画不再显得"裸图贴纸"，并改善品牌与导航的对齐和节奏。

## 变更

| 层 | 改动 |
|---|---|
| CSS | `app.css` 的 `.sidebar__brand`：36px 图标列、10px 列间距、2px 行距；图标改为圆角容器（3px 内边距、`object-fit: contain`、浅底 + 1px 描边、10px 圆角）；标题 16px/行高 1.2、副标题 11.5px/1.2，分别对齐行首/行尾 |
| 间距 | `.sidebar__nav` 顶部 padding 由 8px 调到 12px，品牌块与导航之间增加呼吸 |
| 文档 | `ui-design.md` 侧栏说明补充 36px 圆角容器与"品牌/导航左对齐" |
| 视觉稿 | 保留 `docs/verify/brand-visual-options-01.md` 与三张方案图供对照 |

未改模板/HTML、Logo 资源、行为或 i18n。

## 验证

- 真实页面截图（测试客户端 + 实际 `app.css`，中文、1440×900、浅色）：
  - [方案 A 落地效果](assets/ui/brand-option-a-real-1440.png)
- CSS 预算测试：`test_no_javascript_and_css_budget` 通过；`app.css` 当前 **54,759 字节**（上限 55,000）。
- 全量 `pytest`：**561 passed, 1 failed**（既有的 `test_healthz.py::test_mcp_route_mounted`，与本次无关）；`ruff check .` 全过。

## 边界

- 移动端（≤900px）侧栏品牌隐藏、顶栏品牌显示，本次规则只作用于 `.sidebar__brand`，移动端品牌不受影响。
- 深色主题使用 CSS 变量（`var(--surface)`/`var(--border)`），未单独截图验收；浅色已验收。
- Logo 仍是当前竖版插画，放进圆角容器展示；若之后生成方形 logo，只需替换资源，无需改结构。
- 纯 CSS 改动，无需重启服务，刷新页面即可（CSS 带内容哈希）。
