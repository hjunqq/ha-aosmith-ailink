from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CENTER_HEATING_TO_THERMOSTAT_MODE,
    DOMAIN,
    HEATING_MODE_LABELS,
    THERMOSTAT_LABEL_TO_MODE,
    THERMOSTAT_MODE_LABELS,
)
from .entity_helpers import (
    async_set_whole_home_mode,
    async_set_whole_home_heating_strategy,
    build_center_device_info,
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
        [
            *(
                AOSmithModeSwitch(coordinator, api, item, label, mode)
                for item in thermostats
                for label, mode in THERMOSTAT_LABEL_TO_MODE.items()
            ),
            *(
                AOSmithWholeHomeHeatingSwitch(
                    coordinator,
                    api,
                    coordinator.data["centercontroller"],
                    label,
                    center_mode,
                    CENTER_HEATING_TO_THERMOSTAT_MODE[center_mode],
                )
                for center_mode, label in HEATING_MODE_LABELS.items()
            ),
        ]
        if coordinator.data.get("centercontroller")
        else [
            AOSmithModeSwitch(coordinator, api, item, label, mode)
            for item in thermostats
            for label, mode in THERMOSTAT_LABEL_TO_MODE.items()
        ]
    )


class AOSmithWholeHomeHeatingSwitch(CoordinatorEntity, SwitchEntity):
    _attr_has_entity_name = False

    def __init__(
        self,
        coordinator,
        api,
        center: dict[str, Any],
        label: str,
        center_mode: int,
        thermostat_mode: int,
    ) -> None:
        super().__init__(coordinator)
        self.api = api
        self.device_id = center["deviceId"]
        self._center_mode = center_mode
        self._thermostat_mode = thermostat_mode
        self._strategy_slug = {
            0: "eco",
            1: "max",
            2: "boiler",
            3: "heat_pump",
        }[center_mode]
        self._attr_unique_id = f"{self.device_id}_whole_home_heating_{center_mode}"
        self._attr_name = f"全屋{label}"

    @property
    def center(self) -> dict[str, Any]:
        return self.coordinator.data.get("centercontroller") or {}

    @property
    def available(self) -> bool:
        return bool(self.center)

    @property
    def device_info(self):
        return build_center_device_info(self.center)

    @property
    def suggested_object_id(self) -> str | None:
        return f"ao_smith_whole_home_heating_{self._strategy_slug}"

    @property
    def is_on(self) -> bool:
        return self.center.get("HeatingMode") == self._center_mode

    async def async_turn_on(self, **kwargs: Any) -> None:
        await async_set_whole_home_heating_strategy(
            self.coordinator,
            self.api,
            self._center_mode,
            self._thermostat_mode,
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        # These switches form a radio group; select another strategy instead.
        return


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
        await async_set_whole_home_mode(
            self.coordinator,
            self.api,
            self._mode_value,
            power_device_id=self.device_id,
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.api.async_set_thermostat_power(self.device_id, False)
        await self.coordinator.async_request_refresh()
