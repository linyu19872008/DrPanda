(() => {
  const openDialog = (id) => {
    const dialog = document.getElementById(id);
    if (!dialog || typeof dialog.showModal !== "function") return false;
    if (dialog.open) dialog.close();
    dialog.showModal();
    return true;
  };

  document.querySelectorAll("[data-dialog-open]").forEach((trigger) => {
    trigger.addEventListener("click", (event) => {
      const id = trigger.dataset.dialogOpen;
      if (!id) return;
      // JS 不可用/不支持 dialog 时保留 href，走无 JS 回退页面。
      if (openDialog(id)) event.preventDefault();
    });
  });

  document.querySelectorAll("[data-dialog-close]").forEach((control) => {
    control.addEventListener("click", (event) => {
      event.preventDefault();
      const dialog = control.closest("dialog");
      if (dialog) dialog.close();
    });
  });

  // 服务端渲染的服务端结果默认带 open，脚本加载后转为真正的 modal。
  document.querySelectorAll("dialog.modal[data-open-on-load]").forEach((dialog) => {
    try {
      dialog.close();
      dialog.showModal();
    } catch (_) {
      // 保留 open 状态，至少内容可读。
    }
  });

  document.querySelectorAll("dialog.modal").forEach((dialog) => {
    dialog.addEventListener("click", (event) => {
      if (event.target === dialog) dialog.close();
    });
  });
})();
