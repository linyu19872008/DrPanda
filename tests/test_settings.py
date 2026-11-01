from __future__ import annotations

import logging

import pytest

from dr_panda_mcp import settings
from dr_panda_mcp.errors import InvalidSettings
from dr_panda_mcp.store.protocol import Settings


class StubStore:
    """只实现系统配置读写的假仓储。"""

    def __init__(self, values: dict[str, str] | None = None) -> None:
        self.values = dict(values or {})
        self.updated: tuple[dict[str, str], str] | None = None

    async def get_settings(self) -> dict[str, str]:
        return dict(self.values)

    async def update_settings(
        self, patch: dict[str, str], actor: str
    ) -> dict[str, str]:
        self.updated = (dict(patch), actor)
        self.values.update(patch)
        return dict(self.values)


def test_validate_patch_accepts_valid_values() -> None:
    assert settings.validate_patch(
        {"audit_retention_days": "30", "target_max_concurrency": "5"}
    ) == {"audit_retention_days": "30", "target_max_concurrency": "5"}


@pytest.mark.parametrize(
    "patch",
    [
        {},
        {"audit_retention_days": "0"},
        {"audit_retention_days": "3651"},
        {"audit_retention_days": "abc"},
        {"target_max_concurrency": "0"},
        {"target_max_concurrency": "51"},
        {"readonly": "false"},
    ],
)
def test_validate_patch_rejects_invalid(patch: dict[str, str]) -> None:
    with pytest.raises(InvalidSettings):
        settings.validate_patch(patch)


async def test_load_returns_defaults_for_missing_keys() -> None:
    result = await settings.load(StubStore())

    assert result == Settings(audit_retention_days=90, target_max_concurrency=10)


async def test_load_falls_back_on_invalid_stored_value(caplog) -> None:
    store = StubStore({"audit_retention_days": "9999", "target_max_concurrency": "5"})
    with caplog.at_level(logging.WARNING):
        result = await settings.load(store)

    assert result == Settings(audit_retention_days=90, target_max_concurrency=5)
    assert "已回退默认值" in caplog.text


async def test_update_validates_before_writing() -> None:
    store = StubStore()

    result = await settings.update(store, {"audit_retention_days": "30"}, "anonymous")

    assert result == Settings(audit_retention_days=30, target_max_concurrency=10)
    assert store.updated == ({"audit_retention_days": "30"}, "anonymous")


async def test_update_rejects_invalid_without_writing() -> None:
    store = StubStore()

    with pytest.raises(InvalidSettings):
        await settings.update(store, {"target_max_concurrency": "0"}, "anonymous")

    assert store.updated is None
