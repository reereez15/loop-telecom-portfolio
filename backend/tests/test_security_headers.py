"""모든 API 응답(성공·실패·차단)에 보안 헤더가 붙는지."""
import pytest

from app.core.security_headers import SECURITY_HEADERS
from tests.conftest import login


def _assert_headers(res):
    for name, value in SECURITY_HEADERS.items():
        assert res.headers.get(name) == value, name
    assert res.headers.get("Cache-Control") == "no-store"


@pytest.mark.parametrize("path", ["/api/health/live", "/api/does-not-exist"])
def test_headers_on_public_responses(client, path):
    _assert_headers(client.get(path))


def test_headers_on_login_success_and_failure(client):
    _assert_headers(client.post("/api/auth/login", json={"email": "alice@test.local", "password": "wrong"}))
    _assert_headers(login(client, "alice@test.local"))


def test_headers_on_unauthenticated_admin_request(client):
    res = client.get("/api/admin/customers")
    assert res.status_code in (401, 403)
    _assert_headers(res)
