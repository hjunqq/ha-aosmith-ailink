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
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    HEAT_CAPABLE_MODES,
    ROOM_HEATING_OPTIONS,
    WIND_LABEL_TO_RATE,
    WIND_RATE_LABELS,
)
from .entity_helpers import (
    build_thermostat_device_info,
    decode_half_degree,
    get_thermostat,
    system_mode_code,
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
        | ClimateEntityFeature.PRESET_MODE
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
        return super().available and bool(self.thermostat)

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
    def preset_modes(self) -> list[str]:
        return [
            label for label, (_, capability) in ROOM_HEATING_OPTIONS.items()
            if self.thermostat.get(capability) == 1
        ]

    @property
    def preset_mode(self) -> str | None:
        mode = self.thermostat.get("workModelStatus")
        if self.thermostat.get("powerStatus") != 1 or mode not in HEAT_CAPABLE_MODES:
            mode = self.coordinator.room_heat_modes.get(self.device_id, mode)
        return next((label for label, (value, _) in ROOM_HEATING_OPTIONS.items() if value == mode), None)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs = thermostat_common_attributes(self.thermostat)
        attrs["power_status"] = self.thermostat.get("powerStatus")
        attrs["system_mode_status"] = system_thermostat_mode(self.coordinator.data)
        return attrs

    async def async_turn_on(self) -> None:
        await self._async_apply(start=True)

    async def async_turn_off(self) -> None:
        async with self.coordinator.command_lock:
            await self.api.async_set_thermostat_power(self.device_id, False)
            await self.coordinator.async_request_refresh()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        if hvac_mode == HVACMode.OFF:
            await self.async_turn_off()
            return

        await self._async_apply(hvac_mode=hvac_mode, start=True)

    def _check_room(self, data, hvac_mode=None):
        system = system_mode_code(data)
        room = get_thermostat(data, self.device_id)
        if self.coordinator.stopped or system is None or room.get("powerStatus") not in (0, 1):
            raise ServiceValidationError("Whole-home control is stopped or its state is unavailable")
        expected = HVACMode.COOL if system == 0 else HVACMode.HEAT
        if hvac_mode is not None and hvac_mode != expected:
            raise ServiceValidationError("The requested mode conflicts with the whole-home mode")
        boilers = data.get("boilers", [])
        if system == 0 and (
            len(boilers) < self.coordinator.boiler_count
            or any(boiler.get("warmStatus") != 0 for boiler in boilers)
        ):
            raise ServiceValidationError("Boiler space heating has not reported idle")
        return expected, room

    async def _async_apply(self, *, hvac_mode=None, temperature=None, start=False) -> None:
        async with self.coordinator.command_lock:
            data = await self.coordinator.async_control_snapshot()
            expected, room = self._check_room(data, hvac_mode)
            current_temp = decode_half_degree(room.get("setTempStatus"))
            if start:
                raw_mode = room.get("workModelStatus")
                if expected == HVACMode.COOL:
                    desired_mode = 0
                    if temperature is None and (current_temp is None or current_temp > 27):
                        temperature = SAFE_COOLING_TEMPERATURE
                elif room.get("powerStatus") == 0:
                    fallback = raw_mode if raw_mode in HEAT_CAPABLE_MODES else 3
                    desired_mode = self.coordinator.room_heat_modes.get(self.device_id, fallback)
                    capability = {1: "supWarm", 3: "supFloorWarm", 4: "supDoubleEnergy"}[desired_mode]
                    if room.get(capability) != 1:
                        raise ServiceValidationError("Choose a supported heating method for this room first")
                else:
                    if raw_mode not in HEAT_CAPABLE_MODES:
                        raise ServiceValidationError("This room has not reported a heating mode")
                    desired_mode = raw_mode
                if raw_mode != desired_mode:
                    if room.get("powerStatus") != 0:
                        raise ServiceValidationError("Turn this room off before changing its operating mode")
                    await self.api.async_set_thermostat_mode(self.device_id, desired_mode)
                    await self.coordinator.async_confirm(
                        lambda state: self._check_room(state, expected)[1].get("workModelStatus") == desired_mode,
                        "Could not confirm the room operating mode",
                    )
            if temperature is not None and current_temp != float(temperature):
                await self.api.async_set_thermostat_setpoint(self.device_id, float(temperature))
                if start and room.get("powerStatus") == 0:
                    await self.coordinator.async_confirm(
                        lambda state: decode_half_degree(self._check_room(state, expected)[1].get("setTempStatus"))
                        == round(float(temperature) * 2) / 2,
                        "Target temperature was not confirmed; room remains off",
                    )
            if start and room.get("powerStatus") == 0:
                _, latest = self._check_room(await self.coordinator.async_control_snapshot(), expected)
                if latest.get("workModelStatus") != desired_mode:
                    raise ServiceValidationError("The room mode changed before power-on")
                if latest.get("powerStatus") == 0:
                    await self.api.async_set_thermostat_power(self.device_id, True)
            await self.coordinator.async_request_refresh()

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        desired, capability = ROOM_HEATING_OPTIONS[preset_mode]
        async with self.coordinator.command_lock:
            data = await self.coordinator.async_control_snapshot()
            _, room = self._check_room(data, HVACMode.HEAT)
            if room.get(capability) != 1:
                raise ServiceValidationError("This room does not support the selected heating method")
            if room.get("powerStatus") == 1 and room.get("workModelStatus") != desired:
                if room.get("workModelStatus") not in HEAT_CAPABLE_MODES:
                    raise ServiceValidationError("Turn this room off before selecting its heating method")
                await self.api.async_set_thermostat_mode(self.device_id, desired)
                await self.coordinator.async_confirm(
                    lambda state: self._check_room(state, HVACMode.HEAT)[1].get("workModelStatus") == desired,
                    "The thermostat did not confirm the heating method",
                )
            self.coordinator.room_heat_modes[self.device_id] = desired
            await self.coordinator.async_save_controls()
            await self.coordinator.async_request_refresh()

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        async with self.coordinator.command_lock:
            self._check_room(await self.coordinator.async_control_snapshot())
            await self.api.async_set_thermostat_wind_rate(self.device_id, WIND_LABEL_TO_RATE[fan_mode])
            await self.coordinator.async_request_refresh()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        hvac_mode = kwargs.get("hvac_mode")
        temperature = kwargs.get("temperature")
        if hvac_mode == HVACMode.OFF:
            await self.async_turn_off()
        elif temperature is not None or hvac_mode is not None:
            await self._async_apply(
                hvac_mode=hvac_mode, temperature=temperature, start=hvac_mode is not None
            )
