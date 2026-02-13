"""
Scheduled user sync for DDP-API.

Periodically checks for user updates across all configured organizations,
automatically syncs changes to Brevo, and sends alerts to Zapier.
"""

import logging
import requests
import time
from datetime import datetime

from email_validator import validate_email, EmailNotValidError

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
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

# Overseas users list ID
OVERSEAS_LIST_ID = 58


def clean_email(email: str) -> str | None:
    """Pre-clean an email address before validation, then normalize via email-validator."""
    if not email:
        return None
    # Strip whitespace
    email = email.strip()
    # Strip leading/trailing dots from the whole address
    email = email.strip(".")
    # Clean up dots around the @ sign
    if "@" in email:
        local, domain = email.rsplit("@", 1)
        local = local.rstrip(".")
        domain = domain.strip(".")
        email = f"{local}@{domain}"
    # Validate and normalize
    try:
        result = validate_email(email, check_deliverability=False)
        return result.normalized
    except EmailNotValidError:
        return None


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


def is_us_phone_number(phone: str) -> bool:
    """
    Check if a phone number is a US number.

    US numbers are:
    - +1XXXXXXXXXX (12 chars with +)
    - 1XXXXXXXXXX (11 digits starting with 1)
    - XXXXXXXXXX (10 digits, assumed US)
    """
    if not phone:
        return True  # No phone = treat as domestic (don't add to overseas list)

    # Remove all non-digit characters except leading +
    import re
    cleaned = re.sub(r'[^\d+]', '', phone)

    # +1XXXXXXXXXX
    if cleaned.startswith('+1') and len(cleaned) == 12:
        return True

    # 1XXXXXXXXXX
    if cleaned.startswith('1') and len(cleaned) == 11:
        return True

    # XXXXXXXXXX (10-digit US local)
    if len(cleaned) == 10:
        return True

    # Also handle case where + was stripped but it's still 11 digits starting with 1
    digits_only = re.sub(r'\D', '', phone)
    if digits_only.startswith('1') and len(digits_only) == 11:
        return True
    if len(digits_only) == 10:
        return True

    return False


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
                timeout=180
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
        "customerId": user.get("customerId"),
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


