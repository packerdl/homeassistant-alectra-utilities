"""Tests for the Alectra sidecar HTTP client."""

from datetime import date
from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest

from custom_components.alectra_utilities.client import (
    AlectraAuthError,
    AlectraConnectionError,
    AlectraPortalClient,
)

SIDECAR_URL = "http://localhost:8099"


def _mock_response(status=200, json_data=None, text=""):
    """Create a mock aiohttp response."""
    resp = AsyncMock()
    resp.status = status
    if json_data is not None:
        resp.json = AsyncMock(return_value=json_data)
    else:
        resp.json = AsyncMock(side_effect=aiohttp.ContentTypeError(
            MagicMock(), MagicMock()
        ))
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)
    return resp


def _mock_session(response=None, exception=None):
    """Create a mock aiohttp session."""
    session = MagicMock()
    if exception:
        session.post = MagicMock(side_effect=exception)
    else:
        session.post = MagicMock(return_value=response)
    return session


@pytest.fixture
def client():
    return AlectraPortalClient(SIDECAR_URL, "Test", "123", "4165550000")


async def test_successful_fetch(client):
    resp = _mock_response(status=200, json_data={"xml": "<feed/>"})
    client._session = _mock_session(response=resp)
    result = await client.fetch_usage_data(date(2025, 1, 1), date(2025, 1, 31))
    assert result == "<feed/>"


async def test_auth_error(client):
    resp = _mock_response(
        status=401,
        json_data={"detail": {"error": "auth_error", "message": "bad creds"}},
    )
    client._session = _mock_session(response=resp)
    with pytest.raises(AlectraAuthError):
        await client.fetch_usage_data(date(2025, 1, 1), date(2025, 1, 31))


async def test_connection_error_502(client):
    resp = _mock_response(
        status=502,
        json_data={"detail": {"error": "connection_error", "message": "timed out"}},
    )
    client._session = _mock_session(response=resp)
    with pytest.raises(AlectraConnectionError):
        await client.fetch_usage_data(date(2025, 1, 1), date(2025, 1, 31))


async def test_non_json_error_response(client):
    resp = _mock_response(status=502)  # json raises ContentTypeError
    client._session = _mock_session(response=resp)
    with pytest.raises(AlectraConnectionError, match="Sidecar returned 502"):
        await client.fetch_usage_data(date(2025, 1, 1), date(2025, 1, 31))


async def test_sidecar_unreachable(client):
    client._session = _mock_session(exception=aiohttp.ClientConnectionError())
    with pytest.raises(AlectraConnectionError, match="Cannot reach sidecar"):
        await client.fetch_usage_data(date(2025, 1, 1), date(2025, 1, 31))


async def test_sidecar_token_sent_in_header():
    client = AlectraPortalClient(SIDECAR_URL, "Test", "123", "4165550000", sidecar_token="secret")
    resp = _mock_response(status=200, json_data={"xml": "<feed/>"})
    session = _mock_session(response=resp)
    client._session = session
    await client.fetch_usage_data(date(2025, 1, 1), date(2025, 1, 31))
    _, kwargs = session.post.call_args
    assert kwargs.get("headers", {}).get("X-Sidecar-Token") == "secret"


async def test_no_token_omits_header():
    client = AlectraPortalClient(SIDECAR_URL, "Test", "123", "4165550000", sidecar_token="")
    resp = _mock_response(status=200, json_data={"xml": "<feed/>"})
    session = _mock_session(response=resp)
    client._session = session
    await client.fetch_usage_data(date(2025, 1, 1), date(2025, 1, 31))
    _, kwargs = session.post.call_args
    assert "X-Sidecar-Token" not in kwargs.get("headers", {})
