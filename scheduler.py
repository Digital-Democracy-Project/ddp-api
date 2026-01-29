"""
Scheduled user sync for DDP-API.

Periodically checks for user updates across all configured organizations
and pushes changes to Zapier webhook.
"""

import logging
import requests
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


def check_org_updates(org_config: dict) -> dict | None:
    """
    Check for user updates for a single organization.

    Returns dict with update info if changes found, None otherwise.
    """
    org_name = org_config.get("name", "Unknown")
    org_id = org_config["voatz_org_id"]
    blacklist = set(org_config.get("blacklist", []))

    logger.info(f"Checking updates for org: {org_name} (ID: {org_id})")

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
    brevo_contacts = fetch_brevo_contacts(
        org_config["brevo_api_key"],
        org_config["brevo_list_id"]
    )
    logger.info(f"Fetched {len(brevo_contacts)} contacts from Brevo for {org_name}")

    # Extract voter IDs from Brevo
    brevo_voter_ids = set()
    brevo_details = {}
    for contact in brevo_contacts:
        voter_id = contact.get("attributes", {}).get("VOTER_ID")
        if voter_id:
            voter_id_str = str(voter_id).strip()
            if voter_id_str and voter_id_str not in blacklist:
                brevo_voter_ids.add(voter_id_str)
                brevo_details[voter_id_str] = {
                    "Voter_Id": voter_id_str,
                    "emailAddress": contact.get("email"),
                    "firstName": contact.get("attributes", {}).get("FIRSTNAME"),
                    "lastName": contact.get("attributes", {}).get("LASTNAME")
                }

    # Calculate differences
    added_ids = voatz_voter_ids - brevo_voter_ids
    removed_ids = brevo_voter_ids - voatz_voter_ids

    added_users = [voatz_details[vid] for vid in added_ids if vid in voatz_details]
    removed_users = [brevo_details[vid] for vid in removed_ids if vid in brevo_details]

    logger.info(f"Org {org_name}: {len(added_users)} added, {len(removed_users)} removed")

    # Return results if there are changes
    if added_users or removed_users:
        return {
            "organization_name": org_name,
            "organization_id": org_id,
            "added_users": added_users,
            "removed_users": removed_users,
            "voatz_total": len(voatz_voter_ids),
            "brevo_total": len(brevo_voter_ids),
            "new_count": len(added_users),
            "removed_count": len(removed_users),
            "checked_at": datetime.utcnow().isoformat() + "Z"
        }

    return None


def push_to_zapier(webhook_url: str, updates: list[dict]) -> bool:
    """Push updates to Zapier webhook."""
    if not webhook_url:
        logger.error("No Zapier webhook URL configured")
        return False

    payload = {
        "updates": updates,
        "total_organizations_with_changes": len(updates),
        "checked_at": datetime.utcnow().isoformat() + "Z"
    }

    try:
        response = requests.post(webhook_url, json=payload, timeout=30)
        if response.status_code == 200:
            logger.info(f"Successfully pushed {len(updates)} org updates to Zapier")
            return True
        else:
            logger.error(f"Zapier webhook failed: {response.status_code} - {response.text}")
    except Exception as e:
        logger.error(f"Zapier webhook error: {e}")

    return False


def run_sync_job():
    """Main sync job - checks all orgs and pushes updates to Zapier."""
    logger.info("Starting scheduled user sync job")

    try:
        config = get_config()
        organizations = config.get("organizations", [])
        webhook_url = config.get("zapier_webhook_url")

        # Root-level defaults (shared across all orgs)
        root_brevo_api_key = config.get("brevo_api_key")
        root_blacklist = config.get("blacklist", [])

        all_updates = []

        for org_config in organizations:
            try:
                # Merge root-level defaults with org-specific config
                # Org-level values override root-level if present
                merged_config = {
                    **org_config,
                    "brevo_api_key": org_config.get("brevo_api_key") or root_brevo_api_key,
                    "blacklist": org_config.get("blacklist") if org_config.get("blacklist") else root_blacklist,
                }
                update = check_org_updates(merged_config)
                if update:
                    all_updates.append(update)
            except Exception as e:
                org_name = org_config.get("name", "Unknown")
                logger.error(f"Error checking org {org_name}: {e}")

        # Push to Zapier if there are any updates
        if all_updates:
            push_to_zapier(webhook_url, all_updates)
        else:
            logger.info("No updates found across all organizations")

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
        name="Check for user updates across all organizations",
        replace_existing=True
    )

    _scheduler.start()
    logger.info(f"Scheduler started - checking every {interval_minutes} minutes")

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
