"""Integration tests using de-identified real portal XML.

These tests exercise the full pipeline — XML → parse_espi_xml →
AlectraCoordinator._async_update_data → HA sensor states — without
bypassing any production code.  The key distinction from test_sensor.py
is that _async_update_data is NOT patched here.
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.components.sensor import SensorStateClass
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.alectra_utilities.const import DOMAIN
from custom_components.alectra_utilities.coordinator import AlectraCoordinator
from custom_components.alectra_utilities.parser import UsageData, parse_espi_xml

REAL_FIXTURE = Path(__file__).parent / "fixtures" / "real_espi.xml"

pytestmark = pytest.mark.skipif(
    not REAL_FIXTURE.exists(),
    reason="Real fixture absent — run sidecar to capture real_espi.xml first",
)

VALID_ENTRY_DATA = {
    "sidecar_url": "http://localhost:8099",
    "account_name": "Test",
    "account_number": "123",
    "phone_number": "4160000000",
}


@pytest.fixture(autouse=True)
def _enable(enable_custom_integrations):
    yield


@pytest.fixture(scope="module")
def real_xml():
    """Load the de-identified portal XML (module-scoped; just a string)."""
    return REAL_FIXTURE.read_text()


# -- Test 1: Parser structural validity --


def test_real_xml_parses_without_error(real_xml):
    data = parse_espi_xml(real_xml)
    assert isinstance(data, UsageData)
    assert len(data.readings) > 0


# -- Test 2: Reading value sanity --


def test_real_xml_reading_values_are_plausible(real_xml):
    data = parse_espi_xml(real_xml)
    for r in data.delivered_intervals:
        assert r.kwh >= 0
        assert r.duration_seconds == 3600
        assert r.start.tzinfo is not None
    for r in data.register_reads:
        assert r.kwh >= 0
        assert r.duration_seconds == 0
    # readings span a non-trivial window (at least 1 day)
    span = data.readings[-1].start - data.readings[0].start
    assert span.total_seconds() >= 86400


# -- Test 3: Coordinator parses real XML end-to-end --


async def test_coordinator_with_real_xml(hass: HomeAssistant, real_xml):
    mock_client = MagicMock()
    mock_client.fetch_usage_data = AsyncMock(return_value=real_xml)
    entry = MockConfigEntry(domain=DOMAIN, data=VALID_ENTRY_DATA)
    entry.add_to_hass(hass)
    coord = AlectraCoordinator(hass, mock_client, update_interval_hours=24, config_entry=entry)
    await coord.async_refresh()
    assert coord.last_update_success
    assert isinstance(coord.data, UsageData)
    assert coord.data.total_kwh > 0


# -- Test 4: Full HA sensor pipeline with real XML --


async def test_sensor_states_with_real_xml(hass: HomeAssistant, real_xml):
    mock_client = MagicMock()
    mock_client.fetch_usage_data = AsyncMock(return_value=real_xml)

    entry = MockConfigEntry(domain=DOMAIN, data=VALID_ENTRY_DATA)
    entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.alectra_utilities.AlectraPortalClient",
            return_value=mock_client,
        ),
        patch("custom_components.alectra_utilities.async_get_clientsession"),
        # _async_update_data is NOT patched — full parse path runs
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    # Energy sensor: should show the latest cumulative register read
    energy = hass.states.get("sensor.alectra_utilities_energy")
    assert energy is not None
    energy_val = float(energy.state)
    assert energy_val > 100_000  # cumulative register read ~105,047+ kWh
    assert energy.attributes["unit_of_measurement"] == UnitOfEnergy.KILO_WATT_HOUR
    assert energy.attributes["state_class"] == SensorStateClass.TOTAL_INCREASING

    # Latest interval sensor: should be a small hourly value, not a register read
    latest = hass.states.get("sensor.alectra_utilities_latest_interval")
    assert latest is not None
    latest_val = float(latest.state)
    assert latest_val < 10  # a single hour's usage, not 105K+
    assert latest.attributes["state_class"] == SensorStateClass.MEASUREMENT

    # Daily usage sensor (may be 0.0 if no readings fall on yesterday)
    daily = hass.states.get("sensor.alectra_utilities_daily_usage")
    assert daily is not None
    assert daily.attributes["state_class"] == SensorStateClass.MEASUREMENT

    # Daily cost sensor (present because the real data includes cost)
    cost = hass.states.get("sensor.alectra_utilities_daily_cost")
    assert cost is not None
    assert "state_class" not in cost.attributes

    # data_last_updated extra attribute is populated
    assert energy.attributes.get("data_last_updated") is not None
