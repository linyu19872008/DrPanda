"""Static asset regressions that the ASGI tests cannot execute."""

from __future__ import annotations

from pathlib import Path

APP_JS = Path(__file__).resolve().parents[1] / "src/dr_panda_mcp/web/static/app.js"


def test_form_install_button_is_looked_up_in_main_form() -> None:
    """The install button lives in the main form, not in the hidden install form."""
    source = APP_JS.read_text(encoding="utf-8")

    assert 'const installButton = form.querySelector("[data-probe-install-button]")' in source
    assert 'installForm.querySelector("[data-probe-install-button]")' not in source
