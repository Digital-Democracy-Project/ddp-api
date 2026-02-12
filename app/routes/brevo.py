"""Brevo API proxy endpoints."""

import logging
import time
import os
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from fastapi import APIRouter, HTTPException, Depends

from app.middleware.auth import bearer_auth

logger = logging.getLogger(__name__)

router = APIRouter(tags=["brevo"])

# Rate limiting settings
RATE_LIMIT_RPH = int(os.getenv("BREVO_RATE_LIMIT_RPH", "36000"))
REQUEST_DELAY = 3600.0 / RATE_LIMIT_RPH
MAX_RETRIES = 3

# Requests session configured to retry GET/PUT on 429
BREVO_SESSION = requests.Session()
_brevo_retry = Retry(
    total=3,
    backoff_factor=1,
    status_forcelist=[429],
    allowed_methods=["GET", "PUT", "POST"],
)
BREVO_SESSION.mount("https://", HTTPAdapter(max_retries=_brevo_retry))
BREVO_SESSION.mount("http://", HTTPAdapter(max_retries=_brevo_retry))


@router.post("/update_segment_attribute")
async def update_segment_attribute(
    data: dict,
    token: str = Depends(bearer_auth),
):
    """
    Bulk update an attribute for all contacts in a Brevo segment.

    Required fields: brevo_api_key, segment_id, attribute_name
    Optional fields: attribute_value
    """
    brevo_api_key = data.get("brevo_api_key")
    segment_id = data.get("segment_id")
    attr_name = data.get("attribute_name")
    attr_value = data.get("attribute_value")

    if not brevo_api_key or segment_id is None or not attr_name:
        raise HTTPException(
            status_code=400,
            detail="Missing required fields: brevo_api_key, segment_id, attribute_name",
        )

    # Fetch contacts in segment (paginated)
    headers_brevo = {"Accept": "application/json", "api-key": brevo_api_key}
    contacts = []
    offset = 0
    limit = 500

    while True:
        params = {"segmentId": int(segment_id), "limit": limit, "offset": offset}

        # Retry GET on rate limit
        resp = None
        for _ in range(MAX_RETRIES + 1):
            rep = BREVO_SESSION.get(
                "https://api.brevo.com/v3/contacts",
                headers=headers_brevo,
                params=params,
                timeout=60,
            )
            if rep.status_code == 429:
                time.sleep(REQUEST_DELAY)
                continue
            resp = rep
            break

        if resp is None or resp.status_code != 200:
            return {
                "status": "error",
                "message": "Failed to fetch contacts",
                "code": resp.status_code if resp else 500,
                "text": resp.text if resp else "No response",
            }

        page = resp.json().get("contacts", [])
        if not page:
            break
        contacts.extend(page)
        offset += limit
        time.sleep(REQUEST_DELAY)

    # Bulk update contacts' attribute via Brevo import endpoint as JSON
    import_url = "https://api.brevo.com/v3/contacts/import"

    # Build list of contact entries (email + attributes) for import
    contacts_json = []
    for c in contacts:
        email = c.get("email")
        if email:
            contacts_json.append({"email": email, "attributes": {attr_name: attr_value}})

    total = len(contacts_json)
    updated = 0
    failures = []
    chunk_size = 2000

    for i in range(0, total, chunk_size):
        chunk = contacts_json[i : i + chunk_size]
        payload = {
            "jsonBody": chunk,
            "listIds": [57],
            "updateExistingContacts": True,
        }

        # Retry POST on rate limit
        r = None
        for _ in range(MAX_RETRIES + 1):
            rep = BREVO_SESSION.post(
                import_url,
                headers={**headers_brevo, "Content-Type": "application/json"},
                json=payload,
                timeout=60,
            )
            if rep.status_code == 429:
                time.sleep(REQUEST_DELAY)
                continue
            r = rep
            break

        if r and 200 <= r.status_code < 300:
            updated += len(chunk)
        else:
            failures.append({
                "start": i,
                "code": r.status_code if r else 500,
                "text": r.text if r else "No response",
            })

        # Honor rate-limit delay between chunks
        time.sleep(REQUEST_DELAY)

    return {"status": "success", "total": total, "updated": updated, "failures": failures}


