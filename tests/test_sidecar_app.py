"""Unit tests for the sidecar FastAPI app."""
from __future__ import annotations

import os
import sys
from unittest.mock import AsyncMock, patch

from httpx import ASGITransport, AsyncClient
import pytest

# The sidecar app lives outside the HA custom_components package tree.
# We add its directory to sys.path so we can import it directly.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "alectra_scraper"))

from app import app  # noqa: E402
from scraper import AlectraAuthError, AlectraConnectionError  # noqa: E402

FETCH_URL = "/fetch"
VALID_PAYLOAD = {
    "account_name": "Test User",
    "account_number": "123456",
    "phone_number": "4165551234",
    "start_date": "2025-01-01",
    "end_date": "2025-01-02",
}


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_successful_fetch(client: AsyncClient):
    mock_xml = "<feed>test</feed>"
    with patch("app.AlectraScraper") as MockScraper:
        instance = MockScraper.return_value
        instance.fetch_usage_data = AsyncMock(return_value=mock_xml)
        resp = await client.post(FETCH_URL, json=VALID_PAYLOAD)

    assert resp.status_code == 200
    assert resp.json() == {"xml": mock_xml}


async def test_auth_error_returns_401(client: AsyncClient):
    with patch("app.AlectraScraper") as MockScraper:
        instance = MockScraper.return_value
        instance.fetch_usage_data = AsyncMock(
            side_effect=AlectraAuthError("bad creds")
        )
        resp = await client.post(FETCH_URL, json=VALID_PAYLOAD)

    assert resp.status_code == 401
    assert resp.json()["detail"]["error"] == "auth_error"


async def test_connection_error_returns_502(client: AsyncClient):
    with patch("app.AlectraScraper") as MockScraper:
        instance = MockScraper.return_value
        instance.fetch_usage_data = AsyncMock(
            side_effect=AlectraConnectionError("timeout")
        )
        resp = await client.post(FETCH_URL, json=VALID_PAYLOAD)

    assert resp.status_code == 502
    assert resp.json()["detail"]["error"] == "connection_error"


async def test_unexpected_error_returns_500(client: AsyncClient):
    with patch("app.AlectraScraper") as MockScraper:
        instance = MockScraper.return_value
        instance.fetch_usage_data = AsyncMock(
            side_effect=RuntimeError("boom")
        )
        resp = await client.post(FETCH_URL, json=VALID_PAYLOAD)

    assert resp.status_code == 500
    assert resp.json()["detail"]["error"] == "internal_error"


async def test_token_rejection(client: AsyncClient, monkeypatch):
    monkeypatch.setattr("app._SIDECAR_TOKEN", "correct-token")
    resp = await client.post(
        FETCH_URL,
        json=VALID_PAYLOAD,
        headers={"x-sidecar-token": "wrong-token"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid sidecar token"


async def test_token_accepted(client: AsyncClient, monkeypatch):
    monkeypatch.setattr("app._SIDECAR_TOKEN", "correct-token")
    with patch("app.AlectraScraper") as MockScraper:
        instance = MockScraper.return_value
        instance.fetch_usage_data = AsyncMock(return_value="<feed/>")
        resp = await client.post(
            FETCH_URL,
            json=VALID_PAYLOAD,
            headers={"x-sidecar-token": "correct-token"},
        )
    assert resp.status_code == 200


async def test_no_token_required_when_not_configured(client: AsyncClient, monkeypatch):
    monkeypatch.setattr("app._SIDECAR_TOKEN", "")
    with patch("app.AlectraScraper") as MockScraper:
        instance = MockScraper.return_value
        instance.fetch_usage_data = AsyncMock(return_value="<feed/>")
        resp = await client.post(FETCH_URL, json=VALID_PAYLOAD)
    assert resp.status_code == 200
