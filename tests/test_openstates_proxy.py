"""Tests for the /openstates/* catch-all proxy to DDP's self-hosted api-v3 (OPEN-39).

Mirrors test_broker_proxy.py's mock-the-client convention -- httpx.AsyncClient is
patched directly rather than using a network-mocking library.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest


def _mock_httpx_client(status_code=200, content=b'{"ok": true}', content_type="application/json"):
    """A MagicMock standing in for httpx.AsyncClient's async-context-manager
    usage in openstates_proxy.py's _forward(). `request` accepts a `side_effect`
    override so callers can simulate a ConnectError followed by a real response."""
    fake_response = MagicMock()
    fake_response.status_code = status_code
    fake_response.content = content
    fake_response.headers = {"content-type": content_type}

    mock_client = MagicMock()
    mock_client.request = AsyncMock(return_value=fake_response)

    mock_client_cm = MagicMock()
    mock_client_cm.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client_cm.__aexit__ = AsyncMock(return_value=False)
    return mock_client_cm, mock_client, fake_response


class TestOpenstatesProxyAuth:
    """Auth gating -- same read/write scope split as broker_proxy.py, except healthz."""

    def test_get_requires_read_auth(self, test_client):
        res = test_client.get("/openstates/bills")
        assert res.status_code == 401

    def test_get_rejects_invalid_token(self, test_client):
        res = test_client.get(
            "/openstates/bills", headers={"Authorization": "Bearer not-a-real-token"},
        )
        assert res.status_code == 403

    def test_post_requires_write_scope_not_just_read(self, test_client, read_only_headers):
        res = test_client.post("/openstates/bills", headers=read_only_headers, json={})
        assert res.status_code == 403

    def test_get_with_read_token_reaches_the_proxy(self, test_client, read_only_headers):
        mock_cm, mock_client, _ = _mock_httpx_client()
        with patch("app.routes.openstates_proxy.httpx.AsyncClient", return_value=mock_cm):
            res = test_client.get("/openstates/bills", headers=read_only_headers)
        assert res.status_code == 200


class TestOpenstatesHealthzPassthrough:
    """OPEN-39 AC1: /openstates/healthz needs no ddp-api token."""

    def test_healthz_requires_no_auth(self, test_client):
        mock_cm, mock_client, _ = _mock_httpx_client(status_code=200, content=b'"OK"')
        with patch("app.routes.openstates_proxy.httpx.AsyncClient", return_value=mock_cm):
            res = test_client.get("/openstates/healthz")
        assert res.status_code == 200

    def test_healthz_forwards_to_api_v3_healthz_path(self, test_client):
        mock_cm, mock_client, _ = _mock_httpx_client(status_code=200, content=b'"OK"')
        with patch("app.routes.openstates_proxy.httpx.AsyncClient", return_value=mock_cm):
            test_client.get("/openstates/healthz")
        _, kwargs = mock_client.request.call_args
        assert kwargs["url"] == "/healthz"

    def test_healthz_does_not_shadow_authenticated_catch_all(self, test_client, read_only_headers):
        """Registration-order guard: adding the healthz route must not swallow
        every other /openstates/* path into the unauthenticated handler."""
        res = test_client.get("/openstates/bills")
        assert res.status_code == 401  # still auth-gated, not silently 200/404 via healthz


class TestOpenstatesProxyRetry:
    """OPEN-39 AC2: a single bounded retry on ConnectError, nothing more."""

    def test_connect_error_then_success_is_retried_transparently(self, test_client, read_only_headers):
        fake_response = MagicMock()
        fake_response.status_code = 200
        fake_response.content = b'{"results": []}'
        fake_response.headers = {"content-type": "application/json"}

        mock_client = MagicMock()
        mock_client.request = AsyncMock(
            side_effect=[httpx.ConnectError("refused"), fake_response],
        )
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("app.routes.openstates_proxy.httpx.AsyncClient", return_value=mock_cm), \
                patch("app.routes.openstates_proxy.asyncio.sleep", new=AsyncMock()):
            res = test_client.get("/openstates/bills", headers=read_only_headers)

        assert res.status_code == 200
        assert res.json() == {"results": []}
        assert mock_client.request.call_count == 2

    def test_connect_error_twice_returns_502_and_stops_retrying(self, test_client, read_only_headers):
        mock_client = MagicMock()
        mock_client.request = AsyncMock(side_effect=httpx.ConnectError("refused"))
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("app.routes.openstates_proxy.httpx.AsyncClient", return_value=mock_cm), \
                patch("app.routes.openstates_proxy.asyncio.sleep", new=AsyncMock()):
            res = test_client.get("/openstates/bills", headers=read_only_headers)

        assert res.status_code == 502
        # Exactly one retry -- bounded, not unbounded backoff.
        assert mock_client.request.call_count == 2

    def test_read_timeout_is_not_retried(self, test_client, read_only_headers):
        """ReadTimeout maps straight to 504, same as before OPEN-39 -- only
        ConnectError gets the bounded retry."""
        mock_client = MagicMock()
        mock_client.request = AsyncMock(side_effect=httpx.ReadTimeout("timed out"))
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("app.routes.openstates_proxy.httpx.AsyncClient", return_value=mock_cm):
            res = test_client.get("/openstates/bills", headers=read_only_headers)

        assert res.status_code == 504
        assert mock_client.request.call_count == 1


class TestOpenstatesProxyErrorMapping:
    """Unchanged error mapping for non-retry paths, matching broker_proxy.py's convention."""

    def test_read_timeout_returns_504(self, test_client, read_only_headers):
        mock_client = MagicMock()
        mock_client.request = AsyncMock(side_effect=httpx.ReadTimeout("timed out"))
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("app.routes.openstates_proxy.httpx.AsyncClient", return_value=mock_cm):
            res = test_client.get("/openstates/bills", headers=read_only_headers)
        assert res.status_code == 504
