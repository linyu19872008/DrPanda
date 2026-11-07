from __future__ import annotations

from dr_panda_mcp.connectors.cls import _CLSClient
from tests.fakes import make_target


def test_cls_client_uses_http_profile_timeout() -> None:
    target = make_target(
        type_="cls",
        options={"region": "ap-shanghai", "timeout_s": "30"},
        secret={"secret_id": "id", "secret_key": "key"},
    )

    client, _models = _CLSClient(target)._sdk()

    assert client.region == "ap-shanghai"
    assert client.profile.httpProfile.reqTimeout == 30
