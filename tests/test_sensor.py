from unittest.mock import AsyncMock, patch
from datetime import datetime, timezone
from pathlib import Path
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.components.sensor import SensorStateClass
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant

from custom_components.alectra_utilities.const import DOMAIN
from custom_components.alectra_utilities.parser import UsageData, IntervalReading

FIXTURE_XML = (Path(__file__).parent / "fixtures" / "sample_espi.xml").read_text()

MOCK_READINGS = [
    IntervalReading(
        start=datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc),
        duration_seconds=3600,
        kwh=0.5,
        cost_cad=0.075,
        flow_direction=1,
    ),
    IntervalReading(
        start=datetime(2025, 1, 1, 1, 0, tzinfo=timezone.utc),
        duration_seconds=3600,
        kwh=0.75,
        cost_cad=0.1125,
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
MOCK_DATA = UsageData(readings=MOCK_READINGS)

VALID_ENTRY_DATA = {
    "sidecar_url": "http://localhost:8099",
    "account_name": "Test",
    "account_number": "123",
    "phone_number": "4160000000",
}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture
async def setup_integration(hass: HomeAssistant):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=VALID_ENTRY_DATA,
        options={},
    )
    entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.alectra_utilities.AlectraPortalClient",
        ),
        patch("custom_components.alectra_utilities.async_get_clientsession"),
        patch(
            "custom_components.alectra_utilities.AlectraCoordinator._async_update_data",
            return_value=MOCK_DATA,
        ),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    return entry


async def test_energy_sensor_state(hass: HomeAssistant, setup_integration):
    state = hass.states.get("sensor.alectra_utilities_energy")
    assert state is not None
    assert float(state.state) == pytest.approx(50.0)


async def test_energy_sensor_unit(hass: HomeAssistant, setup_integration):
    state = hass.states.get("sensor.alectra_utilities_energy")
    assert state.attributes["unit_of_measurement"] == UnitOfEnergy.KILO_WATT_HOUR


async def test_energy_sensor_state_class(hass: HomeAssistant, setup_integration):
    state = hass.states.get("sensor.alectra_utilities_energy")
    assert state.attributes["state_class"] == SensorStateClass.TOTAL_INCREASING


async def test_daily_usage_sensor_exists(hass: HomeAssistant, setup_integration):
    state = hass.states.get("sensor.alectra_utilities_daily_usage")
    assert state is not None


async def test_latest_interval_sensor_state(hass: HomeAssistant, setup_integration):
    state = hass.states.get("sensor.alectra_utilities_latest_interval")
    assert state is not None
    assert float(state.state) == pytest.approx(0.75)


async def test_daily_cost_sensor_present(hass: HomeAssistant, setup_integration):
    state = hass.states.get("sensor.alectra_utilities_daily_cost")
    assert state is not None


async def test_energy_sensor_fallback_without_register():
    """When no register reads are present, energy sensor returns None (unavailable)."""
    from custom_components.alectra_utilities.sensor import SENSOR_DESCRIPTIONS

    readings = [
        IntervalReading(
            start=datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc),
            duration_seconds=3600,
            kwh=0.5,
            cost_cad=None,
            flow_direction=1,
        ),
    ]
    data = UsageData(readings=readings)
    assert data.latest_register_kwh is None
    energy_desc = next(d for d in SENSOR_DESCRIPTIONS if d.key == "energy")
    assert energy_desc.value_fn(data) is None


async def test_daily_usage_sensor_returns_none_when_no_yesterday_data():
    """When no intervals match yesterday's date, daily_usage returns None."""
    from custom_components.alectra_utilities.sensor import _daily_usage_kwh, SENSOR_DESCRIPTIONS

    readings = [
        IntervalReading(
            start=datetime(2020, 6, 15, 12, 0, tzinfo=timezone.utc),
            duration_seconds=3600,
            kwh=1.0,
            cost_cad=None,
            flow_direction=1,
        ),
    ]
    data = UsageData(readings=readings)
    assert _daily_usage_kwh(data) is None
    daily_desc = next(d for d in SENSOR_DESCRIPTIONS if d.key == "daily_usage")
    assert daily_desc.value_fn(data) is None


async def test_sensor_has_device_info(hass: HomeAssistant, setup_integration):
    """All sensors should be grouped under a single Alectra Utilities device."""
    from homeassistant.helpers import device_registry as dr

    entry = setup_integration
    device_registry = dr.async_get(hass)

    device = device_registry.async_get_device(
        identifiers={(DOMAIN, entry.entry_id)}
    )
    assert device is not None
    assert device.name == "Alectra Utilities"
    assert device.manufacturer == "Alectra Utilities"
