# 验证截图资产清理 01 · 验证记录

背景：仓库当前树中图片占已跟踪体积的大部分；P1 删除未引用图片，P2 将验证截图压缩为 WebP。

## P1：删除未引用图片

经全仓库文本扫描，以下 3 张图片没有被任何 Markdown/HTML/代码引用，已删除：

- `docs/zh-CN/verify/assets/ui/proposal-audit-result-columns.png`
- `docs/zh-CN/verify/assets/ui/target-mysql-form-1440.png`
- `docs/zh-CN/verify/assets/ui/target-mysql-form-390.png`

## P2：PNG → WebP

- 对 `docs/zh-CN/verify/assets/ui/` 下剩余 48 张 PNG 使用 `cwebp -q 85 -m 6 -sharp_yuv` 转换；
- 保留原分辨率，不缩放；
- 删除原 PNG，更新 19 个 Markdown 文档中的图片引用为 `.webp`；
- 体积变化：
  - 原 50 张 PNG：约 **5.03 MiB**
  - 新 48 张 WebP：约 **1.49 MiB**
  - 当前树节省约 **3.54 MiB**

## 验证

- `webpinfo`：48 个 WebP 全部可解析；
- 抽查 1440×1000 截图，文字和表格可读；
- `python scripts/check_docs_links.py`：OK（74 个 Markdown 文件）；
- 未修改应用代码、测试、README 或运行时资源。

## 边界

- 本次只减小**当前工作树/当前提交**，Git 历史中的旧 PNG 仍然存在，clone 历史体积不会因此明显下降；
- 如需进一步缩小历史体积，需要重写 Git 历史，风险高，不建议为了约 3–4 MiB 执行；
- 文档中的历史截图现在使用 WebP，GitHub/Gitee 与主流 Markdown 预览均支持。
