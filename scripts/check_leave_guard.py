"""真实 Chrome（CDP）回归：目标表单保存后不应触发浏览器「离开此网站」确认框。

背景：目标表单带 `data-leave-guard`；app.js 在 beforeunload 里拦截未保存修改。
曾出现保存成功后跳转仍带着 `data-dirty`，每次保存都弹浏览器原生确认框。本脚本用
真实 Chrome 加载最小 harness（真实 app.js + 打桩 fetch）验证三个场景：

A. 改字段 → 测试连接 → 保存：导航成功，beforeunload 未被拦截，无弹窗事件。
B. 阳性对照：改字段后直接跳转（修复前的保存表现）：beforeunload 被拦截并有弹窗事件。
C. 改字段再改回原值：`data-dirty` 撤销。

依赖：本机 Chrome、`websockets`（项目依赖已装）。仅用于本地有 Chrome 的环境，不接入 pytest。

用法：
    uv run python scripts/check_leave_guard.py
    DR_PANDA_CHROME=/path/to/chrome uv run python scripts/check_leave_guard.py
缺 Chrome 或 websockets 时打印 SKIP 并返回 0。
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

try:  # 可选依赖：缺 websockets 时脚本 SKIP，不影响主流程
    from websockets.sync.client import connect as _ws_connect
except ImportError:  # pragma: no cover - 依赖缺失路径
    _ws_connect = None

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_JS = REPO_ROOT / "src" / "dr_panda_mcp" / "web" / "static" / "app.js"

_HARNESS = """<!doctype html>
<html lang="zh-Hans">
<head><meta charset="utf-8"><title>leave-guard harness</title></head>
<body data-msg-dirty="有未保存的修改，离开后会丢失。确定离开？">
<form data-target-form data-leave-guard
      action="/targets"
      data-probe-url="/targets/probe"
      data-probe-timeout-ms="5000"
      data-gate-baseline="none"
      data-gate-hint-pending="请先测试连接"
      data-gate-hint-clean="已通过连接测试，可以保存。"
      data-gate-hint-saved="连接未修改，可以直接保存。"
      data-gate-hint-dirty="配置已修改，请重新测试连接。"
      data-probe-ok-title="连接测试通过"
      data-probe-fail-title="连接测试失败"
      data-duration-label="耗时">
  <input type="hidden" name="_csrf" value="token">
  <input name="host" value="127.0.0.1">
  <input name="port" value="6379">
  <input name="protocol" value="2">
  <div class="probe-result" data-probe-result hidden>
    <div class="alert" data-probe-alert>
      <span data-probe-icon="ok"></span><span data-probe-icon="fail"></span>
      <strong data-probe-title></strong>
      <span data-probe-detail></span>
      <span data-probe-meta></span>
    </div>
  </div>
  <p data-gate-hint></p>
  <button type="button" data-probe-button data-loading-label="测试中…">测试连接</button>
  <button type="submit" data-save-button data-loading-label="保存中…" disabled aria-disabled="true">保存</button>
</form>
<script>
  window.fetch = async (url) => {
    const isProbe = String(url).indexOf("/probe") !== -1;
    const payload = isProbe
      ? { ok: true, message: "连接测试通过，可以保存。",
          checked_at: "2026-11-05 22:00:00 UTC",
          checked_at_instant: "2026-11-05T22:00:00Z", duration_ms: 12 }
      : { ok: true, message: "已保存", redirect: "about:blank#saved" };
    return { ok: true, headers: { get: () => "application/json; charset=utf-8" },
             json: async () => payload };
  };
</script>
<script src="app.js"></script>
<script>
  // 放在 app.js 之后：本监听排在 app 的 beforeunload 后面，能读到 defaultPrevented。
  window.addEventListener("beforeunload", (event) => {
    const form = document.querySelector("form");
    window.name = JSON.stringify({
      dirty: form ? form.dataset.dirty : null,
      prevented: event.defaultPrevented,
      href: location.href,
    });
  });