def add_contacts_to_brevo(api_key: str, list_id: int, users: list[dict]) -> tuple[int, int, int]:
    """
    Add contacts to Brevo list.

    Non-US phone numbers are also added to the overseas list (ID 58).

    Returns tuple of (successful_count, failed_count, overseas_count).
    """
    if not users:
        return 0, 0, 0

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "api-key": api_key
    }

    # Build contact list for import
    contacts = []
    overseas_count = 0

    for user in users:
        # Get raw phone for overseas check
        raw_phone = user.get("phone", "")
        is_overseas = not is_us_phone_number(raw_phone)

        # Format phone number (remove non-digits, ensure starts with 1 for US)
        phone = raw_phone
        if phone:
            phone = "".join(c for c in phone if c.isdigit())
            if phone and not phone.startswith("1") and is_us_phone_number(raw_phone):
                phone = "1" + phone

        # Get state code from precinct
        state_code = get_state_code_from_precinct(user.get("precinct"))

        # Title case names
        first_name = user.get("firstName")
        last_name = user.get("lastName")
        if first_name:
            first_name = first_name.title()
        if last_name:
            last_name = last_name.title()

        # Determine list IDs - add to overseas list if non-US phone
        if is_overseas and raw_phone:
            list_ids = [list_id, OVERSEAS_LIST_ID]
            overseas_count += 1
        else:
            list_ids = [list_id]

        # Clean, validate, and normalize email
        raw_email = user.get("emailAddress")
        email = clean_email(raw_email)
        if not email:
            logger.warning(f"Skipping contact with invalid email: {raw_email}")
            continue

        contact = {
            "email": email,
            "attributes": {
                "FIRSTNAME": first_name,
                "LASTNAME": last_name,
                "VOTER_ID": user.get("Voter_Id"),
                "VOATZ_ID": user.get("customerId"),
                "BALLOT_ID": user.get("precinct"),
                "RESIDENCE_STATE": state_code,
                "RESIDENCE_ZIP": user.get("zip5"),
                "BIRTH_DATE": user.get("birthDate"),
                "SIGNUP_TIMESTAMP": user.get("timestamp"),
            },
            "listIds": list_ids,
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

    if overseas_count > 0:
        logger.info(f"Added {overseas_count} overseas users to list {OVERSEAS_LIST_ID}")

    return successful, failed, overseas_count


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

    # Extract customer IDs and details from Voatz
    voatz_customer_ids = set()
    voatz_details = {}
    voatz_blacklisted_count = 0
    voatz_no_customer_id_count = 0
    for user in voatz_users:
        flattened = flatten_voatz_user(user)
        customer_id = flattened.get("customerId")
        voter_id = flattened.get("Voter_Id")
        if not customer_id:
            voatz_no_customer_id_count += 1
        elif voter_id and voter_id in blacklist:
            voatz_blacklisted_count += 1
        else:
            cid_str = str(customer_id)
            voatz_customer_ids.add(cid_str)
            voatz_details[cid_str] = flattened

    # Fetch Brevo contacts
    brevo_contacts = fetch_brevo_contacts(brevo_api_key, brevo_list_id)
    logger.info(f"Fetched {len(brevo_contacts)} contacts from Brevo for {org_name}")

    # Extract customer IDs and emails from Brevo (keyed by VOATZ_ID)
    brevo_customer_ids = set()
    brevo_emails_by_customer_id = {}
    brevo_blacklisted_count = 0
    brevo_no_voatz_id_count = 0
    brevo_no_voatz_id_emails = []
    for contact in brevo_contacts:
        voatz_id = contact.get("attributes", {}).get("VOATZ_ID")
        voter_id = contact.get("attributes", {}).get("VOTER_ID")
        email = contact.get("email")
        if not voatz_id:
            brevo_no_voatz_id_count += 1
            if email:
                brevo_no_voatz_id_emails.append(email)
        elif voter_id and str(voter_id).strip() in blacklist:
            brevo_blacklisted_count += 1
        else:
            cid_str = str(voatz_id).strip()
            brevo_customer_ids.add(cid_str)
            if email:
                brevo_emails_by_customer_id[cid_str] = email

    # Diagnostic logging
    logger.info(f"  Voatz breakdown: {len(voatz_customer_ids)} valid, {voatz_blacklisted_count} blacklisted, {voatz_no_customer_id_count} no customer ID")
    logger.info(f"  Brevo breakdown: {len(brevo_customer_ids)} valid, {brevo_blacklisted_count} blacklisted, {brevo_no_voatz_id_count} no VOATZ_ID")

    # Calculate differences
    added_ids = voatz_customer_ids - brevo_customer_ids
    removed_ids = brevo_customer_ids - voatz_customer_ids

    # Log the differences
    logger.info(f"  Diff: {len(added_ids)} in Voatz but not Brevo, {len(removed_ids)} in Brevo but not Voatz")

    users_to_add = [voatz_details[cid] for cid in added_ids if cid in voatz_details]
    emails_to_remove = [brevo_emails_by_customer_id[cid] for cid in removed_ids if cid in brevo_emails_by_customer_id]

    # Also remove contacts that have no VOATZ_ID (no active Voatz account)
    emails_to_remove.extend(brevo_no_voatz_id_emails)

    # Log how many can actually be synced (have required data)
    if len(added_ids) != len(users_to_add):
        logger.warning(f"  {len(added_ids) - len(users_to_add)} users to add missing details")
    if len(removed_ids) != len(emails_to_remove):
        logger.warning(f"  {len(removed_ids) - len(emails_to_remove)} users to remove missing email")

    logger.info(f"Org {org_name}: {len(users_to_add)} to add, {len(emails_to_remove)} to remove")

    # Perform sync operations
    added_success, added_failed, overseas_count = 0, 0, 0
    removed_success, removed_failed = 0, 0

    if users_to_add:
        added_success, added_failed, overseas_count = add_contacts_to_brevo(brevo_api_key, brevo_list_id, users_to_add)
        logger.info(f"Org {org_name}: Added {added_success} contacts ({added_failed} failed, {overseas_count} overseas)")

    if emails_to_remove:
        removed_success, removed_failed = remove_contacts_from_brevo(brevo_api_key, brevo_list_id, emails_to_remove)
        logger.info(f"Org {org_name}: Removed {removed_success} contacts ({removed_failed} failed)")

    # Return summary if there were any changes
    if users_to_add or emails_to_remove:
        return {
            "organization_name": org_name,
            "organization_id": org_id,
            "voatz_total": len(voatz_customer_ids),
            "brevo_total": len(brevo_customer_ids),
            "added_count": added_success,
            "added_failed": added_failed,
            "overseas_count": overseas_count,
            "removed_count": removed_success,
            "removed_failed": removed_failed,
            "synced_at": datetime.utcnow().isoformat() + "Z"
        }

    return None


def full_sync_org(org_config: dict) -> dict | None:
    """
    Full-attribute sync for a single organization.

    Re-imports all Voatz users to Brevo, updating any changed attributes.
    Unlike sync_org(), this does not diff — it pushes all users through
    add_contacts_to_brevo() which uses updateExistingContacts: True.
    """
    org_name = org_config.get("name", "Unknown")
    org_id = org_config["voatz_org_id"]
    blacklist = set(str(b) for b in org_config.get("blacklist", []))
    brevo_api_key = org_config["brevo_api_key"]
    brevo_list_id = org_config["brevo_list_id"]

    logger.info(f"Full-attribute sync for org: {org_name} (ID: {org_id})")

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

    # Fetch all Voatz users
    voatz_users = fetch_voatz_users(ws_token, csrf_token, org_id)
    logger.info(f"Fetched {len(voatz_users)} users from Voatz for {org_name}")

    # Flatten and filter
    users_to_sync = []
    blacklisted_count = 0
    no_customer_id_count = 0

    for user in voatz_users:
        flattened = flatten_voatz_user(user)
        customer_id = flattened.get("customerId")
        voter_id = flattened.get("Voter_Id")

        if not customer_id:
            no_customer_id_count += 1
        elif voter_id and voter_id in blacklist:
            blacklisted_count += 1
        else:
            users_to_sync.append(flattened)

    logger.info(f"  Breakdown: {len(users_to_sync)} valid, {blacklisted_count} blacklisted, {no_customer_id_count} no customer ID")

    if not users_to_sync:
        logger.info(f"No users to sync for {org_name}")
        return None

    # Push all users to Brevo (updates existing contacts matched by email)
    added_success, added_failed, overseas_count = add_contacts_to_brevo(
        brevo_api_key, brevo_list_id, users_to_sync
    )
    logger.info(f"Org {org_name}: Synced {added_success} contacts ({added_failed} failed, {overseas_count} overseas)")

    return {
        "organization_name": org_name,
        "organization_id": org_id,
        "voatz_total": len(voatz_users),
        "synced_count": added_success,
        "synced_failed": added_failed,
        "overseas_count": overseas_count,
        "synced_at": datetime.utcnow().isoformat() + "Z"
    }


def push_alert_to_zapier(webhook_url: str, summaries: list[dict]) -> bool:
    """Push sync summary alert to Zapier webhook."""
    if not webhook_url:
        logger.error("No Zapier webhook URL configured")
        return False

    # Build summary message
    total_added = sum(s.get("added_count", 0) for s in summaries)
    total_removed = sum(s.get("removed_count", 0) for s in summaries)
    total_overseas = sum(s.get("overseas_count", 0) for s in summaries)

    payload = {
        "alert_type": "user_sync_complete",
        "summary": f"Synced {len(summaries)} organizations: {total_added} added ({total_overseas} overseas), {total_removed} removed",
        "total_added": total_added,
        "total_removed": total_removed,
        "total_overseas": total_overseas,
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


def run_full_sync_job():
    """Full-attribute sync job - re-imports all users to update attributes."""
    logger.info("Starting full-attribute sync job")

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
                summary = full_sync_org(merged_config)
                if summary:
                    all_summaries.append(summary)
            except Exception as e:
                org_name = org_config.get("name", "Unknown")
                logger.error(f"Error in full sync for org {org_name}: {e}")

        # Send alert to Zapier
        if all_summaries:
            total_synced = sum(s.get("synced_count", 0) for s in all_summaries)
            total_overseas = sum(s.get("overseas_count", 0) for s in all_summaries)

            payload = {
                "alert_type": "full_attribute_sync_complete",
                "summary": f"Full-attribute sync for {len(all_summaries)} organizations: {total_synced} contacts updated ({total_overseas} overseas)",
                "total_synced": total_synced,
                "total_overseas": total_overseas,
                "organizations_synced": len(all_summaries),
                "details": all_summaries,
                "synced_at": datetime.utcnow().isoformat() + "Z"
            }

            if webhook_url:
                try:
                    response = requests.post(webhook_url, json=payload, timeout=30)
                    if response.status_code == 200:
                        logger.info(f"Sent full sync alert to Zapier: {total_synced} contacts updated")
                    else:
                        logger.error(f"Zapier webhook failed: {response.status_code} - {response.text}")
                except Exception as e:
                    logger.error(f"Zapier webhook error: {e}")
        else:
            logger.info("No organizations synced in full-attribute sync")

    except Exception as e:
        logger.error(f"Full-attribute sync job failed: {e}")

    logger.info("Full-attribute sync job completed")


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

    _scheduler.add_job(
        run_full_sync_job,
        trigger=CronTrigger(day=1, hour=2),
        id="full_attribute_sync_job",
        name="Full-attribute sync on 1st of each month",
        replace_existing=True
    )

    _scheduler.start()
    logger.info(f"Scheduler started - syncing every {interval_minutes} minutes, full-attribute sync on 1st of month at 2 AM")

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
