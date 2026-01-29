"""
Scheduled user sync for DDP-API.

Periodically checks for user updates across all configured organizations,
automatically syncs changes to Brevo, and sends alerts to Zapier.
"""

import logging
import requests
import time
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from config import get_config

logger = logging.getLogger(__name__)

# Voatz API endpoints
LOGIN_URL = "https://vapi-vrb.nimsim.com/voatz/organizations/users/login"
USERS_URL = "https://vapi-vrb.nimsim.com/voatz/customers/delegate/signups/byorg"

LOGIN_HEADERS = {
    'Accept-Encoding': 'identity',
    'Content-Type': 'application/json',
    'Origin': 'http://vapi-vrb.nimsim.com'
}

# State name to 2-letter code mapping
STATE_CODES = {
    "ALABAMA": "AL", "ALASKA": "AK", "ARIZONA": "AZ", "ARKANSAS": "AR",
    "CALIFORNIA": "CA", "COLORADO": "CO", "CONNECTICUT": "CT", "DELAWARE": "DE",
    "FLORIDA": "FL", "GEORGIA": "GA", "HAWAII": "HI", "IDAHO": "ID",
    "ILLINOIS": "IL", "INDIANA": "IN", "IOWA": "IA", "KANSAS": "KS",
    "KENTUCKY": "KY", "LOUISIANA": "LA", "MAINE": "ME", "MARYLAND": "MD",
    "MASSACHUSETTS": "MA", "MICHIGAN": "MI", "MINNESOTA": "MN", "MISSISSIPPI": "MS",
    "MISSOURI": "MO", "MONTANA": "MT", "NEBRASKA": "NE", "NEVADA": "NV",
    "NEW HAMPSHIRE": "NH", "NEW JERSEY": "NJ", "NEW MEXICO": "NM", "NEW YORK": "NY",
    "NORTH CAROLINA": "NC", "NORTH DAKOTA": "ND", "OHIO": "OH", "OKLAHOMA": "OK",
    "OREGON": "OR", "PENNSYLVANIA": "PA", "RHODE ISLAND": "RI", "SOUTH CAROLINA": "SC",
    "SOUTH DAKOTA": "SD", "TENNESSEE": "TN", "TEXAS": "TX", "UTAH": "UT",
    "VERMONT": "VT", "VIRGINIA": "VA", "WASHINGTON": "WA", "WEST VIRGINIA": "WV",
    "WISCONSIN": "WI", "WYOMING": "WY", "DISTRICT OF COLUMBIA": "DC"
}


def get_state_code_from_precinct(precinct: str) -> str | None:
    """Extract state code from precinct string (e.g., 'FLORIDA-SEM-7-38-10' -> 'FL')."""
    if not precinct:
        return None

    # Precinct format is typically "STATE-..."
    parts = precinct.upper().split("-")
    if parts:
        state_name = parts[0]
        return STATE_CODES.get(state_name)

    return None


def get_voatz_tokens(email: str, password: str, org_id: int) -> tuple[str, str] | None:
    """Authenticate with Voatz and get WS/CSRF tokens."""
    payload = {
        "emailAddress": email,
        "password": password,
        "authData": [{"key": "organizationid", "value": str(org_id)}]
    }

    try:
        response = requests.post(LOGIN_URL, headers=LOGIN_HEADERS, json=payload, timeout=30)
        if response.status_code == 200 and response.text.strip() == "OK":
            ws_token = response.cookies.get('WS') or response.headers.get('WS')
            csrf_token = response.cookies.get('Csrf-Token') or response.headers.get('Csrf-Token')
            if ws_token and csrf_token:
                return ws_token, csrf_token
        logger.error(f"Voatz login failed for org {org_id}: {response.status_code} - {response.text}")
    except Exception as e:
        logger.error(f"Voatz login error for org {org_id}: {e}")

    return None


