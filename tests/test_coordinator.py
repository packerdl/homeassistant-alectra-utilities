from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock
import pytest
from pathlib import Path

from homeassistant.helpers.update_coordinator import UpdateFailed
from homeassistant.exceptions import ConfigEntryAuthFailed
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.alectra_utilities.coordinator import AlectraCoordinator
from custom_components.alectra_utilities.client import AlectraAuthError, AlectraConnectionError
from custom_components.alectra_utilities.const import DOMAIN

FIXTURE_XML = (Path(__file__).parent / "fixtures" / "sample_espi.xml").read_text()


@pytest.fixture
def mock_client():
    client = MagicMock()
    client.fetch_usage_data = AsyncMock(return_value=FIXTURE_XML)
    return client


@pytest.fixture
def mock_entry(hass):
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
def coordinator(hass, mock_client, mock_entry):
    return AlectraCoordinator(hass, mock_client, update_interval_hours=24, config_entry=mock_entry)


async def test_coordinator_fetches_and_parses_data(coordinator):
    await coordinator.async_refresh()
    assert coordinator.data is not None
    assert coordinator.data.total_kwh > 0


async def test_coordinator_data_has_readings(coordinator):
    await coordinator.async_refresh()
    assert len(coordinator.data.readings) == 3  # 2 hourly + 1 register


async def test_auth_error_raises_config_entry_auth_failed(hass, mock_client, mock_entry):
    mock_client.fetch_usage_data = AsyncMock(side_effect=AlectraAuthError("bad creds"))
    coord = AlectraCoordinator(hass, mock_client, update_interval_hours=24, config_entry=mock_entry)
    with pytest.raises(ConfigEntryAuthFailed):
        await coord._async_update_data()


async def test_connection_error_raises_update_failed(hass, mock_client, mock_entry):
    mock_client.fetch_usage_data = AsyncMock(side_effect=AlectraConnectionError("timeout"))
    coord = AlectraCoordinator(hass, mock_client, update_interval_hours=24, config_entry=mock_entry)
    with pytest.raises(UpdateFailed):
        await coord._async_update_data()


async def test_update_interval_is_set(coordinator):
    assert coordinator.update_interval == timedelta(hours=24)
