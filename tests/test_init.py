from unittest.mock import AsyncMock, patch
from datetime import datetime, timezone
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from homeassistant.core import HomeAssistant

from custom_components.alectra_utilities.const import DOMAIN
from custom_components.alectra_utilities.parser import UsageData, IntervalReading

MOCK_DATA = UsageData(
    readings=[
        IntervalReading(
            start=datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc),
            duration_seconds=3600,
            kwh=0.5,
            cost_cad=0.075,
            flow_direction=1,
        ),
        IntervalReading(
            start=datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc),
            duration_seconds=0,
            kwh=50.0,
            cost_cad=None,
            flow_direction=1,
        ),
    ]
)

VALID_DATA = {
    "sidecar_url": "http://localhost:8099",
    "account_name": "Test",
    "account_number": "123",
    "phone_number": "4160000000",
}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture
async def loaded_entry(hass: HomeAssistant):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=VALID_DATA,
        options={},
    )
    entry.add_to_hass(hass)

    with (
        patch("custom_components.alectra_utilities.AlectraPortalClient"),
        patch("custom_components.alectra_utilities.async_get_clientsession"),
        patch(
            "custom_components.alectra_utilities.AlectraCoordinator._async_update_data",
            return_value=MOCK_DATA,
        ),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    return entry


async def test_setup_registers_refresh_service(hass: HomeAssistant, loaded_entry):
    assert hass.services.has_service(DOMAIN, "refresh")


async def test_refresh_service_triggers_coordinator(hass: HomeAssistant, loaded_entry):
    coordinator = hass.data[DOMAIN][loaded_entry.entry_id]
    with patch.object(coordinator, "async_refresh", new_callable=AsyncMock) as mock_refresh:
        await hass.services.async_call(DOMAIN, "refresh", blocking=True)
        mock_refresh.assert_called_once()


async def test_first_install_triggers_initial_fetch(hass: HomeAssistant):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=VALID_DATA,
        options={},
    )
    entry.add_to_hass(hass)

    with (
        patch("custom_components.alectra_utilities.AlectraPortalClient"),
        patch("custom_components.alectra_utilities.async_get_clientsession"),
        patch(
            "custom_components.alectra_utilities.AlectraCoordinator._async_update_data",
            return_value=MOCK_DATA,
        ) as mock_update,
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    # First install: _async_update_data should have been called
    mock_update.assert_called()


async def test_unload_entry(hass: HomeAssistant, loaded_entry):
    assert await hass.config_entries.async_unload(loaded_entry.entry_id)
    assert loaded_entry.entry_id not in hass.data.get(DOMAIN, {})
    assert not hass.services.has_service(DOMAIN, "refresh")


async def _setup_entry(hass: HomeAssistant, acct: str = "123") -> MockConfigEntry:
    """Helper: create, add, and set up a single config entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={**VALID_DATA, "account_number": acct},
        options={},
    )
    entry.add_to_hass(hass)
    with (
        patch("custom_components.alectra_utilities.AlectraPortalClient"),
        patch("custom_components.alectra_utilities.async_get_clientsession"),
        patch(
            "custom_components.alectra_utilities.AlectraCoordinator._async_update_data",
            return_value=MOCK_DATA,
        ),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


async def test_unload_keeps_service_when_other_entries_remain(hass: HomeAssistant):
    """Service stays registered when unloading one of multiple entries."""
    entry1 = await _setup_entry(hass, "111")
    entry2 = await _setup_entry(hass, "222")

    # Unload first entry — service should remain
    assert await hass.config_entries.async_unload(entry1.entry_id)
    assert hass.services.has_service(DOMAIN, "refresh")

    # Unload second entry — now service should be removed
    assert await hass.config_entries.async_unload(entry2.entry_id)
    assert not hass.services.has_service(DOMAIN, "refresh")


async def test_refresh_service_calls_all_coordinators(hass: HomeAssistant):
    """Refresh service iterates over all loaded coordinators."""
    entry1 = await _setup_entry(hass, "AAA")
    entry2 = await _setup_entry(hass, "BBB")

    coordinators = [hass.data[DOMAIN][e.entry_id] for e in (entry1, entry2)]
    mocks = []
    for coord in coordinators:
        m = AsyncMock()
        coord.async_refresh = m
        mocks.append(m)

    await hass.services.async_call(DOMAIN, "refresh", blocking=True)
    for m in mocks:
        m.assert_called_once()