@router.post("/user_updates")
async def compare_users(data: dict):
    """
    Compare Voatz users with Brevo contacts and return differences.

    Required fields: organizationId, WS, Csrf-Token, brevo_api_key, brevo_list_id
    Optional fields: voatz_blacklist
    """
    organization_id = data.get("organizationId")
    ws_token = data.get("WS")
    csrf_token = data.get("Csrf-Token")
    brevo_api_key = data.get("brevo_api_key")
    brevo_list_id = data.get("brevo_list_id")
    blacklist_raw = data.get("voatz_blacklist", [])

    if not all([organization_id, ws_token, csrf_token, brevo_api_key, brevo_list_id]):
        raise HTTPException(status_code=400, detail="Missing required fields.")

    # Normalize blacklist
    if isinstance(blacklist_raw, str):
        blacklist = set(v.strip() for v in blacklist_raw.split(",") if v.strip())
    elif isinstance(blacklist_raw, list):
        blacklist = set(str(v).strip() for v in blacklist_raw)
    else:
        blacklist = set()

    # Fetch voter list from Voatz
    users_list_url = "https://vapi-vrb.nimsim.com/voatz/customers/delegate/signups/byorg"
    headers_voatz = {
        "Accept-Encoding": "identity",
        "Content-Type": "application/json",
        "Origin": "http://vapi-vrb.nimsim.com",
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
            resp = requests.post(users_list_url, headers=headers_voatz, json=payload, timeout=60)
        except requests.RequestException as e:
            logger.error(f"Voatz API request failed: {e}")
            raise HTTPException(status_code=502, detail=f"Voatz API request failed: {e}")

        if resp.status_code != 200:
            return {
                "status": "error",
                "message": "Voatz API failed",
                "text": resp.text,
            }

        result = resp.json().get("result", [])
        if not result:
            break
        users.extend(result)
        min_id = resp.json().get("minId")

    def flatten_user(user):
        flattened = {
            "Voter_Id": None,
            "customerId": user.get("customerId"),
            "firstName": None,
            "lastName": None,
            "emailAddress": user.get("email"),
            "phone": user.get("phone"),
            "precinct": None,
            "birthDate": None,
            "zip5": None,
            "timestamp": user.get("timestamp"),
        }

        kv_pairs = user.get("orgVerificationStatus", {}).get("keyValues", [])
        for pair in kv_pairs:
            key = pair.get("key")
            value = pair.get("value")
            if not value:
                continue
            if key == "Voter_Id":
                flattened["Voter_Id"] = str(value).strip()
            elif key == "First_Name":
                flattened["firstName"] = str(value).strip()
            elif key == "Last_Name":
                flattened["lastName"] = str(value).strip()
            elif key == "Precinct":
                flattened["precinct"] = str(value).strip()
            elif key == "Birth_Date":
                flattened["birthDate"] = str(value).strip()
            elif key == "Zip5":
                flattened["zip5"] = str(value).strip()

        return flattened

    voatz_customer_ids = set()
    voatz_details_by_id = {}

    for user in users:
        flattened = flatten_user(user)
        customer_id = flattened.get("customerId")
        voter_id = flattened.get("Voter_Id")
        if not customer_id:
            continue
        if voter_id and voter_id in blacklist:
            continue
        cid_str = str(customer_id)
        voatz_customer_ids.add(cid_str)
        voatz_details_by_id[cid_str] = flattened

    # Fetch contacts from Brevo (keyed by VOATZ_ID)
    brevo_customer_ids = set()
    brevo_details_by_id = {}
    headers_brevo = {"Accept": "application/json", "api-key": brevo_api_key}
    offset = 0
    limit = 500
    base_url = f"https://api.brevo.com/v3/contacts/lists/{brevo_list_id}/contacts"

    while True:
        params = {"limit": limit, "offset": offset}
        try:
            brevo_resp = requests.get(
                base_url, headers=headers_brevo, params=params, timeout=60
            )
        except requests.RequestException as e:
            logger.error(f"Brevo API request failed: {e}")
            raise HTTPException(status_code=502, detail=f"Brevo API request failed: {e}")

        if brevo_resp.status_code != 200:
            return {
                "status": "error",
                "message": "Brevo API failed",
                "text": brevo_resp.text,
            }

        brevo_data = brevo_resp.json()
        contacts = brevo_data.get("contacts", [])
        for contact in contacts:
            voatz_id = contact.get("attributes", {}).get("VOATZ_ID")
            voter_id = contact.get("attributes", {}).get("VOTER_ID")
            email = contact.get("email")
            if not voatz_id:
                continue
            if voter_id and str(voter_id).strip() in blacklist:
                continue
            cid_str = str(voatz_id).strip()
            brevo_customer_ids.add(cid_str)
            brevo_details_by_id[cid_str] = {
                "customerId": cid_str,
                "Voter_Id": str(voter_id).strip() if voter_id else None,
                "emailAddress": email,
                "firstName": contact.get("attributes", {}).get("FIRSTNAME"),
                "lastName": contact.get("attributes", {}).get("LASTNAME"),
            }

        if len(contacts) < limit:
            break
        offset += limit

    added_ids = voatz_customer_ids - brevo_customer_ids
    removed_ids = brevo_customer_ids - voatz_customer_ids

    added_users = [voatz_details_by_id[cid] for cid in added_ids if cid in voatz_details_by_id]
    removed_users = [
        brevo_details_by_id[cid] for cid in removed_ids if cid in brevo_details_by_id
    ]

    return {
        "status": "success",
        "diff_mode": True,
        "added_users": added_users,
        "removed_users": removed_users,
        "api_total": len(voatz_customer_ids),
        "brevo_total": len(brevo_customer_ids),
        "new_count": len(added_users),
        "removed_count": len(removed_users),
    }
