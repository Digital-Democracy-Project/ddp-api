"""Pydantic request/response models for Webflow CMS endpoints."""

from typing import Any, Optional
from pydantic import BaseModel, Field


# ------------------------------------------------------------------
# Shared response models
# ------------------------------------------------------------------

class UpdateResultItem(BaseModel):
    """Single item update outcome."""
    item_id: str
    item_name: str
    fields_updated: dict[str, Any] = {}
    success: bool
    error: str = ""


class FillResultResponse(BaseModel):
    """Aggregate result of a bulk fill operation."""
    status: str
    total_items: int = 0
    items_already_filled: int = 0
    items_updated: int = 0
    items_skipped: int = 0
    items_failed: int = 0
    updates: list[UpdateResultItem] = []


class SyncResultResponse(BaseModel):
    """Result of a bill-org synchronization."""
    status: str
    bills_processed: int = 0
    orgs_updated: int = 0
    references_added: int = 0
    about_fields_parsed: int = 0
    missing_field_hooks_sent: int = 0
    errors: list[str] = []


class DeleteResultItem(BaseModel):
    """Single item deletion outcome."""
    item_id: str
    item_name: str
    deleted: bool
    references_removed: int = 0
    references_failed: int = 0
    error: str = ""


class DuplicateGroupItem(BaseModel):
    """A single item within a duplicate group."""
    id: str
    name: str
    slug: Optional[str] = None
    status: str  # "CORRECT" or "ANOMALOUS"
    is_hidden: bool = False
    has_random_suffix: bool = False
    fields_populated: int = 0
    fields_total: int = 0


class DuplicateGroupResponse(BaseModel):
    """A group of duplicate or companion bills."""
    label: str
    group_type: str  # "duplicate" or "companion"
    match_reasons: list[str] = []
    count: int = 0
    items: list[DuplicateGroupItem] = []


# ------------------------------------------------------------------
# Request models
# ------------------------------------------------------------------

class FillGovUrlRequest(BaseModel):
    """Fill gov-url for a single item."""
    item_id: str
    gov_url: str
    collection_id: Optional[str] = None


class FillSessionCodeRequest(BaseModel):
    """Fill session-code/bill-prefix/bill-number for all items."""
    collection_id: Optional[str] = None
    dry_run: bool = False


class FillMapUrlRequest(BaseModel):
    """Fill map-url and set visibility for all items."""
    collection_id: Optional[str] = None
    dry_run: bool = False


class BillOrgSyncRequest(BaseModel):
    """Sync bill-org references."""
    bills_collection_id: Optional[str] = None
    orgs_collection_id: Optional[str] = None


class OrgAboutFieldsRequest(BaseModel):
    """Parse about-organization into sub-fields."""
    orgs_collection_id: Optional[str] = None


class OrgMissingFieldsRequest(BaseModel):
    """Check organizations for missing fields."""
    orgs_collection_id: Optional[str] = None
    fields_to_check: list[str]
    send_zapier_hooks: bool = True


class OrgMissingFieldsItem(BaseModel):
    """An organization with missing fields."""
    org_id: str
    org_name: str
    missing_fields: list[str]


class OrgMissingFieldsResponse(BaseModel):
    """Response for missing-fields check."""
    status: str
    orgs_with_missing_fields: list[OrgMissingFieldsItem] = []


class FindDuplicatesRequest(BaseModel):
    """Find duplicate and companion bills."""
    collection_id: Optional[str] = None


class FindDuplicatesResponse(BaseModel):
    """Response with duplicate groups."""
    status: str
    duplicate_groups: list[DuplicateGroupResponse] = []
    companion_groups: list[DuplicateGroupResponse] = []


class ResolveDuplicateGroupRequest(BaseModel):
    """Resolve a duplicate group by migrating content and deleting anomalous items."""
    correct_item_id: str
    anomalous_item_ids: list[str]
    collection_id: Optional[str] = None
    orgs_collection_id: Optional[str] = None
    migrate_content: bool = True
    delete_anomalous: bool = True


class ResolveDuplicateGroupResponse(BaseModel):
    """Response for duplicate group resolution."""
    status: str
    results: list[DeleteResultItem] = []


class DeleteItemRequest(BaseModel):
    """Delete a CMS item."""
    collection_id: Optional[str] = None
    ref_collection_ids: list[str] = []
    force_remove_references: bool = False


class DeleteItemResponse(BaseModel):
    """Response for item deletion."""
    status: str
    result: DeleteResultItem
