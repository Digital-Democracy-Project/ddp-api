"""The public Swagger page must tell people how to authenticate (INFRA-7)."""
from fastapi.testclient import TestClient

from app.main import app


def test_docs_page_persists_authorization():
    html = TestClient(app).get("/docs").text
    assert '"persistAuthorization": true' in html


def test_public_description_mentions_authorize():
    from app.main import PUBLIC_API_DESCRIPTION

    assert "Authorize" in PUBLIC_API_DESCRIPTION
    assert app.description == PUBLIC_API_DESCRIPTION
