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
      const dialog = control.closest("dialog");
      // 弹窗已经关闭时不要拦截链接，否则“返回列表”会变成死按钮。
      if (!dialog || !dialog.open) return;
      event.preventDefault();
      dialog.close();
      if (
        control.dataset.dialogClose === "navigate" &&
        control instanceof HTMLAnchorElement
      ) {
        window.location.assign(control.href);
      }
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

  // 渐进增强：提交期间禁用提交按钮，避免重复提交；无 JS 时仍是普通表单。
  document.querySelectorAll("form[data-submit-loading]").forEach((form) => {
    form.addEventListener("submit", () => {
      form.setAttribute("aria-busy", "true");
      form.querySelectorAll('button[type="submit"]').forEach((button) => {
        button.disabled = true;
        if (button.dataset.loadingLabel) button.textContent = button.dataset.loadingLabel;
      });
    });
  });
})();

// 错误页/表单回到浏览器时，把焦点放到第一个错误字段。
(() => {
  const invalid = document.querySelector('[aria-invalid="true"]');
  if (invalid instanceof HTMLElement) invalid.focus();
})();

// TLS 条件显示：仅在启用 TLS 时展示 CA/mTLS 字段。
// 无 JS 时高级区仍显示全部字段，由服务端做最终校验。
(() => {
  const checkbox = document.querySelector('input[name="ssl"], input[name="tls"]');
  const protocol = document.querySelector('select[name="security_protocol"]');
  if (!checkbox && !protocol) return;
  const names = ["ca_pem", "secret_client_cert", "secret_client_key"];
  const fields = names
    .map((name) => document.querySelector(`[name="${name}"]`)?.closest(".field"))
    .filter(Boolean);
  if (!fields.length) return;
  const enabled = () => {
    if (checkbox) return checkbox.checked;
    return protocol?.value === "SSL" || protocol?.value === "SASL_SSL";
  };
  const apply = () => {
    const on = enabled();
    fields.forEach((field) => {
      if (field.querySelector(".field--invalid")) return;
      field.hidden = !on;
    });
  };
  checkbox?.addEventListener("change", apply);
  protocol?.addEventListener("change", apply);
  apply();
})();
