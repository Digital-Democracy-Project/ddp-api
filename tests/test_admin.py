"""Admin endpoint and key management tests."""

import pytest


# ---------------------------------------------------------------------------
# Scope enforcement
# ---------------------------------------------------------------------------

def test_admin_endpoints_reject_unauthenticated(test_client):
    # HTTPBearer returns 401 when no Authorization header is present
    assert test_client.get("/admin/keys").status_code == 401
    assert test_client.post("/admin/keys", json={"name": "x", "scopes": ["read"]}).status_code == 401


def test_admin_endpoints_reject_read_key(key_store_with_test_keys, test_client):
    keys = key_store_with_test_keys
    h = {"Authorization": f"Bearer {keys['read']}"}
    assert test_client.get("/admin/keys", headers=h).status_code == 403
    assert test_client.post("/admin/keys", json={"name": "x", "scopes": ["read"]}, headers=h).status_code == 403


def test_admin_endpoints_reject_write_key(key_store_with_test_keys, test_client):
    keys = key_store_with_test_keys
    h = {"Authorization": f"Bearer {keys['write']}"}
    assert test_client.get("/admin/keys", headers=h).status_code == 403
    assert test_client.post("/admin/keys", json={"name": "x", "scopes": ["read"]}, headers=h).status_code == 403


# ---------------------------------------------------------------------------
# Key issuance
# ---------------------------------------------------------------------------

def test_issue_read_key(key_store_with_test_keys, test_client):
    keys = key_store_with_test_keys
    h    = {"Authorization": f"Bearer {keys['admin']}"}
    resp = test_client.post("/admin/keys", json={"name": "Test read", "scopes": ["read"]}, headers=h)
    assert resp.status_code == 200
    body = resp.json()
    assert body["key"].startswith("ddp-ro-")
    assert body["scopes"] == ["read"]
    assert "will not be shown again" in body["message"]


def test_issue_write_key(key_store_with_test_keys, test_client):
    keys = key_store_with_test_keys
    h    = {"Authorization": f"Bearer {keys['admin']}"}
    resp = test_client.post("/admin/keys", json={"name": "Test write", "scopes": ["read", "write"]}, headers=h)
    assert resp.status_code == 200
    assert resp.json()["key"].startswith("ddp-rw-")


def test_issue_admin_key(key_store_with_test_keys, test_client):
    keys = key_store_with_test_keys
    h    = {"Authorization": f"Bearer {keys['admin']}"}
    resp = test_client.post("/admin/keys", json={"name": "Test admin", "scopes": ["admin"]}, headers=h)
    assert resp.status_code == 200
    assert resp.json()["key"].startswith("ddp-admin-")


def test_issued_read_key_authenticates_on_read_endpoint(key_store_with_test_keys, test_client):
    keys  = key_store_with_test_keys
    h     = {"Authorization": f"Bearer {keys['admin']}"}
    issue = test_client.post("/admin/keys", json={"name": "Temp", "scopes": ["read"]}, headers=h)
    new_key = issue.json()["key"]
    resp = test_client.get("/health", headers={"Authorization": f"Bearer {new_key}"})
    assert resp.status_code == 200


