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
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    HEAT_CAPABLE_MODES,
    THERMOSTAT_LABEL_TO_MODE,
    THERMOSTAT_MODE_LABELS,
    THERMOSTAT_MODE_TO_HVAC,
    WIND_LABEL_TO_RATE,
    WIND_RATE_LABELS,
)
from .entity_helpers import (
    async_set_whole_home_mode,
    build_thermostat_device_info,
    decode_half_degree,
    get_thermostat,
    thermostat_object_id,
    thermostat_mode_for_center_heating,
    thermostat_common_attributes,
)


SAFE_COOLING_TEMPERATURE = 26.0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    thermostats = coordinator.data.get("thermostats", [])
    async_add_entities(
        AOSmithThermostatEntity(coordinator, hass.data[DOMAIN][entry.entry_id]["api"], item)
        for item in thermostats
    )


class AOSmithThermostatEntity(CoordinatorEntity, RestoreEntity, ClimateEntity):
    _attr_has_entity_name = True
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.FAN_MODE
    if hasattr(ClimateEntityFeature, "PRESET_MODE"):
        _attr_supported_features |= ClimateEntityFeature.PRESET_MODE
    if hasattr(ClimateEntityFeature, "TURN_ON"):
        _attr_supported_features |= ClimateEntityFeature.TURN_ON
    if hasattr(ClimateEntityFeature, "TURN_OFF"):
        _attr_supported_features |= ClimateEntityFeature.TURN_OFF
    _attr_target_temperature_step = 0.5
    _attr_min_temp = 16
    _attr_max_temp = 30
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.COOL, HVACMode.HEAT, HVACMode.FAN_ONLY, HVACMode.DRY]
    _attr_fan_modes = list(WIND_LABEL_TO_RATE.keys())
    _attr_preset_modes = list(THERMOSTAT_LABEL_TO_MODE.keys())

    def __init__(self, coordinator, api, thermostat: dict[str, Any]) -> None:
        super().__init__(coordinator)
        self.api = api
        self.device_id = thermostat["deviceId"]
        self._attr_unique_id = self.device_id
        self._attr_name = None
        self._last_heat_mode: int = 3  # 默认地暖

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (last_state := await self.async_get_last_state()) and last_state.attributes.get("preset_mode"):
            preset = last_state.attributes["preset_mode"]
            if preset in THERMOSTAT_LABEL_TO_MODE and THERMOSTAT_LABEL_TO_MODE[preset] in HEAT_CAPABLE_MODES:
                self._last_heat_mode = THERMOSTAT_LABEL_TO_MODE[preset]

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
        mode = self.thermostat.get("workModelStatus")
        return THERMOSTAT_MODE_TO_HVAC.get(mode, HVACMode.HEAT)

    @property
    def hvac_action(self) -> HVACAction:
        if self.thermostat.get("powerStatus") != 1:
            return HVACAction.OFF
        hvac_mode = self.hvac_mode
        if hvac_mode == HVACMode.COOL:
            return HVACAction.COOLING
        if hvac_mode == HVACMode.DRY:
            return HVACAction.DRYING
        if hvac_mode == HVACMode.FAN_ONLY:
            return HVACAction.FAN
        return HVACAction.HEATING

    @property
    def preset_mode(self) -> str | None:
        mode = self.thermostat.get("workModelStatus")
        if mode in HEAT_CAPABLE_MODES and self.thermostat.get("powerStatus") == 1:
            self._last_heat_mode = mode
        return THERMOSTAT_MODE_LABELS.get(mode)

    @property
    def fan_mode(self) -> str | None:
        rate = self.thermostat.get("windModelStatus")
        return WIND_RATE_LABELS.get(rate)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs = thermostat_common_attributes(self.thermostat)
        attrs["power_status"] = self.thermostat.get("powerStatus")
        return attrs

    async def async_turn_on(self) -> None:
        active_modes = [
            item.get("workModelStatus")
            for item in self.coordinator.data.get("thermostats", [])
            if item.get("powerStatus") == 1 and item.get("deviceId") != self.device_id
        ]
        mode = active_modes[0] if active_modes else self.thermostat.get("workModelStatus")
        if mode not in THERMOSTAT_MODE_TO_HVAC:
            mode = thermostat_mode_for_center_heating(self.coordinator.data)

        await async_set_whole_home_mode(
            self.coordinator,
            self.api,
            mode,
            power_device_id=self.device_id,
        )

        # Keep the controller's last mode. HomeKit calls turn_on without a mode,
        # so forcing heating here can unexpectedly carry a 28 C heating setpoint
        # into a cooling request.
        if (
            self.thermostat.get("workModelStatus") == 0
            and (target := self.target_temperature) is not None
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
            await self.api.async_set_thermostat_power(self.device_id, False)
            await self.coordinator.async_request_refresh()
            return

        if hvac_mode == HVACMode.COOL:
            await async_set_whole_home_mode(
                self.coordinator,
                self.api,
                0,
                power_device_id=self.device_id,
            )
            target = self.target_temperature
            if target is None or target > 27:
                await self.api.async_set_thermostat_setpoint(
                    self.device_id, SAFE_COOLING_TEMPERATURE
                )
        elif hvac_mode == HVACMode.FAN_ONLY:
            await async_set_whole_home_mode(
                self.coordinator,
                self.api,
                2,
                power_device_id=self.device_id,
            )
        elif hvac_mode == HVACMode.DRY:
            await async_set_whole_home_mode(
                self.coordinator,
                self.api,
                5,
                power_device_id=self.device_id,
            )
        elif hvac_mode == HVACMode.HEAT:
            target_mode = thermostat_mode_for_center_heating(self.coordinator.data)
            await async_set_whole_home_mode(
                self.coordinator,
                self.api,
                target_mode,
                power_device_id=self.device_id,
            )

        await self.coordinator.async_request_refresh()

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        mode = THERMOSTAT_LABEL_TO_MODE[preset_mode]
        await async_set_whole_home_mode(
            self.coordinator,
            self.api,
            mode,
            power_device_id=self.device_id,
        )

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        rate = WIND_LABEL_TO_RATE[fan_mode]
        await self.api.async_set_thermostat_wind_rate(self.device_id, rate)
        await self.coordinator.async_request_refresh()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        hvac_mode = kwargs.get("hvac_mode")
        if hvac_mode is not None:
            await self.async_set_hvac_mode(hvac_mode)

        temperature = kwargs.get("temperature")
        if temperature is not None:
            await self.api.async_set_thermostat_setpoint(self.device_id, float(temperature))
            await self.coordinator.async_request_refresh()
