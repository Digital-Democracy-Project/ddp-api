"""Tests for the environment tag stamped onto forwarded /sync and /trigger
requests (API-5).

Companion to SYNC-10 (ddp-sync): a dev/prod-tagged key's environment value
is stamped as X-DDP-Environment on the outgoing proxy request so ddp-sync
can route an on-demand LegBot dispatch to the matching ddp-broker-py
instance -- never a value trusted from the caller's own request body.

Mirrors test_endpoint_restrictions.py's integration style: httpx.AsyncClient
is patched directly (this repo's existing mock-the-client convention), and a
single set of tests against /sync and /trigger is enough to prove the header
is stamped consistently by the one shared _forward_to_ddp_sync() call site
both proxy route groups already use.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


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


def _issue_key(test_client, admin_header, scopes, environment):
    resp = test_client.post(
        "/admin/keys",
        json={"name": "Env-tagged", "scopes": scopes, "environment": environment},
        headers=admin_header,
    )
    assert resp.status_code == 200
    return resp.json()["key"]


class TestEnvironmentHeaderStamping:
    def test_dev_tagged_key_stamps_dev_header_on_trigger(self, key_store_with_test_keys, test_client):
        admin_h = {"Authorization": f"Bearer {key_store_with_test_keys['admin']}"}
        dev_key = _issue_key(test_client, admin_h, ["read", "write"], "dev")

        mock_cm, mock_client = _mock_httpx_client()
        with patch("app.routes.ddp_sync_proxy.httpx.AsyncClient", return_value=mock_cm):
            resp = test_client.post(
                "/trigger/legbot-analyze-bill",
                headers={"Authorization": f"Bearer {dev_key}"},
                json={},
            )
        assert resp.status_code == 200
        headers = mock_client.request.call_args.kwargs["headers"]
        assert headers["X-DDP-Environment"] == "dev"

    def test_prod_tagged_key_stamps_prod_header_on_trigger(self, key_store_with_test_keys, test_client):
        admin_h = {"Authorization": f"Bearer {key_store_with_test_keys['admin']}"}
        prod_key = _issue_key(test_client, admin_h, ["read", "write"], "prod")

        mock_cm, mock_client = _mock_httpx_client()
        with patch("app.routes.ddp_sync_proxy.httpx.AsyncClient", return_value=mock_cm):
            resp = test_client.post(
                "/trigger/legbot-analyze-bill",
                headers={"Authorization": f"Bearer {prod_key}"},
                json={},
            )
        assert resp.status_code == 200
        headers = mock_client.request.call_args.kwargs["headers"]
        assert headers["X-DDP-Environment"] == "prod"

    def test_dev_tagged_key_stamps_header_on_sync_too(self, key_store_with_test_keys, test_client):
        """The header is stamped for both /sync and /trigger -- one shared
        _forward_to_ddp_sync() call site backs both proxy route groups."""
        admin_h = {"Authorization": f"Bearer {key_store_with_test_keys['admin']}"}
        dev_key = _issue_key(test_client, admin_h, ["read", "write"], "dev")

        mock_cm, mock_client = _mock_httpx_client()
        with patch("app.routes.ddp_sync_proxy.httpx.AsyncClient", return_value=mock_cm):
            resp = test_client.post(
                "/sync/bills",
                headers={"Authorization": f"Bearer {dev_key}"},
                json={},
            )
        assert resp.status_code == 200
        headers = mock_client.request.call_args.kwargs["headers"]
        assert headers["X-DDP-Environment"] == "dev"

    def test_dev_tagged_read_key_stamps_header_on_get(self, key_store_with_test_keys, test_client):
        admin_h = {"Authorization": f"Bearer {key_store_with_test_keys['admin']}"}
        dev_key = _issue_key(test_client, admin_h, ["read"], "dev")

        mock_cm, mock_client = _mock_httpx_client()
        with patch("app.routes.ddp_sync_proxy.httpx.AsyncClient", return_value=mock_cm):
            resp = test_client.get(
                "/trigger/legbot-analyze-bill/status",
                headers={"Authorization": f"Bearer {dev_key}"},
            )
        assert resp.status_code == 200
        headers = mock_client.request.call_args.kwargs["headers"]
        assert headers["X-DDP-Environment"] == "dev"


class TestUntaggedKeysSendNoHeader:
    """Regression: a key with no environment (existing keys, admin keys,
    env-var tokens) must never send an X-DDP-Environment header at all --
    not an empty string, not the literal "None"."""

    def test_untagged_write_key_sends_no_environment_header(self, auth_headers, test_client):
        mock_cm, mock_client = _mock_httpx_client()
        with patch("app.routes.ddp_sync_proxy.httpx.AsyncClient", return_value=mock_cm):
            resp = test_client.post("/trigger/refresh", headers=auth_headers, json={})
        assert resp.status_code == 200
        headers = mock_client.request.call_args.kwargs["headers"]
        assert "X-DDP-Environment" not in headers

    def test_admin_issued_key_with_no_environment_sends_no_header(self, key_store_with_test_keys, test_client):
        admin_h = {"Authorization": f"Bearer {key_store_with_test_keys['admin']}"}
        resp = test_client.post(
            "/admin/keys",
            json={"name": "No env", "scopes": ["read", "write"]},
            headers=admin_h,
        )
        plain_key = resp.json()["key"]

        mock_cm, mock_client = _mock_httpx_client()
        with patch("app.routes.ddp_sync_proxy.httpx.AsyncClient", return_value=mock_cm):
            resp = test_client.post(
                "/trigger/refresh",
                headers={"Authorization": f"Bearer {plain_key}"},
                json={},
            )
        assert resp.status_code == 200
        headers = mock_client.request.call_args.kwargs["headers"]
        assert "X-DDP-Environment" not in headers