def test_issued_read_key_rejected_on_write_endpoint(key_store_with_test_keys, test_client):
    keys  = key_store_with_test_keys
    h     = {"Authorization": f"Bearer {keys['admin']}"}
    issue = test_client.post("/admin/keys", json={"name": "Temp", "scopes": ["read"]}, headers=h)
    new_key = issue.json()["key"]
    # /create_event requires write scope
    resp = test_client.post(
        "/create_event",
        json={"organizationId": 1, "WS": "x", "Csrf-Token": "x"},
        headers={"Authorization": f"Bearer {new_key}"},
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# List keys
# ---------------------------------------------------------------------------

def test_list_keys(key_store_with_test_keys, test_client):
    keys = key_store_with_test_keys
    h    = {"Authorization": f"Bearer {keys['admin']}"}
    resp = test_client.get("/admin/keys", headers=h)
    assert resp.status_code == 200
    body = resp.json()
    assert "keys" in body
    assert body["total"] == len(body["keys"])
    # Hashes must never be returned
    for k in body["keys"]:
        assert "key_hash" not in k
        assert "key" not in k


# ---------------------------------------------------------------------------
# Revocation
# ---------------------------------------------------------------------------

def test_revoke_key(key_store_with_test_keys, test_client):
    keys = key_store_with_test_keys
    h    = {"Authorization": f"Bearer {keys['admin']}"}
    issue  = test_client.post("/admin/keys", json={"name": "To revoke", "scopes": ["read"]}, headers=h)
    key_id = issue.json()["id"]
    resp   = test_client.delete(f"/admin/keys/{key_id}", headers=h)
    assert resp.status_code == 200
    assert resp.json()["status"] == "success"


def test_revoke_nonexistent_key_returns_404(key_store_with_test_keys, test_client):
    keys = key_store_with_test_keys
    h    = {"Authorization": f"Bearer {keys['admin']}"}
    resp = test_client.delete("/admin/keys/key_doesnotexist", headers=h)
    assert resp.status_code == 404


def test_revoke_is_immediate(key_store_with_test_keys, test_client):
    """Revocation must take effect instantly — not after the 60s TTL expires."""
    keys = key_store_with_test_keys
    h    = {"Authorization": f"Bearer {keys['admin']}"}

    # Issue a key
    issue   = test_client.post("/admin/keys", json={"name": "To revoke", "scopes": ["read"]}, headers=h)
    issued_key = issue.json()["key"]
    key_id     = issue.json()["id"]

    # Confirm it authenticates on a protected endpoint
    # /openstates/test requires read_auth; fails at Voatz (502) but NOT at auth (200 auth pass)
    r = test_client.get("/openstates/test", headers={"Authorization": f"Bearer {issued_key}"})
    assert r.status_code != 401 and r.status_code != 403  # auth passed

    # Revoke it
    test_client.delete(f"/admin/keys/{key_id}", headers=h)

    # Must be rejected immediately — no reload or TTL wait required
    resp = test_client.get("/openstates/test", headers={"Authorization": f"Bearer {issued_key}"})
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Expiry
# ---------------------------------------------------------------------------

def test_expired_key_returns_401(key_store_with_test_keys, test_client):
    keys = key_store_with_test_keys
    h    = {"Authorization": f"Bearer {keys['admin']}"}
    issue = test_client.post(
        "/admin/keys",
        json={"name": "Expired", "scopes": ["read"], "expires_at": "2020-01-01T00:00:00Z"},
        headers=h,
    )
    expired_key = issue.json()["key"]
    # Use a protected endpoint — /health is unprotected and always returns 200
    resp = test_client.get("/openstates/test", headers={"Authorization": f"Bearer {expired_key}"})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Org restrictions
# ---------------------------------------------------------------------------

def test_org_restricted_key_rejected_for_wrong_org(key_store_with_test_keys, test_client):
    keys = key_store_with_test_keys
    h    = {"Authorization": f"Bearer {keys['admin']}"}
    issue = test_client.post(
        "/admin/keys",
        json={"name": "Restricted", "scopes": ["read"], "restrictions": {"org_ids": ["123"]}},
        headers=h,
    )
    restricted_key = issue.json()["key"]
    # org_id 456 is not in the restriction list
    resp = test_client.get(
        "/voatz/users/456",
        headers={"Authorization": f"Bearer {restricted_key}"},
    )
    assert resp.status_code == 403


def test_org_restricted_key_accepted_for_allowed_org(key_store_with_test_keys, test_client):
    keys = key_store_with_test_keys
    h    = {"Authorization": f"Bearer {keys['admin']}"}
    issue = test_client.post(
        "/admin/keys",
        json={"name": "Restricted", "scopes": ["read"], "restrictions": {"org_ids": ["99999"]}},
        headers=h,
    )
    restricted_key = issue.json()["key"]
    # org_id 99999 IS in the restriction list; request will fail at Voatz (502)
    # but must NOT fail at the org restriction check (403)
    resp = test_client.get(
        "/voatz/users/99999",
        headers={"Authorization": f"Bearer {restricted_key}"},
    )
    assert resp.status_code != 403


# ---------------------------------------------------------------------------
# Rotation
# ---------------------------------------------------------------------------

def test_rotate_key(key_store_with_test_keys, test_client):
    keys = key_store_with_test_keys
    h    = {"Authorization": f"Bearer {keys['admin']}"}
    issue  = test_client.post("/admin/keys", json={"name": "To rotate", "scopes": ["read"]}, headers=h)
    key_id = issue.json()["id"]

    rotate = test_client.post(f"/admin/keys/{key_id}/rotate", json={"grace_hours": 1}, headers=h)
    assert rotate.status_code == 200
    body = rotate.json()
    assert body["old_key_id"] == key_id
    assert body["new_key"].startswith("ddp-ro-")
    assert "will not be shown again" in body["message"]


# ---------------------------------------------------------------------------
# Docs access control
# ---------------------------------------------------------------------------

def test_public_docs_hide_admin_routes(test_client):
    """CI guard: /openapi.json must never expose /admin paths."""
    resp  = test_client.get("/openapi.json")
    assert resp.status_code == 200
    paths = resp.json().get("paths", {})
    admin_paths = [p for p in paths if p.startswith("/admin")]
    assert admin_paths == [], f"Admin routes leaked into public schema: {admin_paths}"


def test_admin_openapi_requires_auth(test_client):
    # 401 = no header present; HTTPBearer distinguishes from 403 (wrong scope)
    assert test_client.get("/admin/openapi.json").status_code == 401


def test_admin_docs_requires_auth(test_client):
    assert test_client.get("/admin/docs").status_code == 401


def test_admin_docs_rejects_read_key(key_store_with_test_keys, test_client):
    keys = key_store_with_test_keys
    h    = {"Authorization": f"Bearer {keys['read']}"}
    assert test_client.get("/admin/docs", headers=h).status_code == 403


def test_admin_docs_accessible_with_admin_key(key_store_with_test_keys, test_client):
    keys = key_store_with_test_keys
    h    = {"Authorization": f"Bearer {keys['admin']}"}
    assert test_client.get("/admin/docs", headers=h).status_code == 200
