"""Tests for Brevo phone number conflict resolution during sync."""

import unittest
from unittest.mock import patch, MagicMock, call

import scheduler


class DummyResp:
    def __init__(self, status_code, data=None, text=""):
        self.status_code = status_code
        self._data = data or {}
        self.text = text

    def json(self):
        return self._data


# ---------------------------------------------------------------------------
# clear_phone_from_brevo_contact
# ---------------------------------------------------------------------------

class TestClearPhoneFromBrevoContact(unittest.TestCase):

    @patch("scheduler.time.sleep")
    @patch("scheduler.requests.get")
    def test_no_conflict_404(self, mock_get, mock_sleep):
        """Phone not found in Brevo — no conflict."""
        mock_get.return_value = DummyResp(404)
        result = scheduler.clear_phone_from_brevo_contact("key", "15551234567")
        self.assertTrue(result)
        mock_get.assert_called_once()

    @patch("scheduler.time.sleep")
    @patch("scheduler.requests.put")
    @patch("scheduler.requests.get")
    def test_different_email_owner_cleared(self, mock_get, mock_put, mock_sleep):
        """Phone owned by contact with different email — clear via PUT."""
        mock_get.return_value = DummyResp(200, {"email": "old@example.com"})
        mock_put.return_value = DummyResp(204)

        result = scheduler.clear_phone_from_brevo_contact("key", "15551234567")
        self.assertTrue(result)
        # PUT should target the owning contact's email
        put_call = mock_put.call_args
        self.assertIn("old@example.com", put_call.args[0])
        self.assertEqual(put_call.kwargs["json"]["sms"], "")
        self.assertEqual(put_call.kwargs["json"]["attributes"]["WHATSAPP"], "")

    @patch("scheduler.time.sleep")
    @patch("scheduler.requests.delete")
    @patch("scheduler.requests.get")
    def test_emailless_owner_deleted(self, mock_get, mock_delete, mock_sleep):
        """Phone owned by contact with no email — delete orphan."""
        mock_get.return_value = DummyResp(200, {"email": None})
        mock_delete.return_value = DummyResp(204)

        result = scheduler.clear_phone_from_brevo_contact("key", "15551234567")
        self.assertTrue(result)
        mock_delete.assert_called_once()

    @patch("scheduler.time.sleep")
    @patch("scheduler.requests.put")
    @patch("scheduler.requests.get")
    def test_put_failure_returns_false(self, mock_get, mock_put, mock_sleep):
        """PUT to clear phone fails — return False."""
        mock_get.return_value = DummyResp(200, {"email": "old@example.com"})
        mock_put.return_value = DummyResp(500, text="Server Error")

        result = scheduler.clear_phone_from_brevo_contact("key", "15551234567")
        self.assertFalse(result)

    @patch("scheduler.time.sleep")
    @patch("scheduler.requests.get")
    def test_get_failure_returns_false(self, mock_get, mock_sleep):
        """GET lookup fails — return False."""
        mock_get.return_value = DummyResp(500, text="Server Error")

        result = scheduler.clear_phone_from_brevo_contact("key", "15551234567")
        self.assertFalse(result)


# ---------------------------------------------------------------------------
# resolve_phone_ownership
# ---------------------------------------------------------------------------

