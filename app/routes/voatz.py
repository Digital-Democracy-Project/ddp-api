"""Voatz API proxy endpoints."""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Query

from app.middleware.auth import read_auth, write_auth
from app.schemas.common import (
    CreateEventRequest,
    CreateEventResponse,
    EventsResponse,
    GetEventsRequest,
    GetUsersRequest,
    TokenRequest,
    TokenResponse,
    UsersResponse,
)
from app.services.voatz import (
    CREATE_EVENT_URL,
    VOATZ_HEADERS,
    fetch_events,
    fetch_tokens,
    fetch_tokens_from_config,
    fetch_users,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["voatz"])


# ---------------------------------------------------------------------------
# Passthrough endpoints — callers supply Voatz credentials / tokens directly
# ---------------------------------------------------------------------------

@router.post("/get_tokens", response_model=TokenResponse, summary="Get Voatz WS/CSRF tokens")
async def get_tokens(req: TokenRequest, _key=Depends(read_auth)):
    """Authenticate with Voatz credentials and return WS/CSRF session tokens."""
    try:
        tokens = fetch_tokens(req.emailAddress, req.password, req.organizationid)
        return {"status": "success", "WS": tokens["WS"], "Csrf-Token": tokens["Csrf-Token"]}
    except HTTPException as e:
        # Return the Voatz error as a structured response rather than re-raising,
        # to preserve the existing API contract for this passthrough endpoint.
        return {
            "status": "error",
            "message": "Login failed",
            "status_code": e.status_code,
            "text": e.detail,
        }


@router.post("/get_users", response_model=UsersResponse, summary="Get Voatz users for an organization")
async def get_users(
    req: GetUsersRequest,
    mode: str = Query(default=None, description="Set to 'diff_only' to compare against Brevo voter_ids"),
    _key=Depends(read_auth),
):
    """Fetch users from Voatz for an organization, optionally diffed against a Brevo voter_ids list."""
    try:
        users = fetch_users(req.WS, req.Csrf_Token, req.organizationId)
    except HTTPException as e:
        return {
            "message": "Failed to retrieve users.",
            "status": "error",
            "code": e.status_code,
            "text": e.detail,
        }

    if mode == "diff_only":
        return _process_diff_mode(req, users)
    return {"status": "success", "users": users}


def _process_diff_mode(req: GetUsersRequest, users: list) -> dict:
    """Process diff_only mode for get_users."""
    blacklist_raw = req.voatz_blacklist or []
    if isinstance(blacklist_raw, str):
        blacklist = set(v.strip() for v in blacklist_raw.split(",") if v.strip())
    elif isinstance(blacklist_raw, list):
        blacklist = set(str(v).strip() for v in blacklist_raw)
    else:
        blacklist = set()

    voter_ids_from_api  = []
    voter_details_by_id = {}

    def flatten_user(user):
        flattened = {k: v for k, v in user.items() if k != "orgVerificationStatus"}
        kv_pairs  = user.get("orgVerificationStatus", {}).get("keyValues", [])
        for pair in kv_pairs:
            key   = pair.get("key")
            value = pair.get("value")
            if key and value is not None:
                flattened[key] = value
        return flattened

    for user in users:
        kv = user.get("orgVerificationStatus", {}).get("keyValues", [])
        for pair in kv:
            if pair.get("key") == "Voter_Id":
                voter_id = str(pair.get("value")).strip()
                if voter_id not in blacklist:
                    voter_ids_from_api.append(voter_id)
                    voter_details_by_id[voter_id] = flatten_user(user)
                break

    voter_ids_from_brevo = req.voter_ids or []
    if isinstance(voter_ids_from_brevo, str):
        brevo_ids = [v.strip() for v in voter_ids_from_brevo.split(",") if v.strip()]
    elif isinstance(voter_ids_from_brevo, list):
        brevo_ids = [str(v).strip() for v in voter_ids_from_brevo]
    else:
        raise HTTPException(status_code=400, detail="Invalid voter_ids format")

    api_set   = set(voter_ids_from_api)
    brevo_set = set(brevo_ids)

    added_ids   = api_set - brevo_set - blacklist
    removed_ids = brevo_set - api_set

    added_users   = [voter_details_by_id[v_id] for v_id in added_ids]
    removed_users = [v_id for v_id in removed_ids]

    return {
        "status":             "success",
        "diff_mode":          True,
        "added_users":        added_users,
        "removed_voter_ids":  removed_users,
        "api_total":          len(api_set),
        "brevo_total":        len(brevo_set),
        "new_count":          len(added_users),
        "removed_count":      len(removed_users),
    }


