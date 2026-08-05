from __future__ import annotations

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util.percentage import (
    ordered_list_item_to_percentage,
    percentage_to_ordered_list_item,
)

from .const import DOMAIN, WIND_RATE_LABELS
from .entity_helpers import (
    build_thermostat_device_info,
    get_thermostat,
    system_is_heating,
    thermostat_common_attributes,
    thermostat_object_id,
)

AUTO_PRESET = "auto"
MANUAL_SPEEDS = ["low", "medium", "high", "turbo"]
SPEED_TO_RATE = {"low": 1, "medium": 2, "high": 3, "turbo": 4}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    thermostats = coordinator.data.get("thermostats", [])
    async_add_entities(
        AOSmithThermostatFanEntity(
            coordinator,
            hass.data[DOMAIN][entry.entry_id]["api"],
            item,
        )
        for item in thermostats
    )


class AOSmithThermostatFanEntity(CoordinatorEntity, FanEntity):
    _attr_has_entity_name = True
    _attr_speed_count = len(MANUAL_SPEEDS)
    _attr_preset_modes = [AUTO_PRESET]
    _attr_supported_features = FanEntityFeature.SET_SPEED | FanEntityFeature.PRESET_MODE
    if hasattr(FanEntityFeature, "TURN_ON"):
        _attr_supported_features |= FanEntityFeature.TURN_ON
    if hasattr(FanEntityFeature, "TURN_OFF"):
        _attr_supported_features |= FanEntityFeature.TURN_OFF

    def __init__(self, coordinator, api, thermostat: dict) -> None:
        super().__init__(coordinator)
        self.api = api
        self.device_id = thermostat["deviceId"]
        self._attr_unique_id = f"{self.device_id}_fan"
        self._attr_name = "Fan"

    @property
    def thermostat(self) -> dict:
        return get_thermostat(self.coordinator.data, self.device_id)

    @property
    def available(self) -> bool:
        return bool(self.thermostat)

    @property
    def device_info(self):
        return build_thermostat_device_info(self.thermostat, self.device_id)

    @property
    def suggested_object_id(self) -> str | None:
        return thermostat_object_id(self.thermostat, self.device_id, "fan")

    @property
    def is_on(self) -> bool | None:
        return self.thermostat.get("powerStatus") == 1

    @property
    def preset_mode(self) -> str | None:
        if self.thermostat.get("windModelStatus") == 0 and self.is_on:
            return AUTO_PRESET
        return None

    @property
    def percentage(self) -> int | None:
        rate = self.thermostat.get("windModelStatus")
        if not self.is_on:
            return 0
        if rate in (1, 2, 3, 4):
            speed_name = MANUAL_SPEEDS[rate - 1]
            return ordered_list_item_to_percentage(MANUAL_SPEEDS, speed_name)
        return None

    @property
    def extra_state_attributes(self) -> dict:
        attrs = thermostat_common_attributes(self.thermostat)
        attrs["wind_model_status"] = self.thermostat.get("windModelStatus")
        attrs["wind_label"] = WIND_RATE_LABELS.get(self.thermostat.get("windModelStatus"))
        return attrs

    async def async_turn_on(
        self,
        percentage: int | None = None,
        preset_mode: str | None = None,
        **kwargs,
    ) -> None:
        if not self.is_on and system_is_heating(self.coordinator.data):
            return
        await self.api.async_set_thermostat_power(self.device_id, True)
        if preset_mode:
            await self.async_set_preset_mode(preset_mode)
            return
        if percentage and percentage > 0:
            await self.async_set_percentage(percentage)
            return
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs) -> None:
        await self.api.async_set_thermostat_power(self.device_id, False)
        await self.coordinator.async_request_refresh()

    async def async_set_percentage(self, percentage: int) -> None:
        if percentage <= 0:
            await self.async_turn_off()
            return
        speed_name = percentage_to_ordered_list_item(MANUAL_SPEEDS, percentage)
        if not self.is_on and system_is_heating(self.coordinator.data):
            await self.api.async_set_thermostat_wind_rate(
                self.device_id, SPEED_TO_RATE[speed_name]
            )
            await self.coordinator.async_request_refresh()
            return
        await self.api.async_set_thermostat_power(self.device_id, True)
        await self.api.async_set_thermostat_wind_rate(self.device_id, SPEED_TO_RATE[speed_name])
        await self.coordinator.async_request_refresh()

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        if preset_mode != AUTO_PRESET:
            return
        if not self.is_on and system_is_heating(self.coordinator.data):
            await self.api.async_set_thermostat_wind_rate(self.device_id, 0)
            await self.coordinator.async_request_refresh()
            return
        await self.api.async_set_thermostat_power(self.device_id, True)
        await self.api.async_set_thermostat_wind_rate(self.device_id, 0)
        await self.coordinator.async_request_refresh()
