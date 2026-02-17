"""Tests for Webflow CMS management endpoints."""

import os
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

VALID_AUTH = {"Authorization": "Bearer testtoken"}
INVALID_AUTH = {"Authorization": "Bearer wrong-token"}

# Fake config returned by _get_webflow_config
FAKE_WEBFLOW_CONFIG = {
    "webflow_api_token": "fake-token",
    "bills_collection_id": "bills-cid-123",
    "orgs_collection_id": "orgs-cid-456",
}


# ------------------------------------------------------------------
# Auth tests — every endpoint should require a valid Bearer token
# ------------------------------------------------------------------

class TestWebflowAuth:
    """All Webflow endpoints require Bearer token auth."""

    ENDPOINTS = [
        ("POST", "/webflow/fill/gov-url", {"item_id": "x", "gov_url": "http://x"}),
        ("POST", "/webflow/fill/session-code", {}),
        ("POST", "/webflow/fill/map-url", {}),
        ("POST", "/webflow/sync/bill-org", {}),
        ("POST", "/webflow/sync/org-about-fields", {}),
        ("POST", "/webflow/check/org-missing-fields", {"fields_to_check": ["email"]}),
        ("POST", "/webflow/check/duplicates", {}),
        ("POST", "/webflow/resolve/duplicate-group", {
            "correct_item_id": "a", "anomalous_item_ids": ["b"],
        }),
        ("DELETE", "/webflow/items/item123", {}),
    ]

    @pytest.mark.parametrize("method,url,body", ENDPOINTS)
    def test_requires_auth(self, method, url, body):
        if method == "POST":
            resp = client.post(url, json=body)
        else:
            resp = client.request(method, url, json=body)
        assert resp.status_code in (401, 403)

    @pytest.mark.parametrize("method,url,body", ENDPOINTS)
    def test_rejects_invalid_token(self, method, url, body):
        if method == "POST":
            resp = client.post(url, json=body, headers=INVALID_AUTH)
        else:
            resp = client.request(method, url, json=body, headers=INVALID_AUTH)
        assert resp.status_code == 403


# ------------------------------------------------------------------
# Fill endpoints
# ------------------------------------------------------------------