@router.post("/get_events", response_model=EventsResponse, summary="Get Voatz events for an organization")
async def get_events(req: GetEventsRequest, _key=Depends(read_auth)):
    """Fetch events from Voatz for an organization, optionally bounded by limit/minTs."""
    try:
        events_data = fetch_events(
            req.WS, req.Csrf_Token, req.organizationId, limit=req.limit, min_ts=req.minTs
        )
    except HTTPException as e:
        return {
            "status":  "error",
            "message": "Failed to fetch events",
            "code":    e.status_code,
            "text":    e.detail,
        }

    return {"status": "success", "events": events_data}


@router.post("/create_event", response_model=CreateEventResponse, summary="Create an event in Voatz")
async def create_event(req: CreateEventRequest, _key=Depends(write_auth)):
    """Create an event in Voatz. Any fields beyond organizationId/WS/Csrf-Token are passed through as-is."""
    import requests as _requests

    headers = {
        **VOATZ_HEADERS,
        "WS":         req.WS,
        "Csrf-Token": req.Csrf_Token,
        "Cookie":     f"WS={req.WS}; Csrf-Token={req.Csrf_Token}",
    }

    payload = req.model_extra or {}

    try:
        response = _requests.post(CREATE_EVENT_URL, headers=headers, json=payload, timeout=60)
    except _requests.RequestException as e:
        logger.error("Voatz create event request failed: %s", e)
        raise HTTPException(status_code=502, detail=f"Voatz API request failed: {e}")

    if response.status_code != 200:
        return {
            "status":  "error",
            "message": "Failed to create event",
            "code":    response.status_code,
            "text":    response.text,
        }

    try:
        result = response.json()
    except Exception:
        return {"status": "success", "raw_response": response.text}

    return {"status": "success", "result": result}


# ---------------------------------------------------------------------------
# Pre-authenticated wrappers — server fetches Voatz tokens from config;
# callers need only a DDP-API read key and the org_id
# ---------------------------------------------------------------------------

def _check_org_access(auth_key, org_id: int):
    """Raise 403 if the key has an org_ids restriction that excludes this org."""
    restricted = getattr(auth_key, "restrictions", {}).get("org_ids")
    if restricted and str(org_id) not in restricted:
        raise HTTPException(
            status_code=403,
            detail="Not authorized for this organization",
        )


@router.get("/voatz/users/{org_id}", response_model=UsersResponse, summary="Get Voatz users (pre-authenticated)")
async def get_users_wrapped(org_id: int, auth_key=Depends(read_auth)):
    """
    Pre-authenticated users endpoint.

    Fetches Voatz tokens from server config — callers need only a DDP-API
    read key and the org_id. No Voatz credentials required.
    """
    _check_org_access(auth_key, org_id)
    tokens = fetch_tokens_from_config(org_id)
    users  = fetch_users(tokens["WS"], tokens["Csrf-Token"], org_id)
    return {"status": "success", "users": users}


@router.get("/voatz/events/{org_id}", response_model=EventsResponse, summary="Get Voatz events (pre-authenticated)")
async def get_events_wrapped(
    org_id: int,
    limit:  Optional[int] = Query(default=None),
    min_ts: Optional[int] = Query(default=None, alias="minTs"),
    auth_key=Depends(read_auth),
):
    """
    Pre-authenticated events endpoint.

    Fetches Voatz tokens from server config — callers need only a DDP-API
    read key and the org_id. No Voatz credentials required.

    Query params: limit (int), minTs (int)
    """
    _check_org_access(auth_key, org_id)
    tokens = fetch_tokens_from_config(org_id)
    events = fetch_events(tokens["WS"], tokens["Csrf-Token"], org_id, limit=limit, min_ts=min_ts)
    return {"status": "success", "events": events}
