"""Voatz API proxy endpoints."""

import logging
import os
import requests
from fastapi import APIRouter, HTTPException, Depends, Query

from app.middleware.auth import read_auth, write_auth

logger = logging.getLogger(__name__)

router = APIRouter(tags=["voatz"])

# Voatz API base URL (set via env var or Secrets Manager)
VOATZ_API_BASE = os.getenv("VOATZ_API_BASE_URL", "https://api.voatz.com")
LOGIN_URL = f"{VOATZ_API_BASE}/voatz/organizations/users/login"
USERS_URL = f"{VOATZ_API_BASE}/voatz/customers/delegate/signups/byorg"
EVENTS_URL = f"{VOATZ_API_BASE}/voatz/events/listbyorganization/chrono"
CREATE_EVENT_URL = f"{VOATZ_API_BASE}/voatz/events/create"

VOATZ_HEADERS = {
    "Accept-Encoding": "identity",
    "Content-Type": "application/json",
    "Origin": os.getenv("VOATZ_API_ORIGIN", VOATZ_API_BASE),
}


@router.post("/get_tokens")
async def get_tokens(
    data: dict,
    token: str = Depends(read_auth),
):
    """
    Get Voatz WS/CSRF tokens by authenticating with Voatz credentials.

    Required fields: emailAddress, password, organizationid
    """
    email = data.get("emailAddress")
    password = data.get("password")
    organization_id = data.get("organizationid")

    if not email or not password or not organization_id:
        raise HTTPException(
            status_code=400,
            detail="Missing one or more required fields: emailAddress, password, organizationid",
        )

    login_payload = {
        "emailAddress": email,
        "password": password,
        "authData": [{"key": "organizationid", "value": str(organization_id)}],
    }

    try:
        login_response = requests.post(
            LOGIN_URL, headers=VOATZ_HEADERS, json=login_payload, timeout=30
        )
    except requests.RequestException as e:
        logger.error(f"Voatz login request failed: {e}")
        raise HTTPException(status_code=502, detail=f"Voatz API request failed: {e}")

    if login_response.status_code == 200 and login_response.text.strip() == "OK":
        ws_token = login_response.cookies.get("WS") or login_response.headers.get("WS")
        csrf_token = login_response.cookies.get("Csrf-Token") or login_response.headers.get(
            "Csrf-Token"
        )

        if ws_token and csrf_token:
            return {"status": "success", "WS": ws_token, "Csrf-Token": csrf_token}
        else:
            raise HTTPException(status_code=500, detail="Tokens not found in Voatz response")
    else:
        return {
            "status": "error",
            "message": "Login failed",
            "status_code": login_response.status_code,
            "text": login_response.text,
        }


@router.post("/get_users")
async def get_users(
    data: dict,
    mode: str = Query(default=None),
    token: str = Depends(read_auth),
):
    """
    Get users from Voatz for an organization.

    Required fields: organizationId, WS, Csrf-Token
    Optional query param: mode=diff_only (for comparing with Brevo voter_ids)
    """
    organization_id = data.get("organizationId")
    ws_token = data.get("WS")
    csrf_token = data.get("Csrf-Token")

    if not organization_id or not ws_token or not csrf_token:
        raise HTTPException(status_code=400, detail="Missing required fields.")

    headers = {
        **VOATZ_HEADERS,
        "WS": ws_token,
        "Csrf-Token": csrf_token,
        "Cookie": f"WS={ws_token}; Csrf-Token={csrf_token}",
    }

    users = []
    min_id = None

    while True:
        payload = {"organizationId": int(organization_id), "limit": 1000}
        if min_id:
            payload["minId"] = min_id

        try:
            response = requests.post(USERS_URL, headers=headers, json=payload, timeout=60)
        except requests.RequestException as e:
            logger.error(f"Voatz users request failed: {e}")
            raise HTTPException(status_code=502, detail=f"Voatz API request failed: {e}")

        if response.status_code != 200:
            return {
                "message": "Failed to retrieve users.",
                "status": "error",
                "code": response.status_code,
                "text": response.text,
            }

        try:
            response_data = response.json()
        except Exception:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to parse JSON from Voatz response: {response.text}",
            )

        result = response_data.get("result", [])
        if not result:
            break

        users.extend(result)
        min_id = response_data.get("minId")

    if mode == "diff_only":
        return _process_diff_mode(data, users)
    else:
        return {"status": "success", "users": users}


