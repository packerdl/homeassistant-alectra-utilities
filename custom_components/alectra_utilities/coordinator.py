"""DataUpdateCoordinator for the Alectra Utilities integration.

Wraps the portal client and XML parser, manages the scheduled polling
interval, and maps client errors to Home Assistant-specific exceptions.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import AlectraAuthError, AlectraConnectionError, AlectraPortalClient
from .const import DOMAIN
from .parser import UsageData, parse_espi_xml

_LOGGER = logging.getLogger(__name__)

ROLLING_WINDOW_DAYS = 30


class AlectraCoordinator(DataUpdateCoordinator[UsageData]):
    """Coordinator that fetches Alectra usage data on a rolling 30-day window."""

    def __init__(
        self, hass: HomeAssistant, client: AlectraPortalClient,
        update_interval_hours: int, config_entry: ConfigEntry,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(hours=update_interval_hours),
            config_entry=config_entry,
        )
        self._client = client

    async def _async_update_data(self) -> UsageData:
        """Fetch usage data from the portal and parse the ESPI XML."""
        end_date = date.today()
        start_date = end_date - timedelta(days=ROLLING_WINDOW_DAYS)
        try:
            xml = await self._client.fetch_usage_data(start_date, end_date)
        except AlectraAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except AlectraConnectionError as err:
            raise UpdateFailed(str(err)) from err

        try:
            data = await self.hass.async_add_executor_job(parse_espi_xml, xml)
        except Exception as err:
            raise UpdateFailed(f"Failed to parse usage data: {err}") from err

        if not data.readings:
            _LOGGER.warning("Portal returned valid XML but it contained zero readings")

        return data