class TestResolvePhoneOwnership(unittest.TestCase):

    def test_cross_org_claimed_different_email(self):
        """Phone already claimed by another org's contact — skip."""
        claimed = {"15551234567": "other@example.com"}
        brevo = {}
        result = scheduler.resolve_phone_ownership(
            "key", "15551234567", "new@example.com", claimed, brevo
        )
        self.assertFalse(result)

    def test_brevo_same_email_no_conflict(self):
        """Same email already owns phone in Brevo — no API calls needed."""
        claimed = {}
        brevo = {"15551234567": "new@example.com"}
        result = scheduler.resolve_phone_ownership(
            "key", "15551234567", "New@Example.com", claimed, brevo
        )
        self.assertTrue(result)
        self.assertEqual(claimed["15551234567"], "new@example.com")

    @patch("scheduler.time.sleep")
    @patch("scheduler.requests.put")
    def test_brevo_different_email_cleared(self, mock_put, mock_sleep):
        """Different email owns phone in Brevo — clear and claim."""
        mock_put.return_value = DummyResp(204)
        claimed = {}
        brevo = {"15551234567": "old@example.com"}

        result = scheduler.resolve_phone_ownership(
            "key", "15551234567", "new@example.com", claimed, brevo
        )
        self.assertTrue(result)
        self.assertEqual(claimed["15551234567"], "new@example.com")
        self.assertEqual(brevo["15551234567"], "new@example.com")
        # Verify PUT cleared the old owner
        put_call = mock_put.call_args
        self.assertIn("old@example.com", put_call.args[0])

    @patch("scheduler.time.sleep")
    @patch("scheduler.requests.put")
    def test_brevo_different_email_clear_fails(self, mock_put, mock_sleep):
        """PUT to clear phone from old owner fails — don't claim."""
        mock_put.return_value = DummyResp(500)
        claimed = {}
        brevo = {"15551234567": "old@example.com"}

        result = scheduler.resolve_phone_ownership(
            "key", "15551234567", "new@example.com", claimed, brevo
        )
        self.assertFalse(result)
        self.assertNotIn("15551234567", claimed)

    @patch("scheduler.clear_phone_from_brevo_contact")
    def test_brevo_emailless_owner_cleared(self, mock_clear):
        """Email-less contact owns phone in Brevo — clear orphan and claim."""
        mock_clear.return_value = True
        claimed = {}
        brevo = {"15551234567": None}

        result = scheduler.resolve_phone_ownership(
            "key", "15551234567", "new@example.com", claimed, brevo
        )
        self.assertTrue(result)
        mock_clear.assert_called_once_with("key", "15551234567")
        self.assertEqual(claimed["15551234567"], "new@example.com")
        self.assertEqual(brevo["15551234567"], "new@example.com")

    @patch("scheduler.clear_phone_from_brevo_contact")
    def test_phone_not_in_brevo_phones_live_lookup(self, mock_clear):
        """Phone not in brevo_phones — live lookup resolves it."""
        mock_clear.return_value = True
        claimed = {}
        brevo = {}

        result = scheduler.resolve_phone_ownership(
            "key", "15551234567", "new@example.com", claimed, brevo
        )
        self.assertTrue(result)
        mock_clear.assert_called_once_with("key", "15551234567")
        self.assertEqual(claimed["15551234567"], "new@example.com")

    @patch("scheduler.clear_phone_from_brevo_contact")
    def test_phone_not_in_brevo_phones_lookup_fails(self, mock_clear):
        """Phone not in brevo_phones and live lookup fails — skip phone."""
        mock_clear.return_value = False
        claimed = {}
        brevo = {}

        result = scheduler.resolve_phone_ownership(
            "key", "15551234567", "new@example.com", claimed, brevo
        )
        self.assertFalse(result)
        self.assertNotIn("15551234567", claimed)


# ---------------------------------------------------------------------------
# add_contacts_to_brevo integration with resolve_phone_ownership
# ---------------------------------------------------------------------------

class TestAddContactsPhoneResolution(unittest.TestCase):

    @patch("scheduler.time.sleep")
    @patch("scheduler.requests.post")
    @patch("scheduler.resolve_phone_ownership")
    def test_contact_gets_phone_when_resolved(self, mock_resolve, mock_post, mock_sleep):
        """Phone is assigned when resolve_phone_ownership returns True."""
        mock_resolve.return_value = True
        mock_post.return_value = DummyResp(202)

        users = [{
            "emailAddress": "user@example.com",
            "customerId": "123",
            "phone": "5551234567",
            "firstName": "Test",
            "lastName": "User",
            "Voter_Id": "V1",
            "precinct": "FLORIDA-1",
            "birthDate": None,
            "zip5": None,
            "timestamp": None,
        }]

        success, failed, overseas = scheduler.add_contacts_to_brevo(
            "key", 1, users, {}, {}
        )
        self.assertEqual(success, 1)

        # Verify the import payload included sms/WHATSAPP
        post_call = mock_post.call_args
        contacts = post_call.kwargs["json"]["jsonBody"]
        self.assertEqual(contacts[0]["sms"], "15551234567")
        self.assertEqual(contacts[0]["attributes"]["WHATSAPP"], "15551234567")

    @patch("scheduler.time.sleep")
    @patch("scheduler.requests.post")
    @patch("scheduler.resolve_phone_ownership")
    def test_contact_skips_phone_when_unresolved(self, mock_resolve, mock_post, mock_sleep):
        """Phone is omitted when resolve_phone_ownership returns False."""
        mock_resolve.return_value = False
        mock_post.return_value = DummyResp(202)

        users = [{
            "emailAddress": "user@example.com",
            "customerId": "123",
            "phone": "5551234567",
            "firstName": "Test",
            "lastName": "User",
            "Voter_Id": "V1",
            "precinct": "FLORIDA-1",
            "birthDate": None,
            "zip5": None,
            "timestamp": None,
        }]

        success, failed, overseas = scheduler.add_contacts_to_brevo(
            "key", 1, users, {}, {}
        )
        self.assertEqual(success, 1)

        # Verify the import payload did NOT include sms/WHATSAPP
        post_call = mock_post.call_args
        contacts = post_call.kwargs["json"]["jsonBody"]
        self.assertNotIn("sms", contacts[0])
        self.assertNotIn("WHATSAPP", contacts[0]["attributes"])


# ---------------------------------------------------------------------------
# sync_org seeds brevo_phones from email-less contacts
# ---------------------------------------------------------------------------

