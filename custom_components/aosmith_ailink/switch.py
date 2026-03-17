from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, THERMOSTAT_LABEL_TO_MODE, THERMOSTAT_MODE_LABELS
from .entity_helpers import (
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
    thermostats = coordinator.data.get("thermostats", [])
    async_add_entities(
        AOSmithModeSwitch(coordinator, api, item, label, mode)
        for item in thermostats
        for label, mode in THERMOSTAT_LABEL_TO_MODE.items()
    )


class AOSmithModeSwitch(CoordinatorEntity, SwitchEntity):
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator,
        api,
        thermostat: dict[str, Any],
        label: str,
        mode: int,
    ) -> None:
        super().__init__(coordinator)
        self.api = api
        self.device_id = thermostat["deviceId"]
        self._mode_label = label
        self._mode_value = mode
        self._attr_unique_id = f"{self.device_id}_mode_{mode}"
        self._attr_name = label

    @property
    def thermostat(self) -> dict[str, Any]:
        return get_thermostat(self.coordinator.data, self.device_id)

    @property
    def available(self) -> bool:
        return bool(self.thermostat)

    @property
    def device_info(self):
        return build_thermostat_device_info(
            self.thermostat,
            self.thermostat.get("roomName") or self.device_id,
        )

    @property
    def suggested_object_id(self) -> str | None:
        base = thermostat_object_id(self.thermostat, self.device_id)
        return f"{base}_{self._mode_label}" if base else None

    @property
    def is_on(self) -> bool:
        t = self.thermostat
        return (
            t.get("powerStatus") == 1
            and t.get("workModelStatus") == self._mode_value
        )

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.api.async_set_thermostat_power(self.device_id, True)
        await self.api.async_set_thermostat_mode(self.device_id, self._mode_value)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.api.async_set_thermostat_power(self.device_id, False)
        await self.coordinator.async_request_refresh()