def fetch_voatz_users(ws_token: str, csrf_token: str, org_id: int) -> list[dict]:
    """Fetch all users from Voatz for an organization."""
    headers = {
        'Accept-Encoding': 'identity',
        'Content-Type': 'application/json',
        'Origin': 'http://vapi-vrb.nimsim.com',
        'WS': ws_token,
        'Csrf-Token': csrf_token,
        'Cookie': f"WS={ws_token}; Csrf-Token={csrf_token}"
    }

    users = []
    min_id = None

    while True:
        payload = {"organizationId": org_id, "limit": 1000}
        if min_id:
            payload["minId"] = min_id

        try:
            response = requests.post(USERS_URL, headers=headers, json=payload, timeout=60)
            if response.status_code != 200:
                logger.error(f"Voatz users fetch failed: {response.status_code}")
                break

            data = response.json()
            result = data.get("result", [])
            if not result:
                break

            users.extend(result)
            min_id = data.get("minId")

        except Exception as e:
            logger.error(f"Voatz users fetch error: {e}")
            break

    return users


def fetch_brevo_contacts(api_key: str, list_id: int) -> list[dict]:
    """Fetch all contacts from a Brevo list."""
    headers = {
        "Accept": "application/json",
        "api-key": api_key
    }

    contacts = []
    offset = 0
    limit = 500
    base_url = f"https://api.brevo.com/v3/contacts/lists/{list_id}/contacts"

    while True:
        try:
            response = requests.get(
                base_url,
                headers=headers,
                params={"limit": limit, "offset": offset},
                timeout=60
            )
            if response.status_code != 200:
                logger.error(f"Brevo fetch failed: {response.status_code} - {response.text}")
                break

            data = response.json()
            page = data.get("contacts", [])
            if not page:
                break

            contacts.extend(page)
            if len(page) < limit:
                break
            offset += limit

        except Exception as e:
            logger.error(f"Brevo fetch error: {e}")
            break

    return contacts


def flatten_voatz_user(user: dict) -> dict:
    """Flatten Voatz user structure for comparison."""
    flattened = {
        "Voter_Id": None,
        "firstName": None,
        "lastName": None,
        "emailAddress": user.get("email"),
        "phone": user.get("phone"),
        "precinct": None,
        "birthDate": None,
        "zip5": None,
        "timestamp": user.get("timestamp")
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


def add_contacts_to_brevo(api_key: str, list_id: int, users: list[dict]) -> tuple[int, int]:
    """
    Add contacts to Brevo list.

    Returns tuple of (successful_count, failed_count).
    """
    if not users:
        return 0, 0

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "api-key": api_key
    }

    # Build contact list for import
    contacts = []
    for user in users:
        # Format phone number (remove non-digits, ensure starts with 1 for US)
        phone = user.get("phone", "")
        if phone:
            phone = "".join(c for c in phone if c.isdigit())
            if phone and not phone.startswith("1"):
                phone = "1" + phone

        # Get state code from precinct
        state_code = get_state_code_from_precinct(user.get("precinct"))

        contact = {
            "email": user.get("emailAddress"),
            "attributes": {
                "FIRSTNAME": user.get("firstName"),
                "LASTNAME": user.get("lastName"),
                "VOTER_ID": user.get("Voter_Id"),
                "BALLOT_ID": user.get("precinct"),
                "RESIDENCE_STATE": state_code,
                "RESIDENCE_ZIP": user.get("zip5"),
                "BIRTH_DATE": user.get("birthDate"),
                "SIGNUP_TIMESTAMP": user.get("timestamp"),
            },
            "listIds": [list_id],
            "updateEnabled": True,
            "emailBlacklisted": False,
            "smsBlacklisted": False
        }

        # Add phone/SMS if available
        if phone:
            contact["sms"] = phone
            contact["attributes"]["WHATSAPP"] = phone

        contacts.append(contact)

    # Use Brevo import endpoint for bulk add
    import_url = "https://api.brevo.com/v3/contacts/import"

    successful = 0
    failed = 0
    chunk_size = 500  # Brevo recommends max 500 per request

    for i in range(0, len(contacts), chunk_size):
        chunk = contacts[i:i + chunk_size]
        payload = {
            "jsonBody": chunk,
            "listIds": [list_id],
            "updateExistingContacts": True
        }

        try:
            response = requests.post(import_url, headers=headers, json=payload, timeout=60)
            if 200 <= response.status_code < 300:
                successful += len(chunk)
                logger.info(f"Added {len(chunk)} contacts to Brevo list {list_id}")
            else:
                failed += len(chunk)
                logger.error(f"Brevo import failed: {response.status_code} - {response.text}")
        except Exception as e:
            failed += len(chunk)
            logger.error(f"Brevo import error: {e}")

        # Rate limiting delay
        time.sleep(0.1)

    return successful, failed


