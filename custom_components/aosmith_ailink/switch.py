from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .entity_helpers import build_center_device_info


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    api = hass.data[DOMAIN][entry.entry_id]["api"]
    async_add_entities([AOSmithWholeHomePowerSwitch(coordinator, api)])


class AOSmithWholeHomePowerSwitch(CoordinatorEntity, SwitchEntity):
    """Fail-safe master switch whose only active operation is turn off."""

    _attr_has_entity_name = False
    _attr_name = "全屋温控总开关"
    _attr_unique_id = "aosmith_whole_home_power"

    def __init__(self, coordinator, api) -> None:
        super().__init__(coordinator)
        self.api = api

    @property
    def available(self) -> bool:
        return bool(self.coordinator.data.get("thermostats"))

    @property
    def is_on(self) -> bool:
        return any(
            thermostat.get("powerStatus") == 1
            for thermostat in self.coordinator.data.get("thermostats", [])
        )

    @property
    def suggested_object_id(self) -> str:
        return "ao_smith_whole_home_power"

    @property
    def device_info(self):
        center = self.coordinator.data.get("centercontroller") or {}
        return build_center_device_info(center) if center else None

    async def async_turn_on(self, **kwargs: Any) -> None:
        # A master start is intentionally unsupported: room and mode must be explicit.
        return

    async def async_turn_off(self, **kwargs: Any) -> None:
        for thermostat in self.coordinator.data.get("thermostats", []):
            await self.api.async_set_thermostat_power(thermostat["deviceId"], False)
        await self.coordinator.async_request_refresh()