def _process_diff_mode(data: dict, users: list) -> dict:
    """Process diff_only mode for get_users."""
    # Handle optional voatz_blacklist
    blacklist_raw = data.get("voatz_blacklist", [])
    if isinstance(blacklist_raw, str):
        blacklist = set(v.strip() for v in blacklist_raw.split(",") if v.strip())
    elif isinstance(blacklist_raw, list):
        blacklist = set(str(v).strip() for v in blacklist_raw)
    else:
        blacklist = set()

    voter_ids_from_api = []
    voter_details_by_id = {}

    def flatten_user(user):
        flattened = {k: v for k, v in user.items() if k != "orgVerificationStatus"}
        kv_pairs = user.get("orgVerificationStatus", {}).get("keyValues", [])
        for pair in kv_pairs:
            key = pair.get("key")
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

    api_set = set(voter_ids_from_api)
    brevo_set = set(brevo_ids)

    added_ids = api_set - brevo_set - blacklist
    removed_ids = brevo_set - api_set

    added_users = [voter_details_by_id[v_id] for v_id in added_ids]
    removed_users = [v_id for v_id in removed_ids]

    return {
        "status": "success",
        "diff_mode": True,
        "added_users": added_users,
        "removed_voter_ids": removed_users,
        "api_total": len(api_set),
        "brevo_total": len(brevo_set),
        "new_count": len(added_users),
        "removed_count": len(removed_users),
    }


@router.post("/get_events")
async def get_events(data: dict, token: str = Depends(read_auth)):
    """
    Get events from Voatz for an organization.

    Required fields: organizationId, WS, Csrf-Token
    Optional fields: limit, minTs
    """
    organization_id = data.get("organizationId")
    ws_token = data.get("WS")
    csrf_token = data.get("Csrf-Token")
    limit = data.get("limit")
    min_ts = data.get("minTs")

    if not organization_id or not ws_token or not csrf_token:
        raise HTTPException(
            status_code=400,
            detail="Missing required fields: organizationId, WS, or Csrf-Token",
        )

    headers = {
        **VOATZ_HEADERS,
        "WS": ws_token,
        "Csrf-Token": csrf_token,
        "Cookie": f"WS={ws_token}; Csrf-Token={csrf_token}",
    }

    payload = {"organizationId": organization_id}
    if limit:
        payload["limit"] = limit
    if min_ts:
        payload["minTs"] = min_ts

    try:
        response = requests.post(EVENTS_URL, headers=headers, json=payload, timeout=60)
    except requests.RequestException as e:
        logger.error(f"Voatz events request failed: {e}")
        raise HTTPException(status_code=502, detail=f"Voatz API request failed: {e}")

    if response.status_code != 200:
        return {
            "status": "error",
            "message": "Failed to fetch events",
            "code": response.status_code,
            "text": response.text,
        }

    try:
        events_data = response.json()
    except Exception:
        return {
            "status": "error",
            "message": "Invalid JSON in response",
            "raw_response": response.text,
        }

    return {"status": "success", "events": events_data}


@router.post("/create_event")
async def create_event(data: dict, token: str = Depends(write_auth)):
    """
    Create an event in Voatz.

    Required fields: organizationId, WS, Csrf-Token
    Additional fields are passed through to the Voatz API.
    """
    organization_id = data.get("organizationId")
    ws_token = data.get("WS")
    csrf_token = data.get("Csrf-Token")

    if not organization_id or not ws_token or not csrf_token:
        raise HTTPException(
            status_code=400,
            detail="Missing required fields: organizationId, WS, or Csrf-Token",
        )

    headers = {
        **VOATZ_HEADERS,
        "WS": ws_token,
        "Csrf-Token": csrf_token,
        "Cookie": f"WS={ws_token}; Csrf-Token={csrf_token}",
    }

    # Remove auth fields and pass through the rest
    payload = data.copy()
    payload.pop("WS", None)
    payload.pop("Csrf-Token", None)
    payload.pop("organizationId", None)

    try:
        response = requests.post(CREATE_EVENT_URL, headers=headers, json=payload, timeout=60)
    except requests.RequestException as e:
        logger.error(f"Voatz create event request failed: {e}")
        raise HTTPException(status_code=502, detail=f"Voatz API request failed: {e}")

    if response.status_code != 200:
        return {
            "status": "error",
            "message": "Failed to create event",
            "code": response.status_code,
            "text": response.text,
        }

    try:
        result = response.json()
    except Exception:
        return {"status": "success", "raw_response": response.text}

    return {"status": "success", "result": result}