def remove_contacts_from_brevo(api_key: str, list_id: int, emails: list[str]) -> tuple[int, int]:
    """
    Remove contacts from Brevo list.

    Returns tuple of (successful_count, failed_count).
    """
    if not emails:
        return 0, 0

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "api-key": api_key
    }

    successful = 0
    failed = 0

    # Remove contacts from list (not deleting them entirely, just from this list)
    remove_url = f"https://api.brevo.com/v3/contacts/lists/{list_id}/contacts/remove"

    # Process in chunks
    chunk_size = 150  # Brevo limit for this endpoint

    for i in range(0, len(emails), chunk_size):
        chunk = emails[i:i + chunk_size]
        payload = {"emails": chunk}

        try:
            response = requests.post(remove_url, headers=headers, json=payload, timeout=60)
            if 200 <= response.status_code < 300:
                successful += len(chunk)
                logger.info(f"Removed {len(chunk)} contacts from Brevo list {list_id}")
            else:
                failed += len(chunk)
                logger.error(f"Brevo remove failed: {response.status_code} - {response.text}")
        except Exception as e:
            failed += len(chunk)
            logger.error(f"Brevo remove error: {e}")

        # Rate limiting delay
        time.sleep(0.1)

    return successful, failed


def sync_org(org_config: dict) -> dict | None:
    """
    Sync users for a single organization.

    - Adds new users to Brevo
    - Removes departed users from Brevo
    - Returns summary of changes
    """
    org_name = org_config.get("name", "Unknown")
    org_id = org_config["voatz_org_id"]
    blacklist = set(str(b) for b in org_config.get("blacklist", []))
    brevo_api_key = org_config["brevo_api_key"]
    brevo_list_id = org_config["brevo_list_id"]

    logger.info(f"Syncing org: {org_name} (ID: {org_id})")

    # Authenticate with Voatz
    tokens = get_voatz_tokens(
        org_config["voatz_email"],
        org_config["voatz_password"],
        org_id
    )
    if not tokens:
        logger.error(f"Failed to authenticate for org: {org_name}")
        return None

    ws_token, csrf_token = tokens

    # Fetch Voatz users
    voatz_users = fetch_voatz_users(ws_token, csrf_token, org_id)
    logger.info(f"Fetched {len(voatz_users)} users from Voatz for {org_name}")

    # Extract voter IDs and details from Voatz
    voatz_voter_ids = set()
    voatz_details = {}
    for user in voatz_users:
        flattened = flatten_voatz_user(user)
        voter_id = flattened.get("Voter_Id")
        if voter_id and voter_id not in blacklist:
            voatz_voter_ids.add(voter_id)
            voatz_details[voter_id] = flattened

    # Fetch Brevo contacts
    brevo_contacts = fetch_brevo_contacts(brevo_api_key, brevo_list_id)
    logger.info(f"Fetched {len(brevo_contacts)} contacts from Brevo for {org_name}")

    # Extract voter IDs and emails from Brevo
    brevo_voter_ids = set()
    brevo_emails_by_voter_id = {}
    for contact in brevo_contacts:
        voter_id = contact.get("attributes", {}).get("VOTER_ID")
        email = contact.get("email")
        if voter_id:
            voter_id_str = str(voter_id).strip()
            if voter_id_str and voter_id_str not in blacklist:
                brevo_voter_ids.add(voter_id_str)
                if email:
                    brevo_emails_by_voter_id[voter_id_str] = email

    # Calculate differences
    added_ids = voatz_voter_ids - brevo_voter_ids
    removed_ids = brevo_voter_ids - voatz_voter_ids

    users_to_add = [voatz_details[vid] for vid in added_ids if vid in voatz_details]
    emails_to_remove = [brevo_emails_by_voter_id[vid] for vid in removed_ids if vid in brevo_emails_by_voter_id]

    logger.info(f"Org {org_name}: {len(users_to_add)} to add, {len(emails_to_remove)} to remove")

    # Perform sync operations
    added_success, added_failed = 0, 0
    removed_success, removed_failed = 0, 0

    if users_to_add:
        added_success, added_failed = add_contacts_to_brevo(brevo_api_key, brevo_list_id, users_to_add)
        logger.info(f"Org {org_name}: Added {added_success} contacts ({added_failed} failed)")

    if emails_to_remove:
        removed_success, removed_failed = remove_contacts_from_brevo(brevo_api_key, brevo_list_id, emails_to_remove)
        logger.info(f"Org {org_name}: Removed {removed_success} contacts ({removed_failed} failed)")

    # Return summary if there were any changes
    if users_to_add or emails_to_remove:
        return {
            "organization_name": org_name,
            "organization_id": org_id,
            "voatz_total": len(voatz_voter_ids),
            "brevo_total": len(brevo_voter_ids),
            "added_count": added_success,
            "added_failed": added_failed,
            "removed_count": removed_success,
            "removed_failed": removed_failed,
            "synced_at": datetime.utcnow().isoformat() + "Z"
        }

    return None