</script>
</body>
</html>
"""


def _chrome_binary() -> str | None:
    explicit = os.environ.get("DR_PANDA_CHROME", "").strip()
    if explicit:
        return explicit if Path(explicit).exists() else None
    candidates = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return candidate
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
        found = shutil.which(name)
        if found:
            return found
    return None


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_page(port: int, timeout_s: float = 30.0) -> dict | None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        data = None
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=1) as resp:
                data = json.load(resp)
        except (OSError, ValueError):
            time.sleep(0.2)
        if data is not None:
            pages = [item for item in data if item.get("type") == "page"]
            if pages:
                return pages[0]
    return None


class _Session:
    def __init__(self, ws) -> None:
        self.ws = ws
        self.seq = 0
        self.dialogs: list[str] = []

    def send(self, method: str, params: dict | None = None) -> int:
        self.seq += 1
        self.ws.send(json.dumps({"id": self.seq, "method": method, "params": params or {}}))
        return self.seq

    def cmd(self, method: str, params: dict | None = None) -> dict:
        target = self.send(method, params)
        while True:
            message = json.loads(self.ws.recv(timeout=15))
            if message.get("method") == "Page.javascriptDialogOpening":
                self.dialogs.append(message["params"].get("type", ""))
                self.send("Page.handleJavaScriptDialog", {"accept": True})
                continue
            if message.get("id") == target:
                return message

    def ev(self, expression: str):
        result = self.cmd(
            "Runtime.evaluate",
            {
                "expression": expression,
                "returnByValue": True,
                "awaitPromise": True,
                "userGesture": True,
            },
        )
        payload = result.get("result", {})
        if payload.get("exceptionDetails"):
            return {"error": str(payload["exceptionDetails"].get("text"))}
        return payload.get("result", {}).get("value")

    def load(self, url: str) -> None:
        self.cmd("Page.navigate", {"url": url})
        time.sleep(1.0)


def _run(chrome: str, workdir: Path) -> int:
    (workdir / "harness.html").write_text(_HARNESS, encoding="utf-8")
    shutil.copy2(APP_JS, workdir / "app.js")
    harness_url = (workdir / "harness.html").as_uri()

    port = _free_port()
    proc = subprocess.Popen(
        [
            chrome,
            "--headless=new",
            "--no-sandbox",
            "--disable-setuid-sandbox",
            f"--remote-debugging-port={port}",
            f"--user-data-dir={workdir / 'profile'}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-gpu",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    failures: list[str] = []
    try:
        page = _wait_page(port)
        if page is None:
            print("FAIL: Chrome 调试端口未就绪")
            return 1
        ws = _ws_connect(page["webSocketDebuggerUrl"], max_size=2**24)
        with ws:
            session = _Session(ws)
            session.cmd("Page.enable")
            session.cmd("Runtime.enable")

            # 场景 A：改字段 → 测试连接 → 保存
            session.load(harness_url)
            session.dialogs.clear()
            session.ev(
                "(() => { const f = document.querySelector('form');"
                " const h = f.querySelector('[name=host]');"
                " h.value = '10.0.0.9';"
                " h.dispatchEvent(new Event('input', { bubbles: true }));"
                " f.querySelector('[data-probe-button]').click(); })()"
            )
            time.sleep(0.6)
            session.ev("document.querySelector('[data-save-button]').click()")
            time.sleep(1.2)
            href = session.ev("location.href")
            record = session.ev("window.name")
            print("A 保存后 URL:", href)
            print("A beforeunload 记录:", record)
            print("A 弹窗事件:", session.dialogs)
            if href != "about:blank#saved":
                failures.append("A: 保存后没有按 redirect 跳转")
            if "prevented\":false" not in str(record) or "dirty" in str(record):
                failures.append("A: beforeunload 仍把保存当成未保存修改（dirty 未清）")
            if session.dialogs:
                failures.append("A: 保存后出现了 beforeunload 弹窗")

            # 场景 B：阳性对照（显式置 dirty 后直接跳转）
            session.load(harness_url)
            session.dialogs.clear()
            session.ev(
                "(() => { const f = document.querySelector('form');"
                " const h = f.querySelector('[name=host]');"
                " h.value = '10.0.0.9';"
                " h.dispatchEvent(new Event('input', { bubbles: true }));"
                " window.location.assign('about:blank#control'); })()"
            )
            time.sleep(1.2)
            control = session.ev("window.name")
            print("B 对照 beforeunload:", control)
            print("B 对照弹窗事件:", session.dialogs)
            if "prevented\":true" not in str(control):
                failures.append("B: 未保存修改没有拦截（对照失效）")

            # 场景 C：改字段再改回原值应撤销 dirty
            session.load(harness_url)
            marked = session.ev(
                "(() => { const f = document.querySelector('form');"
                " const h = f.querySelector('[name=host]');"
                " h.value = '10.0.0.9';"
                " h.dispatchEvent(new Event('input', { bubbles: true }));"
                " return String(f.dataset.dirty); })()"
            )
            reverted = session.ev(
                "(() => { const f = document.querySelector('form');"
                " const h = f.querySelector('[name=host]');"
                " h.value = '127.0.0.1';"
                " h.dispatchEvent(new Event('input', { bubbles: true }));"
                " return String(f.dataset.dirty); })()"
            )
            print("C 改后 dirty:", marked, "改回后:", reverted)
            if marked != "1" or reverted != "undefined":
                failures.append("C: 改回原值后 dirty 未撤销")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()

    if failures:
        print("\nFAIL")
        for item in failures:
            print(" -", item)
        return 1
    print("\nPASS: 保存不再触发「离开此网站」，未保存修改仍会被拦截")
    return 0


def main() -> int:
    chrome = _chrome_binary()
    if chrome is None:
        print("SKIP: 未找到 Chrome（可用 DR_PANDA_CHROME 指定路径）")
        return 0
    if _ws_connect is None:
        print("SKIP: 未安装 websockets")
        return 0
    workdir = Path(tempfile.mkdtemp(prefix="drpanda-leave-guard-"))
    try:
        return _run(chrome, workdir)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
