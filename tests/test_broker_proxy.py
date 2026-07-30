"""Tests for the /broker/* catch-all proxy to production ddp-broker-py.

Mirrors this repo's existing mock-the-client convention (see test_webflow.py) --
httpx.AsyncClient is patched directly rather than using a network-mocking
library, since none is already a dependency here.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest


def _mock_httpx_client(status_code=200, content=b'{"ok": true}', content_type="application/json"):
    """A MagicMock standing in for httpx.AsyncClient's async-context-manager
    usage in broker_proxy.py's _forward()."""
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


class TestBrokerProxyAuth:
    """Auth gating -- same read/write scope split as ddp_sync_proxy.py."""

    def test_get_requires_read_auth(self, test_client):
        res = test_client.get("/broker/api/concept-statements/")
        assert res.status_code == 401  # HTTPBearer itself rejects a missing Authorization header

    def test_get_rejects_invalid_token(self, test_client):
        res = test_client.get(
            "/broker/api/concept-statements/",
            headers={"Authorization": "Bearer not-a-real-token"},
        )
        assert res.status_code == 403

    def test_post_requires_write_scope_not_just_read(self, test_client, read_only_headers):
        res = test_client.post(
            "/broker/api/concept-statement-sets/",
            headers=read_only_headers,
            json={},
        )
        assert res.status_code == 403

    def test_post_with_write_token_reaches_the_proxy(self, test_client, auth_headers):
        mock_cm, mock_client = _mock_httpx_client(status_code=201, content=b'{"id": 1}')
        with patch("app.routes.broker_proxy.httpx.AsyncClient", return_value=mock_cm):
            res = test_client.post(
                "/broker/api/concept-statement-sets/",
                headers=auth_headers,
                json={"gov_id": "HB1", "jurisdiction_iso2": "UT", "session_code": "2025",
                      "statements": ["A statement."]},
            )
        assert res.status_code == 201
        assert res.json() == {"id": 1}


class TestBrokerProxyForwarding:
    """Forwarding behavior: verbatim path, verbatim body, this proxy's own token."""

    def test_forwards_path_verbatim_after_broker_prefix(self, test_client, auth_headers):
        mock_cm, mock_client = _mock_httpx_client()
        with patch("app.routes.broker_proxy.httpx.AsyncClient", return_value=mock_cm) as MockAsyncClient:
            test_client.post(
                "/broker/api/concept-statement-sets/",
                headers=auth_headers,
                json={},
            )
        # base_url is the configured EC2_BROKER_SERVICE_URL; the request path
        # is the exact remainder after /broker/, unprefixed and unmodified.
        _, kwargs = mock_client.request.call_args
        assert kwargs["url"] == "/api/concept-statement-sets/"

    def test_never_forwards_the_callers_own_ddp_api_token(self, test_client, auth_headers):
        """The caller's ddp-api bearer token must never reach ddp-broker-py --
        only this proxy's own held DDP_BROKER_API_TOKEN is sent downstream."""
        mock_cm, mock_client = _mock_httpx_client()
        with patch("app.routes.broker_proxy.httpx.AsyncClient", return_value=mock_cm), \
                patch("app.routes.broker_proxy._get_ddp_broker_api_token", return_value="downstream-secret"):
            test_client.post(
                "/broker/api/concept-statement-sets/",
                headers=auth_headers,
                json={},
            )
        _, kwargs = mock_client.request.call_args
        assert kwargs["headers"]["Authorization"] == "Bearer downstream-secret"
        assert auth_headers["Authorization"] not in kwargs["headers"].values()

    def test_get_body_and_status_code_passed_through_verbatim(self, test_client, read_only_headers):
        mock_cm, mock_client = _mock_httpx_client(
            status_code=200, content=b'{"found": false}', content_type="application/json",
        )
        with patch("app.routes.broker_proxy.httpx.AsyncClient", return_value=mock_cm):
            res = test_client.get(
                "/broker/api/concept-statements/?jurisdiction=UT&session=2025&gov_id=HB1",
                headers=read_only_headers,
            )
        assert res.status_code == 200
        assert res.json() == {"found": False}

    def test_get_forwards_query_params(self, test_client, read_only_headers):
        mock_cm, mock_client = _mock_httpx_client()
        with patch("app.routes.broker_proxy.httpx.AsyncClient", return_value=mock_cm):
            test_client.get(
                "/broker/api/concept-statements/?jurisdiction=UT&session=2025&gov_id=HB1",
                headers=read_only_headers,
            )
        _, kwargs = mock_client.request.call_args
        assert dict(kwargs["params"]) == {
            "jurisdiction": "UT", "session": "2025", "gov_id": "HB1",
        }


class TestBrokerProxyErrorMapping:
    """Connect/timeout errors map to 502/504, matching ddp_sync_proxy.py's
    existing convention exactly -- not a new error-handling shape."""

    def test_connect_error_returns_502(self, test_client, auth_headers):
        mock_client = MagicMock()
        mock_client.request = AsyncMock(side_effect=httpx.ConnectError("refused"))
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("app.routes.broker_proxy.httpx.AsyncClient", return_value=mock_cm):
            res = test_client.post(
                "/broker/api/concept-statement-sets/", headers=auth_headers, json={},
            )
        assert res.status_code == 502

    def test_read_timeout_returns_504(self, test_client, auth_headers):
        mock_client = MagicMock()
        mock_client.request = AsyncMock(side_effect=httpx.ReadTimeout("timed out"))
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("app.routes.broker_proxy.httpx.AsyncClient", return_value=mock_cm):
            res = test_client.post(
                "/broker/api/concept-statement-sets/", headers=auth_headers, json={},
            )
        assert res.status_code == 504
