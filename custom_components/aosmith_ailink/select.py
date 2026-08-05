from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    THERMOSTAT_LABEL_TO_MODE,
    THERMOSTAT_MODE_LABELS,
)
from .entity_helpers import (
    async_set_whole_home_mode,
    build_thermostat_device_info,
    get_thermostat,
    thermostat_object_id,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    api = hass.data[DOMAIN][entry.entry_id]["api"]
    async_add_entities(
        AOSmithThermostatModeSelect(coordinator, api, thermostat)
        for thermostat in coordinator.data.get("thermostats", [])
    )


class AOSmithThermostatModeSelect(CoordinatorEntity, SelectEntity):
    _attr_has_entity_name = True
    _attr_options = list(THERMOSTAT_LABEL_TO_MODE.keys())

    def __init__(self, coordinator, api, thermostat: dict) -> None:
        super().__init__(coordinator)
        self.api = api
        self.device_id = thermostat["deviceId"]
        self._attr_unique_id = f"{self.device_id}_mode"
        self._attr_name = "Mode"

    @property
    def thermostat(self) -> dict:
        return get_thermostat(self.coordinator.data, self.device_id)

    @property
    def available(self) -> bool:
        return bool(self.thermostat)

    @property
    def current_option(self) -> str | None:
        return THERMOSTAT_MODE_LABELS.get(self.thermostat.get("workModelStatus"))

    @property
    def device_info(self) -> DeviceInfo:
        return build_thermostat_device_info(self.thermostat, self.device_id)

    @property
    def suggested_object_id(self) -> str | None:
        return thermostat_object_id(self.thermostat, self.device_id, "mode")

    async def async_select_option(self, option: str) -> None:
        await async_set_whole_home_mode(
            self.coordinator,
            self.api,
            THERMOSTAT_LABEL_TO_MODE[option],
            power_device_id=self.device_id,
        )
