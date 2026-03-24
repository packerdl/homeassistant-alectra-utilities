from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo
from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import AlectraCoordinator
from .parser import UsageData

_EASTERN = ZoneInfo("America/Toronto")


@dataclass(frozen=True, kw_only=True)
class AlectraSensorEntityDescription(SensorEntityDescription):
    value_fn: Callable[[UsageData], float | None]
    present_fn: Callable[[UsageData], bool] = lambda _: True


def _daily_usage_kwh(data: UsageData) -> float | None:
    yesterday = datetime.now(_EASTERN).date() - timedelta(days=1)
    daily = [
        r.kwh for r in data.delivered_intervals
        if r.start.astimezone(_EASTERN).date() == yesterday
    ]
    return sum(daily) if daily else None


def _daily_cost_cad(data: UsageData) -> float | None:
    yesterday = datetime.now(_EASTERN).date() - timedelta(days=1)
    daily = [
        r for r in data.delivered_intervals
        if r.start.astimezone(_EASTERN).date() == yesterday
        and r.cost_cad is not None
    ]
    if not daily:
        return None
    return sum(r.cost_cad for r in daily)


def _has_cost_data(data: UsageData) -> bool:
    return any(r.cost_cad is not None for r in data.delivered_intervals)


SENSOR_DESCRIPTIONS: tuple[AlectraSensorEntityDescription, ...] = (
    AlectraSensorEntityDescription(
        key="energy",
        name="Energy",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        # Register reads (duration=0) are expected in Alectra portal ESPI data.
        # Returns None if no register reads exist, which is valid for TOTAL_INCREASING.
        value_fn=lambda data: (
            round(data.latest_register_kwh, 4)
            if data.latest_register_kwh is not None
            else None
        ),
    ),
    AlectraSensorEntityDescription(
        key="daily_usage",
        name="Daily Usage",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: (
            round(v, 4) if (v := _daily_usage_kwh(data)) is not None else None
        ),
    ),
    AlectraSensorEntityDescription(
        key="latest_interval",
        name="Latest Interval",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: (
            round(data.latest_interval_kwh, 4)
            if data.latest_interval_kwh is not None
            else None
        ),
    ),
    AlectraSensorEntityDescription(
        key="daily_cost",
        name="Daily Cost",
        native_unit_of_measurement="CAD",
        device_class=SensorDeviceClass.MONETARY,
        icon="mdi:currency-cad",
        value_fn=lambda data: (
            round(v, 2) if (v := _daily_cost_cad(data)) is not None else None
        ),
        present_fn=_has_cost_data,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: AlectraCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        AlectraSensor(coordinator, description)
        for description in SENSOR_DESCRIPTIONS
        if coordinator.data is None or description.present_fn(coordinator.data)
    )


class AlectraSensor(CoordinatorEntity[AlectraCoordinator], SensorEntity):
    entity_description: AlectraSensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: AlectraCoordinator,
        description: AlectraSensorEntityDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{description.key}"
        if description.key == "daily_cost":
            self._attr_suggested_display_precision = 2

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.config_entry.entry_id)},
            name="Alectra Utilities",
            manufacturer="Alectra Utilities",
        )

    @property
    def native_value(self) -> float | None:
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        if self.coordinator.data is None:
            return {}
        ts = self.coordinator.data.data_timestamp
        return {"data_last_updated": ts.isoformat() if ts else None}
