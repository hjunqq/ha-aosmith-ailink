from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CENTER_HEATING_TO_THERMOSTAT_MODE,
    DOMAIN,
    HEATING_LABEL_TO_MODE,
    HEATING_MODE_LABELS,
    THERMOSTAT_LABEL_TO_MODE,
    THERMOSTAT_MODE_LABELS,
)
from .entity_helpers import (
    async_set_whole_home_mode,
    async_set_whole_home_heating_strategy,
    build_center_device_info,
    build_thermostat_device_info,
    center_object_id,
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
    entities: list[SelectEntity] = []

    center = coordinator.data.get("centercontroller")
    if center:
        entities.append(AOSmithHeatingModeSelect(coordinator, api, center))

    for thermostat in coordinator.data.get("thermostats", []):
        entities.append(AOSmithThermostatModeSelect(coordinator, api, thermostat))

    async_add_entities(entities)


class AOSmithHeatingModeSelect(CoordinatorEntity, SelectEntity):
    _attr_has_entity_name = True
    _attr_options = list(HEATING_LABEL_TO_MODE.keys())

    def __init__(self, coordinator, api, center: dict) -> None:
        super().__init__(coordinator)
        self.api = api
        self.device_id = center["deviceId"]
        self._attr_unique_id = f"{self.device_id}_heating_mode"
        self._attr_name = "Heating Mode"

    @property
    def center(self) -> dict:
        return self.coordinator.data.get("centercontroller") or {}

    @property
    def available(self) -> bool:
        return bool(self.center)

    @property
    def current_option(self) -> str | None:
        mode = self.center.get("HeatingMode")
        return HEATING_MODE_LABELS.get(mode)

    @property
    def device_info(self) -> DeviceInfo:
        return build_center_device_info(self.center)

    @property
    def suggested_object_id(self) -> str | None:
        return center_object_id("heating_mode")

    async def async_select_option(self, option: str) -> None:
        center_mode = HEATING_LABEL_TO_MODE[option]
        await async_set_whole_home_heating_strategy(
            self.coordinator,
            self.api,
            center_mode,
            CENTER_HEATING_TO_THERMOSTAT_MODE[center_mode],
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
