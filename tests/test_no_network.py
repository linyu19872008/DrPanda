from __future__ import annotations

import socket

import pytest

from dr_panda_mcp import errors
from dr_panda_mcp.catalog import Catalog
from dr_panda_mcp.guards import (
    cls as cls_guard,
)
from dr_panda_mcp.guards import (
    es as es_guard,
)
from dr_panda_mcp.guards import (
    gitlab as gitlab_guard,
)
from dr_panda_mcp.guards import (
    kafka as kafka_guard,
)
from dr_panda_mcp.guards import (
    mongo as mongo_guard,
)
from dr_panda_mcp.guards import (
    mysql as mysql_guard,
)
from dr_panda_mcp.guards import (
    rabbit as rabbit_guard,
)
from dr_panda_mcp.guards import (
    redis as redis_guard,
)
from dr_panda_mcp.guards.protocol import guard_rejected
from tests.fakes import FakeConnector, FakeStore, make_target


@pytest.fixture
def block_sockets(monkeypatch: pytest.MonkeyPatch) -> None:
    def blocked(*args, **kwargs):
        raise AssertionError("闸门路径不应建立网络连接")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)


def test_all_guards_run_offline(block_sockets: None) -> None:
    assert mysql_guard.check_sql("SELECT 1").allowed is True
    assert mysql_guard.check_sql("UPDATE orders SET a = 1").allowed is False
    assert mongo_guard.check_mongo_command("ping", {}).allowed is True
    assert mongo_guard.check_mongo_command("find", {}).allowed is False
    assert es_guard.check_http("GET", "/_cluster/health").allowed is True
    assert es_guard.check_http("PUT", "/orders").allowed is False
    assert redis_guard.check_redis("PING").allowed is True
    assert redis_guard.check_redis("SET", ["k", "v"]).allowed is False
    assert gitlab_guard.check_gitlab("GET", "/api/v4/user").allowed is True
    assert gitlab_guard.check_gitlab("POST", "/api/v4/projects/1/issues").allowed is False
    assert rabbit_guard.check_rabbit("GET", "/api/overview").allowed is True
    assert rabbit_guard.check_rabbit("POST", "/api/exchanges/x/publish").allowed is False
    assert kafka_guard.check_kafka("describe_cluster", {}).allowed is True
    assert kafka_guard.check_kafka("delete_topics", {}).allowed is False
    assert cls_guard.check_cls("describe_topics", {}).allowed is True
    assert cls_guard.check_cls("upload_log", {}).allowed is False


async def test_rejected_probe_has_no_outbound(block_sockets: None) -> None:
    target = make_target()
    catalog = Catalog(FakeStore([target]))
    connector = FakeConnector(decision=guard_rejected("test.reject", "拒绝"))

    with pytest.raises(errors.GuardRejected):
        await catalog.test_connection(target.name, connector)

    assert connector.created == 0
    assert connector.probes == 0
