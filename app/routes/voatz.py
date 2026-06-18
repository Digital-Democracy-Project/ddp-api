"""Voatz API proxy endpoints."""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Query

from app.middleware.auth import read_auth, write_auth
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

@router.post("/get_tokens")
async def get_tokens(data: dict, _key=Depends(read_auth)):
    """
    Get Voatz WS/CSRF tokens by authenticating with Voatz credentials.

    Required fields: emailAddress, password, organizationid
    """
    import requests

    email           = data.get("emailAddress")
    password        = data.get("password")
    organization_id = data.get("organizationid")

    if not email or not password or not organization_id:
        raise HTTPException(
            status_code=400,
            detail="Missing one or more required fields: emailAddress, password, organizationid",
        )

    try:
        tokens = fetch_tokens(email, password, int(organization_id))
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


@router.post("/get_users")
async def get_users(
    data: dict,
    mode: str = Query(default=None),
    _key=Depends(read_auth),
):
    """
    Get users from Voatz for an organization.

    Required fields: organizationId, WS, Csrf-Token
    Optional query param: mode=diff_only (for comparing with Brevo voter_ids)
    """
    organization_id = data.get("organizationId")
    ws_token        = data.get("WS")
    csrf_token      = data.get("Csrf-Token")

    if not organization_id or not ws_token or not csrf_token:
        raise HTTPException(status_code=400, detail="Missing required fields.")

    try:
        users = fetch_users(ws_token, csrf_token, organization_id)
    except HTTPException as e:
        return {
            "message": "Failed to retrieve users.",
            "status": "error",
            "code": e.status_code,
            "text": e.detail,
        }

    if mode == "diff_only":
        return _process_diff_mode(data, users)
    return {"status": "success", "users": users}


def _process_diff_mode(data: dict, users: list) -> dict:
    """Process diff_only mode for get_users."""
    blacklist_raw = data.get("voatz_blacklist", [])
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

    voter_ids_from_brevo = data.get("voter_ids", [])
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


@router.post("/get_events")
async def get_events(data: dict, _key=Depends(read_auth)):
    """
    Get events from Voatz for an organization.

    Required fields: organizationId, WS, Csrf-Token
    Optional fields: limit, minTs
    """
    organization_id = data.get("organizationId")
    ws_token        = data.get("WS")
    csrf_token      = data.get("Csrf-Token")
    limit           = data.get("limit")
    min_ts          = data.get("minTs")

    if not organization_id or not ws_token or not csrf_token:
        raise HTTPException(
            status_code=400,
            detail="Missing required fields: organizationId, WS, or Csrf-Token",
        )

    try:
        events_data = fetch_events(ws_token, csrf_token, organization_id, limit=limit, min_ts=min_ts)
    except HTTPException as e:
        return {
            "status":  "error",
            "message": "Failed to fetch events",
            "code":    e.status_code,
            "text":    e.detail,
        }

    return {"status": "success", "events": events_data}


@router.post("/create_event")
async def create_event(data: dict, _key=Depends(write_auth)):
    """
    Create an event in Voatz.

    Required fields: organizationId, WS, Csrf-Token
    Additional fields are passed through to the Voatz API.
    """
    import requests as _requests

    organization_id = data.get("organizationId")
    ws_token        = data.get("WS")
    csrf_token      = data.get("Csrf-Token")

    if not organization_id or not ws_token or not csrf_token:
        raise HTTPException(
            status_code=400,
            detail="Missing required fields: organizationId, WS, or Csrf-Token",
        )

    headers = {
        **VOATZ_HEADERS,
        "WS":         ws_token,
        "Csrf-Token": csrf_token,
        "Cookie":     f"WS={ws_token}; Csrf-Token={csrf_token}",
    }

    payload = data.copy()
    payload.pop("WS", None)
    payload.pop("Csrf-Token", None)
    payload.pop("organizationId", None)

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


@router.get("/voatz/users/{org_id}")
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


@router.get("/voatz/events/{org_id}")
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
