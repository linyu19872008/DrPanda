(() => {
  const button = document.getElementById("copy-mcp-token");
  const target = document.getElementById("mcp-token-value");
  const status = document.getElementById("copy-mcp-token-status");
  if (!button || !target || !status) return;

  const value = target.textContent.trim();
  if (!value) return;

  const label = (name, fallback) => button.dataset[name] || fallback;
  const setStatus = (text) => {
    status.textContent = text;
  };

  const selectToken = () => {
    const selection = window.getSelection();
    if (!selection) return false;
    const range = document.createRange();
    range.selectNodeContents(target);
    selection.removeAllRanges();
    selection.addRange(range);
    return true;
  };

  const fallbackCopy = () => {
    const selected = selectToken();
    try {
      if (selected && document.execCommand("copy")) {
        setStatus(label("copied", "Copied"));
        return;
      }
    } catch (_) {
      // fall through to manual instructions
    }
    setStatus(label("selected", "Selected. Press Ctrl/Cmd+C."));
  };

  button.addEventListener("click", async () => {
    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(value);
        setStatus(label("copied", "Copied"));
        return;
      }
    } catch (_) {
      // clipboard permission denied; fall back to selection
    }
    fallbackCopy();
  });

  // 只有脚本成功初始化后才显示按钮，避免出现点击无效的假按钮。
  button.hidden = false;
})();
