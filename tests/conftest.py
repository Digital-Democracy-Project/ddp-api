"""Pytest configuration and fixtures for DDP-API tests."""

import hashlib
import json
import os
import pytest

# Set test environment variables before any imports.
# These env-var tokens exercise the backward-compat fallback path in auth.py.
os.environ["API_BEARER_TOKEN"] = "testtoken"
os.environ["API_READ_ONLY_TOKEN"] = "readonlytoken"
os.environ["VOTEBOT_SERVICE_URL"] = "http://localhost:8000"
os.environ["VOTEBOT_WS_URL"] = "ws://localhost:8000/ws/chat"
os.environ["VOTEBOT_API_KEY"] = "test-votebot-key"


@pytest.fixture
def test_client():
    """Create a test client for the FastAPI app.

    Uses TestClient as a context manager so the lifespan (startup/shutdown)
    runs correctly. When used alongside key_store_with_test_keys, list that
    fixture first in the test signature so the temp config is in place before
    the lifespan starts.
    """
    import config as cfg_module
    import app.services.key_store as ks_module
    cfg_module._config   = None
    ks_module._key_store = None

    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as client:
        yield client

    # Reset singletons after test to avoid cross-test pollution
    cfg_module._config   = None
    ks_module._key_store = None


@pytest.fixture
def auth_headers():
    """Return write-access authentication headers (env-var token)."""
    return {"Authorization": "Bearer testtoken"}


@pytest.fixture
def read_only_headers():
    """Return read-only authentication headers (env-var token)."""
    return {"Authorization": "Bearer readonlytoken"}


@pytest.fixture
def key_store_with_test_keys(tmp_path, monkeypatch):
    """
    Inject a temporary local config with read, write, and admin test keys.

    Resets the config and key store singletons so they load from the temp file.
    Returns a dict of plaintext keys: {"read": ..., "write": ..., "admin": ...}.
    """
    read_plaintext  = "ddp-ro-testreadkey"
    write_plaintext = "ddp-rw-testwritekey"
    admin_plaintext = "ddp-admin-testadminkey"

    config = {
        "organizations": [
            {
                "name": "Test Org",
                "voatz_org_id": 99999,
                "voatz_email": "test@example.com",
                "voatz_password": "pass",
                "brevo_list_id": 1,
            }
        ],
        "api_keys": [
            {
                "id":           "key_testread",
                "name":         "Test read",
                "key_hash":     hashlib.sha256(read_plaintext.encode()).hexdigest(),
                "prefix":       "ddp-ro",
                "scopes":       ["read"],
                "restrictions": {},
                "created_at":   "2026-01-01T00:00:00Z",
                "expires_at":   None,
                "last_used_at": None,
            },
            {
                "id":           "key_testwrite",
                "name":         "Test write",
                "key_hash":     hashlib.sha256(write_plaintext.encode()).hexdigest(),
                "prefix":       "ddp-rw",
                "scopes":       ["read", "write"],
                "restrictions": {},
                "created_at":   "2026-01-01T00:00:00Z",
                "expires_at":   None,
                "last_used_at": None,
            },
            {
                "id":           "key_testadmin",
                "name":         "Test admin",
                "key_hash":     hashlib.sha256(admin_plaintext.encode()).hexdigest(),
                "prefix":       "ddp-admin",
                "scopes":       ["admin"],
                "restrictions": {},
                "created_at":   "2026-01-01T00:00:00Z",
                "expires_at":   None,
                "last_used_at": None,
            },
        ],
    }

    config_file = tmp_path / "config.test.json"
    config_file.write_text(json.dumps(config))

    import config as cfg_module
    import app.services.key_store as ks_module

    # config.LOCAL_CONFIG_PATH is a module-level constant (evaluated at import
    # time), so monkeypatch.setenv alone won't update it. Set it directly.
    original_path         = cfg_module.LOCAL_CONFIG_PATH
    cfg_module.LOCAL_CONFIG_PATH = str(config_file)
    cfg_module._config    = None
    ks_module._key_store  = None

    yield {
        "read":  read_plaintext,
        "write": write_plaintext,
        "admin": admin_plaintext,
    }

    # Cleanup
    cfg_module.LOCAL_CONFIG_PATH = original_path
    cfg_module._config    = None
    ks_module._key_store  = None
