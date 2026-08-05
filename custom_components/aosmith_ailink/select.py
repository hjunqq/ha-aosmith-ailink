from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    HEATING_LABEL_TO_MODE,
    HEATING_MODE_LABELS,
    SYSTEM_LABEL_TO_MODE,
    SYSTEM_MODE_LABELS,
)
from .entity_helpers import (
    async_set_system_mode,
    build_center_device_info,
    center_object_id,
    get_main_thermostat,
    system_is_heating,
    system_mode_code,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    api = hass.data[DOMAIN][entry.entry_id]["api"]
    entities: list[SelectEntity] = [AOSmithSystemModeSelect(coordinator, api)]
    if coordinator.data.get("centercontroller"):
        entities.append(AOSmithHeatingModeSelect(coordinator, api))
    async_add_entities(entities)


class AOSmithSystemModeSelect(CoordinatorEntity, SelectEntity):
    _attr_has_entity_name = False
    _attr_name = "全屋运行模式"
    _attr_unique_id = "aosmith_system_mode"
    _attr_options = list(SYSTEM_LABEL_TO_MODE.keys())

    def __init__(self, coordinator, api) -> None:
        super().__init__(coordinator)
        self.api = api

    @property
    def available(self) -> bool:
        return bool(get_main_thermostat(self.coordinator.data))

    @property
    def current_option(self) -> str | None:
        mode = system_mode_code(self.coordinator.data)
        return SYSTEM_MODE_LABELS.get(mode)

    @property
    def suggested_object_id(self) -> str:
        return "ao_smith_system_mode"

    async def async_select_option(self, option: str) -> None:
        await async_set_system_mode(
            self.coordinator,
            self.api,
            SYSTEM_LABEL_TO_MODE[option],
        )


class AOSmithHeatingModeSelect(CoordinatorEntity, SelectEntity):
    _attr_has_entity_name = True
    _attr_options = list(HEATING_LABEL_TO_MODE.keys())

    def __init__(self, coordinator, api) -> None:
        super().__init__(coordinator)
        self.api = api
        self._attr_unique_id = (
            f"{coordinator.data['centercontroller']['deviceId']}_heating_mode"
        )
        self._attr_name = "Heating Mode"

    @property
    def center(self) -> dict:
        return self.coordinator.data.get("centercontroller") or {}

    @property
    def available(self) -> bool:
        return bool(self.center) and system_is_heating(self.coordinator.data)

    @property
    def current_option(self) -> str | None:
        return HEATING_MODE_LABELS.get(self.center.get("HeatingMode"))

    @property
    def device_info(self):
        return build_center_device_info(self.center)

    @property
    def suggested_object_id(self) -> str:
        return center_object_id("heating_mode")

    async def async_select_option(self, option: str) -> None:
        if not system_is_heating(self.coordinator.data):
            return
        await self.api.async_set_heating_mode(
            self.center["deviceId"], HEATING_LABEL_TO_MODE[option]
        )
        await self.coordinator.async_request_refresh()
