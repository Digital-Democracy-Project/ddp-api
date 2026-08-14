"""Tests for restrictions.endpoints enforcement (API-2).

Enforcement is centralized in app/middleware/auth.py's write_auth/read_auth
via _check_endpoint_access() -- every proxied route already depends on one
of those two functions, so a single set of integration tests exercising
/broker, /sync, /trigger, and the Voatz routes is enough to prove the
restriction is applied consistently across the app, not per-route.

Mirrors this repo's existing mock-the-client convention (see
test_broker_proxy.py, test_openstates_proxy.py) -- httpx.AsyncClient is
patched directly rather than using a network-mocking library.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.middleware.auth import _check_endpoint_access


class _FakeKey:
    """Minimal stand-in for ApiKey/_EnvVarKey -- only .restrictions is read."""
    def __init__(self, endpoints=None):
        self.restrictions = {"endpoints": endpoints} if endpoints is not None else {}


# ---------------------------------------------------------------------------
# Unit tests: _check_endpoint_access matching logic
# ---------------------------------------------------------------------------

class TestCheckEndpointAccessUnit:
    def test_no_restriction_allows_any_path(self):
        _check_endpoint_access(_FakeKey(endpoints=None), "/anything")  # must not raise

    def test_empty_restriction_list_allows_any_path(self):
        _check_endpoint_access(_FakeKey(endpoints=[]), "/anything")  # must not raise

    def test_exact_prefix_match_allowed(self):
        _check_endpoint_access(_FakeKey(endpoints=["/broker"]), "/broker")  # must not raise

    def test_sub_path_match_allowed(self):
        _check_endpoint_access(_FakeKey(endpoints=["/broker"]), "/broker/api/concept-statements/")

    def test_unrelated_path_rejected(self):
        with pytest.raises(HTTPException) as exc:
            _check_endpoint_access(_FakeKey(endpoints=["/broker"]), "/sync/bills")
        assert exc.value.status_code == 403

    def test_false_prefix_is_not_a_match(self):
        """"/broker" must not match "/brokerage" -- path-prefix, not string-prefix."""
        with pytest.raises(HTTPException) as exc:
            _check_endpoint_access(_FakeKey(endpoints=["/broker"]), "/brokerage/x")
        assert exc.value.status_code == 403

    def test_trailing_slash_in_restriction_is_normalized(self):
        _check_endpoint_access(_FakeKey(endpoints=["/broker/"]), "/broker/api/x")  # must not raise

    def test_multiple_prefixes_use_or_semantics(self):
        key = _FakeKey(endpoints=["/broker", "/sync"])
        _check_endpoint_access(key, "/broker/x")  # must not raise
        _check_endpoint_access(key, "/sync/x")    # must not raise
        with pytest.raises(HTTPException):
            _check_endpoint_access(key, "/trigger/x")


# ---------------------------------------------------------------------------
# Integration helpers
# ---------------------------------------------------------------------------

def _mock_httpx_client(status_code=200, content=b'{"ok": true}', content_type="application/json"):
    fake_response = MagicMock()
    fake_response.status_code = status_code
    fake_response.content = content
    fake_response.headers = {"content-type": content_type}

    mock_client = MagicMock()
    mock_client.request = AsyncMock(return_value=fake_response)

    mock_client_cm = MagicMock()
    mock_client_cm.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client_cm.__aexit__ = AsyncMock(return_value=False)
    return mock_client_cm, mock_client


def _issue_key(test_client, admin_header, scopes, endpoints):
    resp = test_client.post(
        "/admin/keys",
        json={"name": "Restricted", "scopes": scopes, "restrictions": {"endpoints": endpoints}},
        headers=admin_header,
    )
    assert resp.status_code == 200
    return resp.json()["key"]


# ---------------------------------------------------------------------------
# Write-scoped key restricted to /broker
# ---------------------------------------------------------------------------

class TestWriteScopedEndpointRestriction:
    def test_restricted_write_key_allowed_on_its_own_prefix(self, key_store_with_test_keys, test_client):
        admin_h = {"Authorization": f"Bearer {key_store_with_test_keys['admin']}"}
        restricted_key = _issue_key(test_client, admin_h, ["read", "write"], ["/broker"])

        mock_cm, mock_client = _mock_httpx_client(status_code=201, content=b'{"id": 1}')
        with patch("app.routes.broker_proxy.httpx.AsyncClient", return_value=mock_cm):
            resp = test_client.post(
                "/broker/api/concept-statement-sets/",
                headers={"Authorization": f"Bearer {restricted_key}"},
                json={},
            )
        assert resp.status_code == 201
        mock_client.request.assert_called_once()

    def test_restricted_write_key_rejected_on_sync(self, key_store_with_test_keys, test_client):
        admin_h = {"Authorization": f"Bearer {key_store_with_test_keys['admin']}"}
        restricted_key = _issue_key(test_client, admin_h, ["read", "write"], ["/broker"])

        mock_cm, mock_client = _mock_httpx_client()
        with patch("app.routes.ddp_sync_proxy.httpx.AsyncClient", return_value=mock_cm):
            resp = test_client.post(
                "/sync/bills",
                headers={"Authorization": f"Bearer {restricted_key}"},
                json={},
            )
        assert resp.status_code == 403
        mock_client.request.assert_not_called()

    def test_restricted_write_key_rejected_on_trigger(self, key_store_with_test_keys, test_client):
        admin_h = {"Authorization": f"Bearer {key_store_with_test_keys['admin']}"}
        restricted_key = _issue_key(test_client, admin_h, ["read", "write"], ["/broker"])

        mock_cm, mock_client = _mock_httpx_client()
        with patch("app.routes.ddp_sync_proxy.httpx.AsyncClient", return_value=mock_cm):
            resp = test_client.post(
                "/trigger/refresh",
                headers={"Authorization": f"Bearer {restricted_key}"},
                json={},
            )
        assert resp.status_code == 403
        mock_client.request.assert_not_called()

    def test_restricted_write_key_rejected_on_voatz_write_route(self, key_store_with_test_keys, test_client):
        """/create_event requires write_auth -- restriction check must fire before
        the route ever reaches Voatz (no downstream call is made or mocked here)."""
        admin_h = {"Authorization": f"Bearer {key_store_with_test_keys['admin']}"}
        restricted_key = _issue_key(test_client, admin_h, ["read", "write"], ["/broker"])

        resp = test_client.post(
            "/create_event",
            headers={"Authorization": f"Bearer {restricted_key}"},
            json={"organizationId": 1, "WS": "x", "Csrf-Token": "x"},
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Read-scoped key restricted to /broker
# ---------------------------------------------------------------------------

class TestReadScopedEndpointRestriction:
    def test_restricted_read_key_allowed_on_its_own_prefix(self, key_store_with_test_keys, test_client):
        admin_h = {"Authorization": f"Bearer {key_store_with_test_keys['admin']}"}
        restricted_key = _issue_key(test_client, admin_h, ["read"], ["/broker"])

        mock_cm, mock_client = _mock_httpx_client()
        with patch("app.routes.broker_proxy.httpx.AsyncClient", return_value=mock_cm):
            resp = test_client.get(
                "/broker/api/concept-statements/",
                headers={"Authorization": f"Bearer {restricted_key}"},
            )
        assert resp.status_code == 200
        mock_client.request.assert_called_once()

    def test_restricted_read_key_rejected_on_sync(self, key_store_with_test_keys, test_client):
        admin_h = {"Authorization": f"Bearer {key_store_with_test_keys['admin']}"}
        restricted_key = _issue_key(test_client, admin_h, ["read"], ["/broker"])

        mock_cm, mock_client = _mock_httpx_client()
        with patch("app.routes.ddp_sync_proxy.httpx.AsyncClient", return_value=mock_cm):
            resp = test_client.get(
                "/sync/bills",
                headers={"Authorization": f"Bearer {restricted_key}"},
            )
        assert resp.status_code == 403
        mock_client.request.assert_not_called()

    def test_restricted_read_key_rejected_on_voatz(self, key_store_with_test_keys, test_client):
        admin_h = {"Authorization": f"Bearer {key_store_with_test_keys['admin']}"}
        restricted_key = _issue_key(test_client, admin_h, ["read"], ["/broker"])

        resp = test_client.get(
            "/voatz/users/99999",
            headers={"Authorization": f"Bearer {restricted_key}"},
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Regression: keys with no endpoints restriction are unaffected
# ---------------------------------------------------------------------------

class TestUnrestrictedKeysUnaffected:
    def test_unrestricted_write_key_still_reaches_broker(self, auth_headers, test_client):
        mock_cm, mock_client = _mock_httpx_client(status_code=201)
        with patch("app.routes.broker_proxy.httpx.AsyncClient", return_value=mock_cm):
            resp = test_client.post("/broker/api/x", headers=auth_headers, json={})
        assert resp.status_code == 201

    def test_unrestricted_write_key_still_reaches_sync(self, auth_headers, test_client):
        mock_cm, mock_client = _mock_httpx_client()
        with patch("app.routes.ddp_sync_proxy.httpx.AsyncClient", return_value=mock_cm):
            resp = test_client.post("/sync/bills", headers=auth_headers, json={})
        assert resp.status_code == 200

    def test_unrestricted_write_key_still_reaches_trigger(self, auth_headers, test_client):
        mock_cm, mock_client = _mock_httpx_client()
        with patch("app.routes.ddp_sync_proxy.httpx.AsyncClient", return_value=mock_cm):
            resp = test_client.post("/trigger/refresh", headers=auth_headers, json={})
        assert resp.status_code == 200
