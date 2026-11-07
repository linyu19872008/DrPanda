# 新建/编辑表单客户端安装 1.2.0 · 验证记录

## 背景

列表页已有“缺少客户端 → 安装 → 自动重测”，但新建/编辑目标表单只显示错误文本，未保存目标无法走 `/targets/{id}/install-client`。

以 Mongo 为例，表单探测失败显示：

```text
mongo client is not installed: uv sync --extra mongo --inexact
```

用户仍需手工执行命令。

## 改动

### 后端

- `web/views.py` 新增 `probe_install_extra()`：只从固定 missing-client 错误中识别 extra。
- `web/routes.py`：
  - `_probe_failure()` 写入结构化 `install_extra`；
  - probe JSON 返回 `install_extra`；
  - HTML probe 结果隐藏 `uv sync` 命令，只保留业务说明；
  - 新增 `POST /targets/install-client`，只接受目标类型，服务端推导固定 extra；
  - 安装失败只展示业务错误，不把命令暴露给页面。
- 复用现有 `client_install.install_extra()` 的固定 extra、安装锁和超时机制。

### 前端

- 新建/编辑表单的 probe 结果区域增加“安装客户端”动作；
- 安装成功后自动重新 probe；
- 安装失败保留表单，显示安装错误；
- 只对 `mysql/mongo/redis/kafka/cls` 显示安装动作；
- ES/GitLab/RabbitMQ 没有独立 extra，不显示无法兑现的安装按钮；
- PostgreSQL 是配置库 extra，不属于目标类型，后续单独在安装向导处理。

## 测试

新增覆盖：

- `probe_install_extra` 对五个固定 extra 的识别；
- 普通连接失败不产生安装动作；
- probe JSON 返回 `install_extra`，消息不包含 `uv sync`；
- HTML 表单包含 `/targets/install-client` 安装入口，且不展示命令；
- 新安装接口只执行固定 extra；
- 不支持的类型返回 400；
- 安装失败返回干净的业务错误，不包含 `uv sync`。

验证：

- `pytest -q`：**578 passed**；
- `ruff check .`：通过；
- 文档链接检查：通过；
- `uv build --offline`：成功生成 `dr_panda_mcp-1.2.0` sdist/wheel。

## 边界

- 自动安装仍只支持 source + uv 项目部署；`uv tool` / PyPI 安装未找到项目目录时会显示安装失败原因。
- PostgreSQL 配置库驱动安装未纳入本次目标表单流程。
