"""Config flow for Alectra Utilities integration."""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

import voluptuous as vol
from yarl import URL
from homeassistant.helpers.selector import TextSelector, TextSelectorConfig, TextSelectorType

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .client import AlectraAuthError, AlectraConnectionError, AlectraPortalClient
from .const import (
    CONF_ACCOUNT_NAME,
    CONF_ACCOUNT_NUMBER,
    CONF_PHONE_NUMBER,
    CONF_SIDECAR_TOKEN,
    CONF_SIDECAR_URL,
    DEFAULT_SIDECAR_URL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


def _validate_sidecar_url(value: str) -> str:
    """Reject non-http/https URLs to prevent SSRF via the config UI."""
    try:
        parsed = URL(value)
    except Exception as err:
        raise vol.Invalid("Invalid sidecar URL") from err
    if parsed.scheme not in ("http", "https"):
        raise vol.Invalid("Sidecar URL must use http or https scheme")
    return value


STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_SIDECAR_URL, default=DEFAULT_SIDECAR_URL): vol.All(
            str, _validate_sidecar_url
        ),
        vol.Required(CONF_ACCOUNT_NAME): str,
        vol.Required(CONF_ACCOUNT_NUMBER): str,
        vol.Required(CONF_PHONE_NUMBER): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        ),
        vol.Optional(CONF_SIDECAR_TOKEN, default=""): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        ),
    }
)


class AlectraConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Alectra Utilities."""

    VERSION = 1

    @staticmethod
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        from .options_flow import AlectraOptionsFlow

        return AlectraOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            errors = await self._validate_credentials(user_input)
            if not errors:
                await self.async_set_unique_id(user_input[CONF_ACCOUNT_NUMBER])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=user_input[CONF_ACCOUNT_NAME], data=user_input
                )

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors
        )

    async def _validate_credentials(
        self, user_input: dict[str, Any]
    ) -> dict[str, str]:
        """Validate credentials by attempting a live login."""
        client = AlectraPortalClient(
            sidecar_url=user_input[CONF_SIDECAR_URL],
            account_name=user_input[CONF_ACCOUNT_NAME],
            account_number=user_input[CONF_ACCOUNT_NUMBER],
            phone_number=user_input[CONF_PHONE_NUMBER],
            session=async_get_clientsession(self.hass),
            sidecar_token=user_input.get(CONF_SIDECAR_TOKEN, ""),
        )
        end = date.today()
        start = end - timedelta(days=1)
        try:
            await client.fetch_usage_data(start, end)
        except AlectraAuthError as err:
            _LOGGER.warning("Credential validation failed: %s", err)
            return {"base": "invalid_auth"}
        except AlectraConnectionError as err:
            _LOGGER.error("Cannot reach sidecar during validation: %s", err)
            return {"base": "cannot_connect"}
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Unexpected error during credential validation")
            return {"base": "unknown"}
        return {}
