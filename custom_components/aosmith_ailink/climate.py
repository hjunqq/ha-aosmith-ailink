from __future__ import annotations

from typing import Any

from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import (
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    HEAT_CAPABLE_MODES,
    WIND_LABEL_TO_RATE,
    WIND_RATE_LABELS,
)
from .entity_helpers import (
    async_set_system_mode,
    build_thermostat_device_info,
    decode_half_degree,
    get_thermostat,
    system_thermostat_mode,
    thermostat_common_attributes,
    thermostat_object_id,
)


SAFE_COOLING_TEMPERATURE = 26.0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    api = hass.data[DOMAIN][entry.entry_id]["api"]
    async_add_entities(
        AOSmithThermostatEntity(coordinator, api, thermostat)
        for thermostat in coordinator.data.get("thermostats", [])
    )


class AOSmithThermostatEntity(CoordinatorEntity, ClimateEntity):
    _attr_has_entity_name = True
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.FAN_MODE
    )
    if hasattr(ClimateEntityFeature, "TURN_ON"):
        _attr_supported_features |= ClimateEntityFeature.TURN_ON
    if hasattr(ClimateEntityFeature, "TURN_OFF"):
        _attr_supported_features |= ClimateEntityFeature.TURN_OFF
    _attr_target_temperature_step = 0.5
    _attr_min_temp = 16
    _attr_max_temp = 30
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.COOL, HVACMode.HEAT]
    _attr_fan_modes = list(WIND_LABEL_TO_RATE.keys())

    def __init__(self, coordinator, api, thermostat: dict[str, Any]) -> None:
        super().__init__(coordinator)
        self.api = api
        self.device_id = thermostat["deviceId"]
        self._attr_unique_id = self.device_id
        self._attr_name = None

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
        return thermostat_object_id(self.thermostat, self.device_id)

    @property
    def current_temperature(self) -> float | None:
        return decode_half_degree(self.thermostat.get("realTempStatus"))

    @property
    def target_temperature(self) -> float | None:
        return decode_half_degree(self.thermostat.get("setTempStatus"))

    @property
    def hvac_mode(self) -> HVACMode:
        if self.thermostat.get("powerStatus") != 1:
            return HVACMode.OFF
        system_mode = system_thermostat_mode(self.coordinator.data)
        if system_mode == 0:
            return HVACMode.COOL
        if system_mode in HEAT_CAPABLE_MODES:
            return HVACMode.HEAT
        return HVACMode.OFF

    @property
    def hvac_action(self) -> HVACAction:
        if self.hvac_mode == HVACMode.COOL:
            return HVACAction.COOLING
        if self.hvac_mode == HVACMode.HEAT:
            return HVACAction.HEATING
        return HVACAction.OFF

    @property
    def fan_mode(self) -> str | None:
        return WIND_RATE_LABELS.get(self.thermostat.get("windModelStatus"))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs = thermostat_common_attributes(self.thermostat)
        attrs["power_status"] = self.thermostat.get("powerStatus")
        attrs["system_mode_status"] = system_thermostat_mode(self.coordinator.data)
        return attrs

    async def async_turn_on(self) -> None:
        # Generic HomeKit turn-on is allowed only while the whole-home system is
        # already cooling. Heating always requires an explicit HEAT command.
        if system_thermostat_mode(self.coordinator.data) != 0:
            return
        await async_set_system_mode(
            self.coordinator,
            self.api,
            0,
            power_device_id=self.device_id,
        )
        if (
            (target := self.target_temperature) is not None
            and target > 27
        ):
            await self.api.async_set_thermostat_setpoint(
                self.device_id, SAFE_COOLING_TEMPERATURE
            )
            await self.coordinator.async_request_refresh()

    async def async_turn_off(self) -> None:
        await self.api.async_set_thermostat_power(self.device_id, False)
        await self.coordinator.async_request_refresh()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        if hvac_mode == HVACMode.OFF:
            await self.async_turn_off()
            return

        if hvac_mode == HVACMode.COOL:
            await async_set_system_mode(
                self.coordinator,
                self.api,
                0,
                power_device_id=self.device_id,
            )
            if self.target_temperature is None or self.target_temperature > 27:
                await self.api.async_set_thermostat_setpoint(
                    self.device_id, SAFE_COOLING_TEMPERATURE
                )
                await self.coordinator.async_request_refresh()
            return

        if hvac_mode == HVACMode.HEAT:
            await async_set_system_mode(
                self.coordinator,
                self.api,
                1,
                power_device_id=self.device_id,
            )

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        await self.api.async_set_thermostat_wind_rate(
            self.device_id, WIND_LABEL_TO_RATE[fan_mode]
        )
        await self.coordinator.async_request_refresh()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        hvac_mode = kwargs.get("hvac_mode")
        if hvac_mode is not None:
            await self.async_set_hvac_mode(hvac_mode)

        temperature = kwargs.get("temperature")
        if temperature is not None:
            await self.api.async_set_thermostat_setpoint(
                self.device_id, float(temperature)
            )
            await self.coordinator.async_request_refresh()