class TestSyncOrgBrevoPhones(unittest.TestCase):

    @patch("scheduler.time.sleep")
    @patch("scheduler.requests.post")
    @patch("scheduler.remove_contacts_from_brevo", return_value=(0, 0))
    @patch("scheduler.add_contacts_to_brevo", return_value=(1, 0, 0))
    @patch("scheduler.fetch_brevo_contacts")
    @patch("scheduler.fetch_voatz_users")
    @patch("scheduler.get_voatz_tokens")
    def test_emailless_contacts_seeded_in_brevo_phones(
        self, mock_tokens, mock_voatz, mock_brevo, mock_add, mock_remove,
        mock_post, mock_sleep
    ):
        """Email-less Brevo contacts with WHATSAPP are tracked in brevo_phones."""
        mock_tokens.return_value = ("ws", "csrf")
        mock_voatz.return_value = [{
            "customerId": "123",
            "email": "new@example.com",
            "phone": "15551234567",
            "orgVerificationStatus": {"keyValues": [
                {"key": "Voter_Id", "value": "V1"},
                {"key": "First_Name", "value": "Test"},
                {"key": "Last_Name", "value": "User"},
            ]},
        }]
        # Brevo has an email-less contact with a phone, plus a normal contact
        mock_brevo.return_value = [
            {
                "email": None,
                "attributes": {"WHATSAPP": "15551234567", "VOTER_ID": None}
            },
            {
                "email": "existing@example.com",
                "attributes": {"WHATSAPP": "15559999999", "VOTER_ID": None}
            },
        ]

        org_config = {
            "name": "TestOrg",
            "voatz_org_id": 1,
            "voatz_email": "e",
            "voatz_password": "p",
            "brevo_api_key": "key",
            "brevo_list_id": 1,
            "blacklist": [],
        }

        claimed_phones = {}
        scheduler.sync_org(org_config, claimed_phones)

        # Verify add_contacts_to_brevo was called with brevo_phones
        add_call = mock_add.call_args
        brevo_phones_arg = add_call.args[4] if len(add_call.args) > 4 else add_call.kwargs.get("brevo_phones", {})
        # Email-less contact phone should be None
        self.assertIsNone(brevo_phones_arg.get("15551234567"))
        # Normal contact phone should map to email
        self.assertEqual(brevo_phones_arg.get("15559999999"), "existing@example.com")


# ---------------------------------------------------------------------------
# End-to-end: phantom diff scenario
# ---------------------------------------------------------------------------

class TestPhantomDiffResolution(unittest.TestCase):

    @patch("scheduler.time.sleep")
    @patch("scheduler.requests.delete")
    @patch("scheduler.requests.get")
    @patch("scheduler.requests.post")
    @patch("scheduler.fetch_brevo_contacts")
    @patch("scheduler.fetch_voatz_users")
    @patch("scheduler.get_voatz_tokens")
    def test_phantom_diff_resolved(
        self, mock_tokens, mock_voatz, mock_brevo_fetch,
        mock_post, mock_get, mock_delete, mock_sleep
    ):
        """
        Scenario: email-less Brevo contact owns a phone. Same person
        registers in Voatz with that phone and an email. First sync
        should resolve the conflict and import successfully.
        """
        mock_tokens.return_value = ("ws", "csrf")
        mock_voatz.return_value = [{
            "customerId": "C1",
            "email": "voter@example.com",
            "phone": "15551234567",
            "orgVerificationStatus": {"keyValues": [
                {"key": "Voter_Id", "value": "V1"},
                {"key": "First_Name", "value": "Voter"},
                {"key": "Last_Name", "value": "One"},
            ]},
        }]
        # Brevo has the email-less orphan with that phone
        mock_brevo_fetch.return_value = [
            {
                "email": None,
                "attributes": {"WHATSAPP": "15551234567", "VOTER_ID": None}
            },
        ]

        # clear_phone_from_brevo_contact will GET the phone owner, then DELETE
        mock_get.return_value = DummyResp(200, {"email": None})
        mock_delete.return_value = DummyResp(204)
        # Import call
        mock_post.return_value = DummyResp(202)

        org_config = {
            "name": "Florida",
            "voatz_org_id": 1,
            "voatz_email": "e",
            "voatz_password": "p",
            "brevo_api_key": "key",
            "brevo_list_id": 10,
            "blacklist": [],
        }

        result = scheduler.sync_org(org_config, {})
        self.assertIsNotNone(result)
        self.assertEqual(result["added_count"], 1)

        # The import POST should have been called with the phone
        import_call = mock_post.call_args
        contacts = import_call.kwargs["json"]["jsonBody"]
        self.assertEqual(contacts[0]["sms"], "15551234567")
        self.assertEqual(contacts[0]["attributes"]["WHATSAPP"], "15551234567")


if __name__ == "__main__":
    unittest.main()
