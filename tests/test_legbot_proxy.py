"""Tests for the /legbot proxy — on-demand LegBot analyze_bill dispatch (API-4).

Mirrors test_broker_proxy.py's mock-the-client convention -- httpx.AsyncClient
is patched directly rather than using a network-mocking library.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest


def _mock_httpx_client(status_code=200, content=b'{"ok": true}', content_type="application/json"):
    """A MagicMock standing in for httpx.AsyncClient's async-context-manager
    usage in legbot_proxy.py's _forward_to_cams()."""
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


class TestLegBotProxyAuth:
    """Auth gating -- POST (dispatch) requires write; GET (status) accepts read."""

    def test_post_requires_auth(self, test_client):
        res = test_client.post("/legbot/tasks", json={"question_type": "summary_500char"})
        assert res.status_code == 401  # HTTPBearer itself rejects a missing Authorization header

    def test_post_rejects_invalid_token(self, test_client):
        res = test_client.post(
            "/legbot/tasks",
            headers={"Authorization": "Bearer not-a-real-token"},
            json={"question_type": "summary_500char"},
        )
        assert res.status_code == 403

    def test_post_requires_write_scope_not_just_read(self, test_client, read_only_headers):
        res = test_client.post(
            "/legbot/tasks",
            headers=read_only_headers,
            json={"question_type": "summary_500char"},
        )
        assert res.status_code == 403

    def test_get_requires_auth(self, test_client):
        res = test_client.get("/legbot/tasks/abc123")
        assert res.status_code == 401

    def test_get_accepts_read_only_token(self, test_client, read_only_headers):
        mock_cm, mock_client = _mock_httpx_client(content=b'{"status": "queued"}')
        with patch("app.routes.legbot_proxy.httpx.AsyncClient", return_value=mock_cm):
            res = test_client.get("/legbot/tasks/abc123", headers=read_only_headers)
        assert res.status_code == 200
        assert res.json() == {"status": "queued"}


class TestLegBotProxyDispatch:
    """POST /legbot/tasks -- payload shaping and downstream forwarding."""

    def test_injects_bot_and_task_type(self, test_client, auth_headers):
        mock_cm, mock_client = _mock_httpx_client(content=b'{"task_id": "abc123"}')
        with patch("app.routes.legbot_proxy.httpx.AsyncClient", return_value=mock_cm):
            res = test_client.post(
                "/legbot/tasks",
                headers=auth_headers,
                json={"question_type": "summary_500char", "bill_source": "https://example.com/bill.pdf"},
            )
        assert res.status_code == 200
        assert res.json() == {"task_id": "abc123"}

        _, kwargs = mock_client.request.call_args
        assert kwargs["url"] == "/api/v1/tasks"
        assert kwargs["json"]["bot"] == "legbot"
        assert kwargs["json"]["task_type"] == "analyze_bill"

    def test_preserves_caller_payload_and_stamps_caller(self, test_client, auth_headers):
        mock_cm, mock_client = _mock_httpx_client(content=b'{"task_id": "abc123"}')
        with patch("app.routes.legbot_proxy.httpx.AsyncClient", return_value=mock_cm):
            test_client.post(
                "/legbot/tasks",
                headers=auth_headers,
                json={"question_type": "pros_cons", "bill_source": "https://example.com/bill.pdf"},
            )
        _, kwargs = mock_client.request.call_args
        payload = kwargs["json"]["payload"]
        assert payload["question_type"] == "pros_cons"
        assert payload["bill_source"] == "https://example.com/bill.pdf"
        assert payload["caller"] == "ddp_next"

    def test_rejects_missing_question_type(self, test_client, auth_headers):
        res = test_client.post("/legbot/tasks", headers=auth_headers, json={})
        assert res.status_code == 422

    def test_never_forwards_the_callers_own_ddp_api_token(self, test_client, auth_headers):
        """The caller's ddp-api bearer token must never reach CAMS -- only
        this proxy's own held CAMS_API_TOKEN is sent downstream."""
        mock_cm, mock_client = _mock_httpx_client(content=b'{"task_id": "abc123"}')
        with patch("app.routes.legbot_proxy.httpx.AsyncClient", return_value=mock_cm), \
                patch("app.routes.legbot_proxy._get_cams_api_token", return_value="downstream-secret"):
            test_client.post(
                "/legbot/tasks",
                headers=auth_headers,
                json={"question_type": "summary_500char"},
            )
        _, kwargs = mock_client.request.call_args
        assert kwargs["headers"]["Authorization"] == "Bearer downstream-secret"
        assert auth_headers["Authorization"] not in kwargs["headers"].values()


class TestLegBotProxyStatus:
    """GET /legbot/tasks/{task_id} -- verbatim forwarding of CAMS's status response."""

    def test_forwards_to_cams_task_status_path(self, test_client, read_only_headers):
        mock_cm, mock_client = _mock_httpx_client(content=b'{"status": "running"}')
        with patch("app.routes.legbot_proxy.httpx.AsyncClient", return_value=mock_cm):
            test_client.get("/legbot/tasks/abc123", headers=read_only_headers)
        _, kwargs = mock_client.request.call_args
        assert kwargs["url"] == "/api/v1/tasks/abc123"

    def test_returns_cams_response_body_and_status_verbatim(self, test_client, read_only_headers):
        mock_cm, mock_client = _mock_httpx_client(status_code=200, content=b'{"status": "completed"}')
        with patch("app.routes.legbot_proxy.httpx.AsyncClient", return_value=mock_cm):
            res = test_client.get("/legbot/tasks/abc123", headers=read_only_headers)
        assert res.status_code == 200
        assert res.json() == {"status": "completed"}


class TestLegBotProxyErrorMapping:
    """Connect/timeout errors map to 502/504, matching broker_proxy.py's
    existing convention exactly -- not a new error-handling shape."""

    def test_connect_error_returns_502(self, test_client, auth_headers):
        mock_client = MagicMock()
        mock_client.request = AsyncMock(side_effect=httpx.ConnectError("refused"))
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("app.routes.legbot_proxy.httpx.AsyncClient", return_value=mock_cm):
            res = test_client.post(
                "/legbot/tasks", headers=auth_headers, json={"question_type": "summary_500char"},
            )
        assert res.status_code == 502

    def test_read_timeout_returns_504(self, test_client, read_only_headers):
        mock_client = MagicMock()
        mock_client.request = AsyncMock(side_effect=httpx.ReadTimeout("timed out"))
        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("app.routes.legbot_proxy.httpx.AsyncClient", return_value=mock_cm):
            res = test_client.get("/legbot/tasks/abc123", headers=read_only_headers)
        assert res.status_code == 504
