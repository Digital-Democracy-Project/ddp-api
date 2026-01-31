"""Common Pydantic models for request/response validation."""

from typing import Any, Optional
from pydantic import BaseModel, Field


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


class TokenResponse(BaseModel):
    """Response model for /get_tokens endpoint."""
    status: str
    WS: Optional[str] = Field(None, alias="WS")
    Csrf_Token: Optional[str] = Field(None, alias="Csrf-Token")
    message: Optional[str] = None


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


class UserUpdatesResponse(BaseModel):
    """Response model for /user_updates endpoint."""
    status: str
    diff_mode: bool
    added_users: list
    removed_users: list
    api_total: int
    brevo_total: int
    new_count: int
    removed_count: int


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


class UpdateSegmentResponse(BaseModel):
    """Response model for /update_segment_attribute endpoint."""
    status: str
    total: int
    updated: int
    failures: list


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


class FeedbackRequest(BaseModel):
    """Request model for VoteBot feedback endpoint."""
    session_id: str
    message_id: str
    feedback_type: str  # "positive" or "negative"
    feedback_text: Optional[str] = None