class TestFillGovUrl:
    """POST /webflow/fill/gov-url"""

    @patch("app.routes.webflow._get_webflow_config", return_value=FAKE_WEBFLOW_CONFIG)
    @patch("app.routes.webflow._get_client")
    def test_success(self, mock_get_client, _mock_cfg):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.fetch_item.return_value = {"id": "item1", "fieldData": {"name": "Bill A"}}

        mock_update = MagicMock()
        mock_update.item_id = "item1"
        mock_update.item_name = "Bill A"
        mock_update.fields_updated = {"gov-url": "http://gov.example"}
        mock_update.success = True
        mock_update.error = ""

        with patch("webflow_cms.services.fill_gov_url.GovUrlService") as MockSvc:
            MockSvc.return_value.fill_item.return_value = mock_update
            resp = client.post(
                "/webflow/fill/gov-url",
                json={"item_id": "item1", "gov_url": "http://gov.example"},
                headers=VALID_AUTH,
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["items_updated"] == 1

    @patch("app.routes.webflow._get_webflow_config", return_value=FAKE_WEBFLOW_CONFIG)
    @patch("app.routes.webflow._get_client")
    def test_item_not_found(self, mock_get_client, _mock_cfg):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.fetch_item.return_value = None

        resp = client.post(
            "/webflow/fill/gov-url",
            json={"item_id": "nonexistent", "gov_url": "http://gov.example"},
            headers=VALID_AUTH,
        )
        assert resp.status_code == 404


class TestFillSessionCode:
    """POST /webflow/fill/session-code"""

    @patch("app.routes.webflow._get_webflow_config", return_value=FAKE_WEBFLOW_CONFIG)
    @patch("app.routes.webflow._get_client")
    def test_success(self, mock_get_client, _mock_cfg):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        mock_result = MagicMock()
        mock_result.total_items = 50
        mock_result.items_already_filled = 40
        mock_result.items_updated = 8
        mock_result.items_skipped = 2
        mock_result.items_failed = 0
        mock_result.updates = []

        with patch("webflow_cms.services.fill_session_code.SessionCodeService") as MockSvc:
            MockSvc.return_value.fill.return_value = mock_result
            resp = client.post(
                "/webflow/fill/session-code",
                json={},
                headers=VALID_AUTH,
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["total_items"] == 50
        assert data["items_updated"] == 8

    @patch("app.routes.webflow._get_webflow_config", return_value=FAKE_WEBFLOW_CONFIG)
    @patch("app.routes.webflow._get_client")
    def test_dry_run(self, mock_get_client, _mock_cfg):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        mock_result = MagicMock()
        mock_result.total_items = 10
        mock_result.items_already_filled = 5
        mock_result.items_updated = 5
        mock_result.items_skipped = 0
        mock_result.items_failed = 0
        mock_result.updates = []

        with patch("webflow_cms.services.fill_session_code.SessionCodeService") as MockSvc:
            MockSvc.return_value.fill.return_value = mock_result
            resp = client.post(
                "/webflow/fill/session-code",
                json={"dry_run": True},
                headers=VALID_AUTH,
            )

        assert resp.status_code == 200
        MockSvc.return_value.fill.assert_called_once_with("bills-cid-123", dry_run=True)


class TestFillMapUrl:
    """POST /webflow/fill/map-url"""

    @patch("app.routes.webflow._get_webflow_config", return_value=FAKE_WEBFLOW_CONFIG)
    @patch("app.routes.webflow._get_client")
    def test_success(self, mock_get_client, _mock_cfg):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        mock_result = MagicMock()
        mock_result.total_items = 20
        mock_result.items_already_filled = 15
        mock_result.items_updated = 3
        mock_result.items_skipped = 2
        mock_result.items_failed = 0
        mock_result.updates = []

        with patch("webflow_cms.services.fill_map_url.MapUrlService") as MockSvc:
            MockSvc.return_value.fill.return_value = mock_result
            resp = client.post(
                "/webflow/fill/map-url",
                json={},
                headers=VALID_AUTH,
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["items_updated"] == 3


# ------------------------------------------------------------------
# Sync endpoints
# ------------------------------------------------------------------

class TestSyncBillOrg:
    """POST /webflow/sync/bill-org"""

    @patch("app.routes.webflow._get_webflow_config", return_value=FAKE_WEBFLOW_CONFIG)
    @patch("app.routes.webflow._get_client")
    def test_success(self, mock_get_client, _mock_cfg):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        mock_result = MagicMock()
        mock_result.bills_processed = 100
        mock_result.orgs_updated = 5
        mock_result.references_added = 12
        mock_result.errors = []

        with patch("webflow_cms.services.bill_org_sync.BillOrgSyncService") as MockSvc:
            MockSvc.return_value.sync_bill_org_references.return_value = mock_result
            resp = client.post(
                "/webflow/sync/bill-org",
                json={},
                headers=VALID_AUTH,
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["references_added"] == 12


class TestSyncOrgAboutFields:
    """POST /webflow/sync/org-about-fields"""

    @patch("app.routes.webflow._get_webflow_config", return_value=FAKE_WEBFLOW_CONFIG)
    @patch("app.routes.webflow._get_client")
    def test_success(self, mock_get_client, _mock_cfg):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        with patch("webflow_cms.services.bill_org_sync.BillOrgSyncService") as MockSvc:
            MockSvc.return_value.parse_about_fields.return_value = 7
            resp = client.post(
                "/webflow/sync/org-about-fields",
                json={},
                headers=VALID_AUTH,
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["items_updated"] == 7


# ------------------------------------------------------------------
# Check endpoints
# ------------------------------------------------------------------

class TestCheckOrgMissingFields:
    """POST /webflow/check/org-missing-fields"""

    @patch("app.routes.webflow._get_webflow_config", return_value=FAKE_WEBFLOW_CONFIG)
    @patch("app.routes.webflow._get_client")
    def test_success(self, mock_get_client, _mock_cfg):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        missing = [
            {"org_id": "org1", "org_name": "Org One", "missing_fields": ["email", "website"]},
        ]

        with patch("webflow_cms.services.bill_org_sync.BillOrgSyncService") as MockSvc:
            MockSvc.return_value.check_missing_fields.return_value = missing
            resp = client.post(
                "/webflow/check/org-missing-fields",
                json={"fields_to_check": ["email", "website"]},
                headers=VALID_AUTH,
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert len(data["orgs_with_missing_fields"]) == 1
        assert data["orgs_with_missing_fields"][0]["org_name"] == "Org One"

    def test_requires_fields_to_check(self):
        resp = client.post(
            "/webflow/check/org-missing-fields",
            json={},
            headers=VALID_AUTH,
        )
        assert resp.status_code == 422  # validation error


class TestCheckDuplicates:
    """POST /webflow/check/duplicates"""

    @patch("app.routes.webflow._get_webflow_config", return_value=FAKE_WEBFLOW_CONFIG)
    @patch("app.routes.webflow._get_client")
    def test_success(self, mock_get_client, _mock_cfg):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        dup_group = MagicMock()
        dup_group.label = "HB 123"
        dup_group.group_type = "duplicate"
        dup_group.match_reasons = ["same_title"]
        dup_group.items = [
            {
                "id": "a1", "name": "HB 123", "slug": "hb-123",
                "is_hidden": False, "has_random_suffix": False,
                "completeness": {"populated_count": 10, "total_fields": 12},
            },
            {
                "id": "a2", "name": "HB 123", "slug": "hb-123-abc123",
                "is_hidden": True, "has_random_suffix": True,
                "completeness": {"populated_count": 3, "total_fields": 12},
            },
        ]

        comp_group = MagicMock()
        comp_group.label = "SB 456"
        comp_group.group_type = "companion"
        comp_group.match_reasons = ["companion_bill"]
        comp_group.items = [
            {
                "id": "b1", "name": "SB 456", "slug": "sb-456",
                "is_hidden": False, "has_random_suffix": False,
                "completeness": {"populated_count": 8, "total_fields": 12},
            },
        ]

        with patch("webflow_cms.services.duplicate_bills.DuplicateBillsService") as MockSvc:
            MockSvc.return_value.find_duplicates.return_value = [dup_group, comp_group]
            resp = client.post(
                "/webflow/check/duplicates",
                json={},
                headers=VALID_AUTH,
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert len(data["duplicate_groups"]) == 1
        assert len(data["companion_groups"]) == 1
        assert data["duplicate_groups"][0]["label"] == "HB 123"
        assert data["duplicate_groups"][0]["items"][0]["status"] == "CORRECT"


# ------------------------------------------------------------------
# Resolve endpoint
# ------------------------------------------------------------------

class TestResolveDuplicateGroup:
    """POST /webflow/resolve/duplicate-group"""

    @patch("app.routes.webflow._get_webflow_config", return_value=FAKE_WEBFLOW_CONFIG)
    @patch("app.routes.webflow._get_client")
    def test_success(self, mock_get_client, _mock_cfg):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        mock_del = MagicMock()
        mock_del.item_id = "b1"
        mock_del.item_name = "Dup Bill"
        mock_del.deleted = True
        mock_del.references_removed = 2
        mock_del.references_failed = 0
        mock_del.error = ""

        with patch("webflow_cms.services.duplicate_bills.DuplicateBillsService") as MockSvc:
            MockSvc.return_value.resolve_group.return_value = [mock_del]
            resp = client.post(
                "/webflow/resolve/duplicate-group",
                json={
                    "correct_item_id": "a1",
                    "anomalous_item_ids": ["b1"],
                },
                headers=VALID_AUTH,
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert len(data["results"]) == 1
        assert data["results"][0]["deleted"] is True


# ------------------------------------------------------------------
# Delete endpoint
# ------------------------------------------------------------------

class TestDeleteItem:
    """DELETE /webflow/items/{item_id}"""

    @patch("app.routes.webflow._get_webflow_config", return_value=FAKE_WEBFLOW_CONFIG)
    @patch("app.routes.webflow._get_client")
    def test_success(self, mock_get_client, _mock_cfg):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        mock_result = MagicMock()
        mock_result.item_id = "item-xyz"
        mock_result.item_name = "Old Bill"
        mock_result.deleted = True
        mock_result.references_removed = 0
        mock_result.references_failed = 0
        mock_result.error = ""

        with patch("webflow_cms.services.delete_item.DeleteItemService") as MockSvc:
            MockSvc.return_value.delete.return_value = mock_result
            resp = client.request(
                "DELETE",
                "/webflow/items/item-xyz",
                json={},
                headers=VALID_AUTH,
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["result"]["item_id"] == "item-xyz"

    @patch("app.routes.webflow._get_webflow_config", return_value=FAKE_WEBFLOW_CONFIG)
    @patch("app.routes.webflow._get_client")
    def test_with_ref_removal(self, mock_get_client, _mock_cfg):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        mock_result = MagicMock()
        mock_result.item_id = "item-xyz"
        mock_result.item_name = "Old Bill"
        mock_result.deleted = True
        mock_result.references_removed = 3
        mock_result.references_failed = 0
        mock_result.error = ""

        with patch("webflow_cms.services.delete_item.DeleteItemService") as MockSvc:
            MockSvc.return_value.delete.return_value = mock_result
            resp = client.request(
                "DELETE",
                "/webflow/items/item-xyz",
                json={
                    "ref_collection_ids": ["orgs-cid-456"],
                    "force_remove_references": True,
                },
                headers=VALID_AUTH,
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["result"]["references_removed"] == 3


# ------------------------------------------------------------------
# Config / error handling
# ------------------------------------------------------------------

class TestWebflowConfigErrors:
    """Test error handling when Webflow is not configured."""

    @patch("app.routes.webflow._get_webflow_config", return_value={
        "webflow_api_token": "",
        "bills_collection_id": "",
        "orgs_collection_id": "",
    })
    def test_missing_api_token(self, _mock_cfg):
        resp = client.post(
            "/webflow/fill/session-code",
            json={},
            headers=VALID_AUTH,
        )
        assert resp.status_code == 500
        assert "WEBFLOW_API_TOKEN" in resp.json()["detail"]

    @patch("app.routes.webflow._get_webflow_config", return_value={
        "webflow_api_token": "ok-token",
        "bills_collection_id": "",
        "orgs_collection_id": "",
    })
    @patch("app.routes.webflow._get_client")
    def test_missing_collection_id(self, mock_get_client, _mock_cfg):
        mock_get_client.return_value = MagicMock()
        resp = client.post(
            "/webflow/fill/session-code",
            json={},
            headers=VALID_AUTH,
        )
        assert resp.status_code == 400
        assert "collection_id" in resp.json()["detail"]

    @patch("app.routes.webflow._get_webflow_config", return_value={
        "webflow_api_token": "ok-token",
        "bills_collection_id": "",
        "orgs_collection_id": "",
    })
    @patch("app.routes.webflow._get_client")
    def test_override_collection_id(self, mock_get_client, _mock_cfg):
        """Passing collection_id in request body should override default."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        mock_result = MagicMock()
        mock_result.total_items = 0
        mock_result.items_already_filled = 0
        mock_result.items_updated = 0
        mock_result.items_skipped = 0
        mock_result.items_failed = 0
        mock_result.updates = []

        with patch("webflow_cms.services.fill_session_code.SessionCodeService") as MockSvc:
            MockSvc.return_value.fill.return_value = mock_result
            resp = client.post(
                "/webflow/fill/session-code",
                json={"collection_id": "custom-cid"},
                headers=VALID_AUTH,
            )

        assert resp.status_code == 200
        MockSvc.return_value.fill.assert_called_once_with("custom-cid", dry_run=False)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
