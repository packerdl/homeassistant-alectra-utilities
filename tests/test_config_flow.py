from unittest.mock import AsyncMock, patch
import pytest
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType

from custom_components.alectra_utilities.const import DOMAIN
from custom_components.alectra_utilities.client import AlectraAuthError, AlectraConnectionError
from custom_components.alectra_utilities.config_flow import _validate_sidecar_url
from custom_components.alectra_utilities.parser import UsageData

VALID_INPUT = {
    "sidecar_url": "http://localhost:8099",
    "account_name": "Test Account",
    "account_number": "123456789",
    "phone_number": "4165550000",
}


@pytest.fixture(autouse=True)
def _enable_custom_integrations(enable_custom_integrations):
    """Enable loading of custom integrations in all tests in this module."""


async def test_form_shows_on_init(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"
    assert "sidecar_url" in result["data_schema"].schema
    assert "account_name" in result["data_schema"].schema
    assert "account_number" in result["data_schema"].schema
    assert "phone_number" in result["data_schema"].schema
    assert "sidecar_token" in result["data_schema"].schema


async def test_successful_setup_creates_entry(hass):
    with (
        patch(
            "custom_components.alectra_utilities.config_flow.AlectraPortalClient"
        ) as mock_client_cls,
        patch("custom_components.alectra_utilities.config_flow.async_get_clientsession"),
        patch("custom_components.alectra_utilities.AlectraPortalClient"),
        patch("custom_components.alectra_utilities.async_get_clientsession"),
        patch(
            "custom_components.alectra_utilities.AlectraCoordinator._async_update_data",
            return_value=UsageData(),
        ),
    ):
        mock_client = mock_client_cls.return_value
        mock_client.fetch_usage_data = AsyncMock(return_value="<feed/>")

        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], VALID_INPUT
        )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"] == {**VALID_INPUT, "sidecar_token": ""}


async def test_invalid_auth_shows_error(hass):
    with (
        patch(
            "custom_components.alectra_utilities.config_flow.AlectraPortalClient"
        ) as mock_client_cls,
        patch("custom_components.alectra_utilities.config_flow.async_get_clientsession"),
    ):
        mock_client = mock_client_cls.return_value
        mock_client.fetch_usage_data = AsyncMock(side_effect=AlectraAuthError("bad"))

        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], VALID_INPUT
        )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_connection_error_shows_error(hass):
    with (
        patch(
            "custom_components.alectra_utilities.config_flow.AlectraPortalClient"
        ) as mock_client_cls,
        patch("custom_components.alectra_utilities.config_flow.async_get_clientsession"),
    ):
        mock_client = mock_client_cls.return_value
        mock_client.fetch_usage_data = AsyncMock(side_effect=AlectraConnectionError("down"))

        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], VALID_INPUT
        )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


def test_validate_sidecar_url_valid():
    assert _validate_sidecar_url("http://localhost:8099") == "http://localhost:8099"
    assert _validate_sidecar_url("https://example.com/sidecar") == "https://example.com/sidecar"


def test_validate_sidecar_url_invalid_scheme():
    with pytest.raises(vol.Invalid, match="http or https"):
        _validate_sidecar_url("ftp://localhost:8099")


def test_validate_sidecar_url_unparseable():
    with pytest.raises(vol.Invalid):
        _validate_sidecar_url("://not a url")


async def test_options_flow_shows_form(hass):
    from pytest_homeassistant_custom_component.common import MockConfigEntry
    from custom_components.alectra_utilities.options_flow import AlectraOptionsFlow

    entry = MockConfigEntry(domain=DOMAIN, data=VALID_INPUT, options={})
    entry.add_to_hass(hass)

    flow = AlectraOptionsFlow()
    flow.hass = hass
    flow.handler = entry.entry_id

    result = await flow.async_step_init(None)
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "init"
    assert "update_interval_hours" in result["data_schema"].schema


async def test_options_flow_creates_entry(hass):
    from pytest_homeassistant_custom_component.common import MockConfigEntry
    from custom_components.alectra_utilities.options_flow import AlectraOptionsFlow

    entry = MockConfigEntry(domain=DOMAIN, data=VALID_INPUT, options={})
    entry.add_to_hass(hass)

    flow = AlectraOptionsFlow()
    flow.hass = hass
    flow.handler = entry.entry_id

    result = await flow.async_step_init({"update_interval_hours": 12})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"] == {"update_interval_hours": 12}


async def test_already_configured_aborts(hass):
    from pytest_homeassistant_custom_component.common import MockConfigEntry
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=VALID_INPUT,
        unique_id=VALID_INPUT["account_number"],
    )
    entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.alectra_utilities.config_flow.AlectraPortalClient"
        ) as mock_client_cls,
        patch("custom_components.alectra_utilities.config_flow.async_get_clientsession"),
    ):
        mock_client = mock_client_cls.return_value
        mock_client.fetch_usage_data = AsyncMock(return_value="<feed/>")

        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], VALID_INPUT
        )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"
