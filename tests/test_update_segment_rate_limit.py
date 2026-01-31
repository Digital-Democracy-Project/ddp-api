"""Test rate limiting behavior for update_segment_attribute endpoint."""

import os
import unittest
from unittest.mock import patch, MagicMock

# Set test environment before importing app
os.environ["API_BEARER_TOKEN"] = "testtoken"

from fastapi.testclient import TestClient
from app.main import app
from app.routes import brevo


class DummyResp:
    def __init__(self, status_code, data=None, text=""):
        self.status_code = status_code
        self._data = data or {}
        self.text = text

    def json(self):
        return self._data


class TestUpdateSegmentAttributeRateLimit(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_rate_limit_retry(self):
        """Test that rate-limited requests are retried."""
        # Simulate GET first returning 429, then contacts page, then empty
        get_seq = [
            DummyResp(429, text="Rate limit"),
            DummyResp(200, data={"contacts": [{"id": "1", "email": "user@example.com"}]}),
            DummyResp(200, data={"contacts": []}),
        ]
        idx = {"i": 0}

        def fake_get(*args, **kwargs):
            resp = get_seq[idx["i"]]
            idx["i"] += 1
            return resp

        # Simulate POST to import endpoint failing twice then succeeding
        post_seq = [
            DummyResp(429, text="Rate limit"),
            DummyResp(429, text="Rate limit"),
            DummyResp(200, data={}),
        ]
        idx2 = {"i": 0}

        def fake_post(*args, **kwargs):
            resp = post_seq[idx2["i"]]
            idx2["i"] += 1
            return resp

        # Patch the BREVO_SESSION and time.sleep
        with patch.object(brevo.BREVO_SESSION, "get", side_effect=fake_get):
            with patch.object(brevo.BREVO_SESSION, "post", side_effect=fake_post):
                with patch.object(brevo.time, "sleep"):  # Disable sleep
                    rv = self.client.post(
                        "/update_segment_attribute",
                        headers={"Authorization": "Bearer testtoken"},
                        json={
                            "brevo_api_key": "key",
                            "segment_id": 123,
                            "attribute_name": "FOO",
                            "attribute_value": "BAR",
                        },
                    )

        self.assertEqual(rv.status_code, 200)
        data = rv.json()
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["updated"], 1)
        self.assertEqual(data["failures"], [])


if __name__ == "__main__":
    unittest.main()
