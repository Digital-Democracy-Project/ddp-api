"""Common Pydantic models for request/response validation."""

from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field

# Examples shown on /docs are for non-destructive testing (API-7): running one
# unmodified must never write or delete real data. Where an endpoint has no
# dry-run mode the example uses obviously fake values that cannot match a real
# record or credential, so the upstream rejects the call.
EXAMPLE_ID = "EXAMPLE-DO-NOT-USE"
WS_HINT = "<WS from /get_tokens>"
CSRF_HINT = "<Csrf-Token from /get_tokens>"


class StatusResponse(BaseModel):
    """Generic status response."""
    status: str
    message: Optional[str] = None


class ErrorResponse(BaseModel):
    """Error response model."""
    status: str = "error"
    message: str
    code: Optional[int] = None
    text: Optional[str] = None


# Voatz Token endpoints
class TokenRequest(BaseModel):
    """Request model for /get_tokens endpoint."""
    emailAddress: str
    password: str
    organizationid: int

    model_config = ConfigDict(json_schema_extra={"examples": [
        {"emailAddress": "user@example.com", "password": EXAMPLE_ID, "organizationid": 1}
    ]})


class TokenResponse(BaseModel):
    """Response model for /get_tokens endpoint."""
    status: str
    WS: Optional[str] = Field(None, alias="WS")
    Csrf_Token: Optional[str] = Field(None, alias="Csrf-Token")
    message: Optional[str] = None
    status_code: Optional[int] = None
    text: Optional[str] = None

    class Config:
        populate_by_name = True


# Get Users endpoint
class GetUsersRequest(BaseModel):
    """Request model for /get_users endpoint."""
    organizationId: int
    WS: str
    Csrf_Token: str = Field(..., alias="Csrf-Token")
    voter_ids: Optional[Any] = None  # Can be string or list
    voatz_blacklist: Optional[Any] = None  # Can be string or list

    class Config:
        populate_by_name = True
        json_schema_extra = {"examples": [
            {"organizationId": 1, "WS": WS_HINT, "Csrf-Token": CSRF_HINT}
        ]}


class UsersResponse(BaseModel):
    """Response model for /get_users endpoint."""
    status: str
    users: Optional[list] = None
    diff_mode: Optional[bool] = None
    added_users: Optional[list] = None
    removed_voter_ids: Optional[list] = None
    api_total: Optional[int] = None
    brevo_total: Optional[int] = None
    new_count: Optional[int] = None
    removed_count: Optional[int] = None
    message: Optional[str] = None
    code: Optional[int] = None
    text: Optional[str] = None


# User Updates endpoint
class UserUpdatesRequest(BaseModel):
    """Request model for /user_updates endpoint."""
    organizationId: int
    WS: str
    Csrf_Token: str = Field(..., alias="Csrf-Token")
    brevo_api_key: str
    brevo_list_id: int
    voatz_blacklist: Optional[Any] = None

    class Config:
        populate_by_name = True
        json_schema_extra = {"examples": [
            {"organizationId": 1, "WS": WS_HINT, "Csrf-Token": CSRF_HINT,
             "brevo_api_key": EXAMPLE_ID, "brevo_list_id": 1}
        ]}


class UserUpdatesResponse(BaseModel):
    """Response model for /user_updates endpoint."""
    status: str
    diff_mode: Optional[bool] = None
    added_users: Optional[list] = None
    removed_users: Optional[list] = None
    api_total: Optional[int] = None
    brevo_total: Optional[int] = None
    no_voatz_id_count: Optional[int] = None
    new_count: Optional[int] = None
    removed_count: Optional[int] = None
    message: Optional[str] = None
    text: Optional[str] = None


# Get Events endpoint
class GetEventsRequest(BaseModel):
    """Request model for /get_events endpoint."""
    organizationId: int
    WS: str
    Csrf_Token: str = Field(..., alias="Csrf-Token")
    limit: Optional[int] = None
    minTs: Optional[int] = None

    class Config:
        populate_by_name = True
        json_schema_extra = {"examples": [
            {"organizationId": 1, "WS": WS_HINT, "Csrf-Token": CSRF_HINT, "limit": 10}
        ]}


class EventsResponse(BaseModel):
    """Response model for /get_events endpoint."""
    status: str
    events: Optional[Any] = None
    message: Optional[str] = None
    code: Optional[int] = None
    text: Optional[str] = None


# Create Event endpoint
class CreateEventRequest(BaseModel):
    """Request model for /create_event endpoint."""
    organizationId: int
    WS: str
    Csrf_Token: str = Field(..., alias="Csrf-Token")
    # Additional event fields will be passed through

    class Config:
        populate_by_name = True
        extra = "allow"  # Allow additional fields for event data
        # Creates a Voatz event: fake session values so Voatz rejects it.
        json_schema_extra = {"examples": [
            {"organizationId": 1, "WS": EXAMPLE_ID, "Csrf-Token": EXAMPLE_ID}
        ]}


class CreateEventResponse(BaseModel):
    """Response model for /create_event endpoint."""
    status: str
    result: Optional[Any] = None
    raw_response: Optional[str] = None
    message: Optional[str] = None
    code: Optional[int] = None
    text: Optional[str] = None


# Update Segment Attribute endpoint
class UpdateSegmentRequest(BaseModel):
    """Request model for /update_segment_attribute endpoint."""
    brevo_api_key: str
    segment_id: int
    attribute_name: str
    attribute_value: Optional[Any] = None

    # Bulk-updates Brevo contacts: fake key/segment so Brevo rejects it.
    model_config = ConfigDict(json_schema_extra={"examples": [
        {"brevo_api_key": EXAMPLE_ID, "segment_id": 1,
         "attribute_name": "EXAMPLE_ATTRIBUTE", "attribute_value": "EXAMPLE"}
    ]})


class UpdateSegmentResponse(BaseModel):
    """Response model for /update_segment_attribute endpoint."""
    status: str
    total: Optional[int] = None
    updated: Optional[int] = None
    failures: Optional[list] = None
    message: Optional[str] = None
    code: Optional[int] = None
    text: Optional[str] = None


# VoteBot Chat endpoint
class PageContext(BaseModel):
    """Page context for VoteBot chat."""
    type: str
    url: Optional[str] = None
    title: Optional[str] = None
    legislator_id: Optional[str] = None
    bill_id: Optional[str] = None
    organization_id: Optional[str] = None


class ChatRequest(BaseModel):
    """Request model for VoteBot chat endpoints."""
    message: str
    session_id: str
    page_context: Optional[PageContext] = None

    model_config = ConfigDict(json_schema_extra={"examples": [
        {"message": "What does this bill do?", "session_id": "example-session-1",
         "page_context": {"type": "bill", "bill_id": "EXAMPLE-DO-NOT-USE"}}
    ]})


class FeedbackRequest(BaseModel):
    """Request model for VoteBot feedback endpoint."""
    session_id: str
    message_id: str
    feedback_type: str  # "positive" or "negative"
    feedback_text: Optional[str] = None

    # Stores feedback: a fake session/message id that matches nothing real.
    model_config = ConfigDict(json_schema_extra={"examples": [
        {"session_id": EXAMPLE_ID, "message_id": EXAMPLE_ID,
         "feedback_type": "positive", "feedback_text": "EXAMPLE - ignore"}
    ]})