def push_alert_to_zapier(webhook_url: str, summaries: list[dict]) -> bool:
    """Push sync summary alert to Zapier webhook."""
    if not webhook_url:
        logger.error("No Zapier webhook URL configured")
        return False

    # Build summary message
    total_added = sum(s.get("added_count", 0) for s in summaries)
    total_removed = sum(s.get("removed_count", 0) for s in summaries)

    payload = {
        "alert_type": "user_sync_complete",
        "summary": f"Synced {len(summaries)} organizations: {total_added} added, {total_removed} removed",
        "total_added": total_added,
        "total_removed": total_removed,
        "organizations_synced": len(summaries),
        "details": summaries,
        "synced_at": datetime.utcnow().isoformat() + "Z"
    }

    try:
        response = requests.post(webhook_url, json=payload, timeout=30)
        if response.status_code == 200:
            logger.info(f"Successfully sent sync alert to Zapier: {total_added} added, {total_removed} removed")
            return True
        else:
            logger.error(f"Zapier webhook failed: {response.status_code} - {response.text}")
    except Exception as e:
        logger.error(f"Zapier webhook error: {e}")

    return False


def run_sync_job():
    """Main sync job - syncs all orgs and sends alert to Zapier."""
    logger.info("Starting scheduled user sync job")

    try:
        config = get_config()
        organizations = config.get("organizations", [])
        webhook_url = config.get("zapier_webhook_url")

        # Root-level defaults (shared across all orgs)
        root_brevo_api_key = config.get("brevo_api_key")
        root_blacklist = config.get("blacklist", [])

        all_summaries = []

        for org_config in organizations:
            try:
                # Merge root-level defaults with org-specific config
                merged_config = {
                    **org_config,
                    "brevo_api_key": org_config.get("brevo_api_key") or root_brevo_api_key,
                    "blacklist": org_config.get("blacklist") if org_config.get("blacklist") else root_blacklist,
                }
                summary = sync_org(merged_config)
                if summary:
                    all_summaries.append(summary)
            except Exception as e:
                org_name = org_config.get("name", "Unknown")
                logger.error(f"Error syncing org {org_name}: {e}")

        # Send alert to Zapier if there were any changes
        if all_summaries:
            push_alert_to_zapier(webhook_url, all_summaries)
        else:
            logger.info("No changes found across all organizations")

    except Exception as e:
        logger.error(f"Sync job failed: {e}")

    logger.info("Scheduled user sync job completed")


# Scheduler instance
_scheduler = None


def start_scheduler(app=None):
    """Start the background scheduler."""
    global _scheduler

    if _scheduler is not None:
        logger.warning("Scheduler already running")
        return _scheduler

    config = get_config()
    interval_minutes = config.get("sync_interval_minutes", 30)

    _scheduler = BackgroundScheduler()
    _scheduler.add_job(
        run_sync_job,
        trigger=IntervalTrigger(minutes=interval_minutes),
        id="user_sync_job",
        name="Sync users across all organizations",
        replace_existing=True
    )

    _scheduler.start()
    logger.info(f"Scheduler started - syncing every {interval_minutes} minutes")

    # Run immediately on startup
    run_sync_job()

    return _scheduler


def stop_scheduler():
    """Stop the background scheduler."""
    global _scheduler
    if _scheduler:
        _scheduler.shutdown()
        _scheduler = None
        logger.info("Scheduler stopped")
