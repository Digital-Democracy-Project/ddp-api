"""Webflow CMS management endpoints.

Thin route handlers that instantiate webflow_cms services and return
structured results.  All endpoints require Bearer token auth.
"""

import logging
import os

from fastapi import APIRouter, Depends, HTTPException

from app.middleware.auth import read_auth, write_auth
from app.schemas.webflow import (
    BillOrgSyncRequest,
    DeleteItemRequest,
    DeleteItemResponse,
    DeleteResultItem,
    DuplicateGroupItem,
    DuplicateGroupResponse,
    FillGovUrlRequest,
    FillMapUrlRequest,
    FillResultResponse,
    FillSessionCodeRequest,
    FindDuplicatesRequest,
    FindDuplicatesResponse,
    OrgAboutFieldsRequest,
    OrgMissingFieldsItem,
    OrgMissingFieldsRequest,
    OrgMissingFieldsResponse,
    ResolveDuplicateGroupRequest,
    ResolveDuplicateGroupResponse,
    SyncResultResponse,
    UpdateResultItem,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webflow", tags=["webflow"])


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _get_webflow_config() -> dict:
    """Load Webflow-specific config from environment or config.local.json."""
    try:
        from config import get_config
        config = get_config()
    except Exception:
        config = {}
    return {
        "webflow_api_token": config.get("webflow_api_token", os.getenv("WEBFLOW_API_TOKEN", "")),
        "bills_collection_id": config.get("webflow_bills_collection_id", os.getenv("WEBFLOW_COLLECTION_ID", "")),
        "orgs_collection_id": config.get("webflow_orgs_collection_id", os.getenv("WEBFLOW_ORGS_COLLECTION_ID", "")),
    }


def _get_client():
    """Instantiate a WebflowClient from config."""
    from webflow_cms import WebflowClient
    cfg = _get_webflow_config()
    token = cfg["webflow_api_token"]
    if not token:
        raise HTTPException(status_code=500, detail="WEBFLOW_API_TOKEN not configured")
    return WebflowClient(token)


def _resolve_bills_collection(override: str | None) -> str:
    if override:
        return override
    cid = _get_webflow_config()["bills_collection_id"]
    if not cid:
        raise HTTPException(status_code=400, detail="bills collection_id required")
    return cid


def _resolve_orgs_collection(override: str | None) -> str:
    if override:
        return override
    cid = _get_webflow_config()["orgs_collection_id"]
    if not cid:
        raise HTTPException(status_code=400, detail="orgs collection_id required")
    return cid


# ------------------------------------------------------------------
# Fill endpoints
# ------------------------------------------------------------------

@router.post("/fill/gov-url", response_model=FillResultResponse)
async def fill_gov_url(req: FillGovUrlRequest, token: str = Depends(write_auth)):
    """Set gov-url on a single CMS item."""
    try:
        from webflow_cms.services.fill_gov_url import GovUrlService

        client = _get_client()
        collection_id = _resolve_bills_collection(req.collection_id)
        service = GovUrlService(client)

        item = client.fetch_item(collection_id, req.item_id)
        if not item:
            raise HTTPException(status_code=404, detail=f"Item {req.item_id} not found")

        update = service.fill_item(collection_id, item, req.gov_url)
        return FillResultResponse(
            status="success",
            total_items=1,
            items_updated=1 if update.success else 0,
            items_failed=0 if update.success else 1,
            updates=[UpdateResultItem(**vars(update))],
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"fill_gov_url failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/fill/session-code", response_model=FillResultResponse)
async def fill_session_code(req: FillSessionCodeRequest, token: str = Depends(write_auth)):
    """Fill session-code, bill-prefix, bill-number from open-states-url-2."""
    try:
        from webflow_cms.services.fill_session_code import SessionCodeService

        client = _get_client()
        collection_id = _resolve_bills_collection(req.collection_id)
        service = SessionCodeService(client)

        result = service.fill(collection_id, dry_run=req.dry_run)
        return FillResultResponse(
            status="success",
            total_items=result.total_items,
            items_already_filled=result.items_already_filled,
            items_updated=result.items_updated,
            items_skipped=result.items_skipped,
            items_failed=result.items_failed,
            updates=[UpdateResultItem(**vars(u)) for u in result.updates],
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"fill_session_code failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/fill/map-url", response_model=FillResultResponse)
async def fill_map_url(req: FillMapUrlRequest, token: str = Depends(write_auth)):
    """Fill map-url and set bill visibility."""
    try:
        from webflow_cms.services.fill_map_url import MapUrlService

        client = _get_client()
        collection_id = _resolve_bills_collection(req.collection_id)
        service = MapUrlService(client)

        result = service.fill(collection_id, dry_run=req.dry_run)
        return FillResultResponse(
            status="success",
            total_items=result.total_items,
            items_already_filled=result.items_already_filled,
            items_updated=result.items_updated,
            items_skipped=result.items_skipped,
            items_failed=result.items_failed,
            updates=[UpdateResultItem(**vars(u)) for u in result.updates],
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"fill_map_url failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ------------------------------------------------------------------
# Sync endpoints
# ------------------------------------------------------------------

@router.post("/sync/bill-org", response_model=SyncResultResponse)
async def sync_bill_org(req: BillOrgSyncRequest, token: str = Depends(write_auth)):
    """Sync bill-org references (ensure orgs' bills-support/bills-oppose are populated)."""
    try:
        from webflow_cms.services.bill_org_sync import BillOrgSyncService

        client = _get_client()
        bills_cid = _resolve_bills_collection(req.bills_collection_id)
        orgs_cid = _resolve_orgs_collection(req.orgs_collection_id)
        service = BillOrgSyncService(client)

        result = service.sync_bill_org_references(bills_cid, orgs_cid)
        return SyncResultResponse(
            status="success",
            bills_processed=result.bills_processed,
            orgs_updated=result.orgs_updated,
            references_added=result.references_added,
            errors=result.errors,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"sync_bill_org failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sync/org-about-fields", response_model=FillResultResponse)
async def sync_org_about_fields(req: OrgAboutFieldsRequest, token: str = Depends(write_auth)):
    """Parse about-organization into sub-fields for all orgs."""
    try:
        from webflow_cms.services.bill_org_sync import BillOrgSyncService

        client = _get_client()
        orgs_cid = _resolve_orgs_collection(req.orgs_collection_id)
        service = BillOrgSyncService(client)

        updated = service.parse_about_fields(orgs_cid)
        return FillResultResponse(
            status="success",
            items_updated=updated,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"sync_org_about_fields failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ------------------------------------------------------------------
# Check endpoints
# ------------------------------------------------------------------

@router.post("/check/org-missing-fields", response_model=OrgMissingFieldsResponse)
async def check_org_missing_fields(req: OrgMissingFieldsRequest, token: str = Depends(read_auth)):
    """Check organizations for missing fields and optionally send Zapier hooks."""
    try:
        from webflow_cms.services.bill_org_sync import BillOrgSyncService

        client = _get_client()
        orgs_cid = _resolve_orgs_collection(req.orgs_collection_id)
        service = BillOrgSyncService(client)

        results = service.check_missing_fields(
            orgs_cid,
            req.fields_to_check,
            send_zapier_hooks=req.send_zapier_hooks,
        )
        return OrgMissingFieldsResponse(
            status="success",
            orgs_with_missing_fields=[OrgMissingFieldsItem(**r) for r in results],
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"check_org_missing_fields failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/check/duplicates", response_model=FindDuplicatesResponse)
async def check_duplicates(req: FindDuplicatesRequest, token: str = Depends(read_auth)):
    """Find duplicate and companion bills."""
    try:
        from webflow_cms.services.duplicate_bills import DuplicateBillsService

        client = _get_client()
        collection_id = _resolve_bills_collection(req.collection_id)
        service = DuplicateBillsService(client)

        groups = service.find_duplicates(collection_id)

        def _format_group(g) -> DuplicateGroupResponse:
            sorted_items = sorted(
                g.items,
                key=lambda x: (x["completeness"]["populated_count"], 0 if x.get("has_random_suffix") else 1),
                reverse=True,
            )
            max_pop = sorted_items[0]["completeness"]["populated_count"] if sorted_items else 0
            items_out = []
            for item in sorted_items:
                pop = item["completeness"]["populated_count"]
                has_rand = item.get("has_random_suffix", False)
                items_out.append(DuplicateGroupItem(
                    id=item["id"],
                    name=item["name"],
                    slug=item.get("slug"),
                    status="CORRECT" if pop == max_pop and pop > 0 and not has_rand else "ANOMALOUS",
                    is_hidden=item.get("is_hidden", False),
                    has_random_suffix=has_rand,
                    fields_populated=pop,
                    fields_total=item["completeness"]["total_fields"],
                ))
            return DuplicateGroupResponse(
                label=g.label,
                group_type=g.group_type,
                match_reasons=g.match_reasons,
                count=len(g.items),
                items=items_out,
            )

        duplicates = [_format_group(g) for g in groups if g.group_type == "duplicate"]
        companions = [_format_group(g) for g in groups if g.group_type == "companion"]

        return FindDuplicatesResponse(
            status="success",
            duplicate_groups=duplicates,
            companion_groups=companions,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"check_duplicates failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ------------------------------------------------------------------
# Resolve endpoints
# ------------------------------------------------------------------

@router.post("/resolve/duplicate-group", response_model=ResolveDuplicateGroupResponse)
async def resolve_duplicate_group(req: ResolveDuplicateGroupRequest, token: str = Depends(write_auth)):
    """Resolve a duplicate group: migrate content and delete anomalous items."""
    try:
        from webflow_cms.services.duplicate_bills import DuplicateBillsService

        client = _get_client()
        collection_id = _resolve_bills_collection(req.collection_id)
        orgs_cid = req.orgs_collection_id or _get_webflow_config()["orgs_collection_id"] or None
        service = DuplicateBillsService(client)

        results = service.resolve_group(
            collection_id,
            req.correct_item_id,
            req.anomalous_item_ids,
            migrate_content=req.migrate_content,
            delete_anomalous=req.delete_anomalous,
            orgs_collection_id=orgs_cid,
        )
        return ResolveDuplicateGroupResponse(
            status="success",
            results=[DeleteResultItem(**vars(r)) for r in results],
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"resolve_duplicate_group failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ------------------------------------------------------------------
# Delete endpoint
# ------------------------------------------------------------------

@router.delete("/items/{item_id}", response_model=DeleteItemResponse)
async def delete_item(item_id: str, req: DeleteItemRequest, token: str = Depends(write_auth)):
    """Delete a CMS item, optionally removing references first."""
    try:
        from webflow_cms.services.delete_item import DeleteItemService

        client = _get_client()
        collection_id = _resolve_bills_collection(req.collection_id)
        service = DeleteItemService(client)

        result = service.delete(
            collection_id,
            item_id,
            ref_collection_ids=req.ref_collection_ids,
            force_remove_references=req.force_remove_references,
        )
        return DeleteItemResponse(
            status="success" if result.deleted else "error",
            result=DeleteResultItem(**vars(result)),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"delete_item failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
