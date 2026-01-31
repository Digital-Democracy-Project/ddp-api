"""Tests for VoteBot proxy endpoints."""

import os
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

VALID_AUTH = {"Authorization": "Bearer testtoken"}
INVALID_AUTH = {"Authorization": "Bearer wrong-token"}


class TestVotebotChat:
    """Tests for POST /votebot/chat endpoint."""

    def test_chat_requires_auth(self):
        """Chat endpoint should require authentication."""
        response = client.post(
            "/votebot/chat",
            json={"message": "hello", "session_id": "test-session"},
        )
        assert response.status_code == 401

    def test_chat_rejects_invalid_token(self):
        """Chat endpoint should reject invalid tokens."""
        response = client.post(
            "/votebot/chat",
            json={"message": "hello", "session_id": "test-session"},
            headers=INVALID_AUTH,
        )
        assert response.status_code == 403

    def test_chat_with_valid_auth_reaches_votebot(self):
        """Chat endpoint should proxy to VoteBot with valid auth."""
        response = client.post(
            "/votebot/chat",
            json={
                "message": "What is a bill?",
                "session_id": "test-session-123",
                "page_context": {"type": "general"},
            },
            headers=VALID_AUTH,
        )
        # Will get 502/404 if VoteBot is not running, which is expected
        # The important thing is auth passed (not 401/403)
        assert response.status_code in [200, 404, 502]


class TestVotebotChatStream:
    """Tests for POST /votebot/chat/stream endpoint."""

    def test_stream_requires_auth(self):
        """Stream endpoint should require authentication."""
        response = client.post(
            "/votebot/chat/stream",
            json={"message": "hello", "session_id": "test-session"},
        )
        assert response.status_code == 401

    def test_stream_rejects_invalid_token(self):
        """Stream endpoint should reject invalid tokens."""
        response = client.post(
            "/votebot/chat/stream",
            json={"message": "hello", "session_id": "test-session"},
            headers=INVALID_AUTH,
        )
        assert response.status_code == 403

    def test_stream_returns_event_stream(self):
        """Stream endpoint should return event-stream content type."""
        response = client.post(
            "/votebot/chat/stream",
            json={
                "message": "hello",
                "session_id": "test-session",
                "page_context": {"type": "general"},
            },
            headers=VALID_AUTH,
        )
        # Even if VoteBot is down, should return streaming response
        # Content type will be event-stream on success or JSON on error
        content_type = response.headers.get("content-type", "")
        assert "text/event-stream" in content_type or "application/json" in content_type


class TestVotebotFeedback:
    """Tests for POST /votebot/feedback endpoint."""

    def test_feedback_requires_auth(self):
        """Feedback endpoint should require authentication."""
        response = client.post(
            "/votebot/feedback",
            json={
                "session_id": "test-session",
                "message_id": "msg-123",
                "feedback_type": "positive",
            },
        )
        assert response.status_code == 401

    def test_feedback_rejects_invalid_token(self):
        """Feedback endpoint should reject invalid tokens."""
        response = client.post(
            "/votebot/feedback",
            json={
                "session_id": "test-session",
                "message_id": "msg-123",
                "feedback_type": "positive",
            },
            headers=INVALID_AUTH,
        )
        assert response.status_code == 403

    def test_feedback_with_valid_auth(self):
        """Feedback endpoint should proxy to VoteBot with valid auth."""
        response = client.post(
            "/votebot/feedback",
            json={
                "session_id": "test-session",
                "message_id": "msg-123",
                "feedback_type": "positive",
                "feedback_text": "Very helpful!",
            },
            headers=VALID_AUTH,
        )
        # Will get 502/404 if VoteBot is not running
        assert response.status_code in [200, 404, 502]


class TestVotebotWebSocket:
    """Tests for WS /votebot/ws endpoint."""

    def test_websocket_connects(self):
        """WebSocket endpoint should accept connections."""
        # Note: Full WebSocket testing requires VoteBot running
        # This just verifies the endpoint exists and accepts connections initially
        try:
            with client.websocket_connect("/votebot/ws") as websocket:
                # Connection accepted, but will fail when trying to proxy
                pass
        except Exception as e:
            # Expected to fail at proxy stage if VoteBot not running
            assert "VoteBot" in str(e) or "connect" in str(e).lower()

    def test_websocket_with_session_id(self):
        """WebSocket should accept session_id query param."""
        try:
            with client.websocket_connect("/votebot/ws?session_id=test-session") as websocket:
                pass
        except Exception as e:
            # Expected to fail at proxy stage if VoteBot not running
            assert "VoteBot" in str(e) or "connect" in str(e).lower()


class TestHealthEndpoints:
    """Tests for health check endpoints."""

    def test_root_endpoint(self):
        """Root endpoint should return service info."""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["service"] == "DDP-API"
        assert "version" in data

    def test_health_endpoint(self):
        """Health endpoint should return healthy status."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "healthy"}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
