"""Voatz HTTP client — shared by route handlers and pre-authenticated wrapper endpoints."""

import logging
import os
import requests
from fastapi import HTTPException

logger = logging.getLogger(__name__)

VOATZ_API_BASE   = os.getenv("VOATZ_API_BASE_URL", "https://api.voatz.com")
LOGIN_URL        = f"{VOATZ_API_BASE}/voatz/organizations/users/login"
USERS_URL        = f"{VOATZ_API_BASE}/voatz/customers/delegate/signups/byorg"
EVENTS_URL       = f"{VOATZ_API_BASE}/voatz/events/listbyorganization/chrono"
CREATE_EVENT_URL = f"{VOATZ_API_BASE}/voatz/events/create"

VOATZ_HEADERS = {
    "Accept-Encoding": "identity",
    "Content-Type": "application/json",
    "Origin": os.getenv("VOATZ_API_ORIGIN", VOATZ_API_BASE),
}


def fetch_tokens(email: str, password: str, org_id: int) -> dict:
    """Authenticate with Voatz. Returns {"WS": ..., "Csrf-Token": ...}."""
    payload = {
        "emailAddress": email,
        "password": password,
        "authData": [{"key": "organizationid", "value": str(org_id)}],
    }
    try:
        resp = requests.post(LOGIN_URL, headers=VOATZ_HEADERS, json=payload, timeout=30)
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Voatz login failed: {e}")

    if resp.status_code == 200 and resp.text.strip() == "OK":
        ws   = resp.cookies.get("WS")        or resp.headers.get("WS")
        csrf = resp.cookies.get("Csrf-Token") or resp.headers.get("Csrf-Token")
        if ws and csrf:
            return {"WS": ws, "Csrf-Token": csrf}
        raise HTTPException(status_code=500, detail="Tokens not found in Voatz response")

    raise HTTPException(
        status_code=502,
        detail=f"Voatz login failed: {resp.status_code} {resp.text}",
    )


def fetch_tokens_from_config(org_id: int) -> dict:
    """
    Look up org credentials from config and call fetch_tokens().
    Used by GET wrapper endpoints — the caller never sees Voatz credentials.
    """
    from config import get_config
    config = get_config()
    org = next(
        (o for o in config.get("organizations", []) if o.get("voatz_org_id") == org_id),
        None,
    )
    if not org:
        raise HTTPException(status_code=404, detail=f"Organization {org_id} not found")
    return fetch_tokens(org["voatz_email"], org["voatz_password"], org_id)


def fetch_users(ws_token: str, csrf_token: str, org_id: int) -> list:
    """Paginated fetch of all users for an org. Returns raw result list."""
    headers = {
        **VOATZ_HEADERS,
        "WS": ws_token,
        "Csrf-Token": csrf_token,
        "Cookie": f"WS={ws_token}; Csrf-Token={csrf_token}",
    }
    users, min_id = [], None
    while True:
        payload = {"organizationId": int(org_id), "limit": 1000}
        if min_id:
            payload["minId"] = min_id
        try:
            resp = requests.post(USERS_URL, headers=headers, json=payload, timeout=60)
        except requests.RequestException as e:
            raise HTTPException(status_code=502, detail=f"Voatz users request failed: {e}")
        if resp.status_code != 200:
            raise HTTPException(
                status_code=502,
                detail=f"Voatz users request failed: {resp.status_code} {resp.text}",
            )
        data   = resp.json()
        result = data.get("result", [])
        if not result:
            break
        users.extend(result)
        min_id = data.get("minId")
    return users


def fetch_events(
    ws_token: str,
    csrf_token: str,
    org_id: int,
    limit: int = None,
    min_ts: int = None,
) -> object:
    """Fetch events for an org. Returns raw Voatz response JSON."""
    headers = {
        **VOATZ_HEADERS,
        "WS": ws_token,
        "Csrf-Token": csrf_token,
        "Cookie": f"WS={ws_token}; Csrf-Token={csrf_token}",
    }
    payload = {"organizationId": org_id}
    if limit:
        payload["limit"] = limit
    if min_ts:
        payload["minTs"] = min_ts
    try:
        resp = requests.post(EVENTS_URL, headers=headers, json=payload, timeout=60)
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Voatz events request failed: {e}")
    if resp.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"Voatz events request failed: {resp.status_code} {resp.text}",
        )
    return resp.json()
