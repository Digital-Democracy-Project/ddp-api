"""Pytest configuration and fixtures for DDP-API tests."""

import os
import pytest

# Set test environment variables before any imports
os.environ["API_BEARER_TOKEN"] = "testtoken"
os.environ["API_READ_ONLY_TOKEN"] = "readonlytoken"
os.environ["VOTEBOT_SERVICE_URL"] = "http://localhost:8000"
os.environ["VOTEBOT_WS_URL"] = "ws://localhost:8000/ws/chat"
os.environ["VOTEBOT_API_KEY"] = "test-votebot-key"


@pytest.fixture
def test_client():
    """Create a test client for the FastAPI app."""
    from fastapi.testclient import TestClient
    from app.main import app

    return TestClient(app)


@pytest.fixture
def auth_headers():
    """Return write-access authentication headers."""
    return {"Authorization": "Bearer testtoken"}


@pytest.fixture
def read_only_headers():
    """Return read-only authentication headers."""
    return {"Authorization": "Bearer readonlytoken"}
