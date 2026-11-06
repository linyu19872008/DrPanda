# 保存后误弹「离开此网站」01 · 验证记录

背景：目标表单点「保存」后，无论保存成功与否，Chrome 每次都弹原生确认框「离开此网站?
系统可能不会保存您所做的更改。」。根因是 `app.js` 的未保存守卫：表单带 `data-leave-guard`，
任何输入会置 `data-dirty="1"`；但目标表单保存成功后 `doSave` 直接
`window.location.assign(redirect)` / `window.location.reload()`，**没有清除 dirty 标记**，
于是 `beforeunload` 把「保存后的正常跳转」当成放弃修改，触发浏览器原生弹窗。

导航只发生在 `await postForm(...)` 成功之后，所以弹窗出现时数据其实已经保存；点「取消」
会停在已保存的旧页面上，容易误导并导致重复提交。系统配置表单当时已清除 dirty，所以只有
目标表单会弹。

## 变更（`src/dr_panda_mcp/web/static/app.js`）

| 项 | 现状 |
|---|---|
| 新增 `clearUnsaved(form)` | 主动跳转前清掉该表单的 `data-dirty`，集中一个入口 |
| 目标表单保存 | 成功分支在 `location.assign(redirect)` 与 `location.reload()` 之前调用 `clearUnsaved(form)` |
| 系统配置保存 | 原有 `delete form.dataset.dirty` 改为 `clearUnsaved(form)`，行为等价 |
| 其他程序化跳转 | 登录/改密跳转、安装向导完成跳转、401 跳登录前同样清理，避免以后加守卫时重复踩坑 |
| dirty 判定 | 由「任何 input/change 即 dirty」改为「`FormData` 指纹与打开页面时比较」，改回原值会撤销 dirty |

未改动的行为：点普通链接、切换语言时仍走自定义中文确认
「有未保存的修改，离开后会丢失。确定离开？」（这是设计意图，保留）。

## 验证

### 自动化

- `node --check src/dr_panda_mcp/web/static/app.js`：通过。
- `uv run python scripts/check_leave_guard.py`（真实 Chrome + CDP，最小 harness 加载真实 `app.js`、打桩 fetch）：

```
A 保存后 URL: about:blank#saved
A beforeunload 记录: {"prevented":false,...}          # dirty 已清，未拦截
A 弹窗事件: []
B 对照 beforeunload: {"dirty":"1","prevented":true}   # 阳性对照：未保存修改会被拦截
B 对照弹窗事件: ['beforeunload']
C 改后 dirty: 1  改回后: undefined
PASS: 保存不再触发「离开此网站」，未保存修改仍会被拦截
```

场景 A 是修复后的保存路径；场景 B 手工构造「带 dirty 直接跳转」（即修复前的保存表现），
证明检测有效；场景 C 验证改回原值撤销 dirty。

- `ruff check .`：全过。
- 全量 `pytest`：525 passed, 1 failed；唯一失败是 `tests/test_healthz.py::test_mcp_route_mounted`
  （`SecurityHeadersMiddleware` 无 `routes` 属性），已在干净 HEAD 上复现，属既有问题，与本次无关。

### 手工回归清单（真实实例）

1. 新建目标 → 填字段 → 测试连接 → 保存：跳回目标列表并显示成功提示，**不出现**「离开此网站」。
2. 编辑目标 → 改一个字段 → 保存：同样不弹。
3. 改一个字段后点「取消」链接：出现自定义确认「有未保存的修改，离开后会丢失。确定离开？」（应弹）。
4. 改一个字段再改回原值：点「取消」不应弹确认（dirty 已撤销）。

## 边界

- 「离开此网站」是浏览器原生对话框，文案不可自定义、不可翻译；修好后正常保存路径不会再触发。
- 守卫只作用于带 `data-leave-guard` 的表单（目标新建/编辑、系统配置）。
- `scripts/check_leave_guard.py` 依赖本机 Chrome 与 `websockets`；找不到 Chrome 时打印 SKIP 并返回 0，不接入 pytest。
- 若以后新增「保存后程序化跳转」的表单，记得跳转前调用 `clearUnsaved(form)`（或复用同一约定）。
