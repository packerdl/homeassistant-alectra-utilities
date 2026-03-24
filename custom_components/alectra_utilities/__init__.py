from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .client import AlectraPortalClient
from .const import (
    CONF_ACCOUNT_NAME,
    CONF_ACCOUNT_NUMBER,
    CONF_PHONE_NUMBER,
    CONF_SIDECAR_TOKEN,
    CONF_SIDECAR_URL,
    CONF_UPDATE_INTERVAL_HOURS,
    DEFAULT_UPDATE_INTERVAL_HOURS,
    DOMAIN,
)
from .coordinator import AlectraCoordinator

PLATFORMS = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    client = AlectraPortalClient(
        sidecar_url=entry.data[CONF_SIDECAR_URL],
        account_name=entry.data[CONF_ACCOUNT_NAME],
        account_number=entry.data[CONF_ACCOUNT_NUMBER],
        phone_number=entry.data[CONF_PHONE_NUMBER],
        session=async_get_clientsession(hass),
        sidecar_token=entry.data.get(CONF_SIDECAR_TOKEN, ""),
    )
    update_interval_hours = entry.options.get(
        CONF_UPDATE_INTERVAL_HOURS, DEFAULT_UPDATE_INTERVAL_HOURS
    )
    coordinator = AlectraCoordinator(hass, client, update_interval_hours, config_entry=entry)

    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    if not hass.services.has_service(DOMAIN, "refresh"):

        async def handle_refresh(call: ServiceCall) -> None:
            errors = []
            for coord in hass.data.get(DOMAIN, {}).values():
                await coord.async_refresh()
                if not coord.last_update_success:
                    errors.append(type(coord.last_exception).__name__)
            if errors:
                raise HomeAssistantError(
                    f"Refresh failed ({', '.join(errors)}) — check logs for details"
                )

        hass.services.async_register(DOMAIN, "refresh", handle_refresh)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
        if not hass.data.get(DOMAIN):
            hass.services.async_remove(DOMAIN, "refresh")
    return unload_ok
