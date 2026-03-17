from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONCENTRATION_MICROGRAMS_PER_CUBIC_METER, EntityCategory, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, HEATING_MODE_LABELS, THERMOSTAT_MODE_LABELS, WIND_RATE_LABELS
from .entity_helpers import (
    build_center_device_info,
    build_thermostat_device_info,
    center_object_id,
    decode_half_degree,
    decode_number,
    first_number,
    get_thermostat,
    has_air_metrics,
    thermostat_object_id,
)


def _always(_: dict[str, Any]) -> bool:
    return True


def _has_room_humidity(thermostat: dict[str, Any]) -> bool:
    return thermostat.get("humCurValue") not in (None, 0) or has_air_metrics(thermostat)


def _has_air_temperature(thermostat: dict[str, Any]) -> bool:
    return has_air_metrics(thermostat) and thermostat.get("airDrumTempValue") not in (None, 0)


def _has_air_humidity(thermostat: dict[str, Any]) -> bool:
    return has_air_metrics(thermostat) and thermostat.get("airDrumHumValue") not in (None, 0)


def _has_pm25(thermostat: dict[str, Any]) -> bool:
    return has_air_metrics(thermostat)


def _has_co2(thermostat: dict[str, Any]) -> bool:
    return has_air_metrics(thermostat)


def _has_tvoc(thermostat: dict[str, Any]) -> bool:
    return has_air_metrics(thermostat)


def _has_formaldehyde(thermostat: dict[str, Any]) -> bool:
    return has_air_metrics(thermostat)


@dataclass(frozen=True, kw_only=True)
class ThermostatSensorDescription(SensorEntityDescription):
    unique_suffix: str
    value_fn: Callable[[dict[str, Any]], str | int | float | None]
    exists_fn: Callable[[dict[str, Any]], bool] = _always


THERMOSTAT_SENSOR_DESCRIPTIONS: tuple[ThermostatSensorDescription, ...] = (
    ThermostatSensorDescription(
        key="realTempStatus",
        name="Room Temperature",
        unique_suffix="room_temperature",
        icon="mdi:home-thermometer",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda thermostat: decode_half_degree(thermostat.get("realTempStatus")),
    ),
    ThermostatSensorDescription(
        key="setTempStatus",
        name="Target Temperature",
        unique_suffix="target_temperature",
        icon="mdi:thermometer-chevron-up",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda thermostat: decode_half_degree(thermostat.get("setTempStatus")),
    ),
    ThermostatSensorDescription(
        key="workModelStatus",
        name="Mode",
        unique_suffix="mode",
        icon="mdi:hvac",
        value_fn=lambda thermostat: THERMOSTAT_MODE_LABELS.get(thermostat.get("workModelStatus")),
    ),
    ThermostatSensorDescription(
        key="windModelStatus",
        name="Fan Speed",
        unique_suffix="fan_speed",
        icon="mdi:fan",
        value_fn=lambda thermostat: WIND_RATE_LABELS.get(thermostat.get("windModelStatus")),
    ),
    ThermostatSensorDescription(
        key="humCurValue",
        name="Room Humidity",
        unique_suffix="room_humidity",
        icon="mdi:water-percent",
        device_class=SensorDeviceClass.HUMIDITY,
        native_unit_of_measurement="%",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda thermostat: decode_number(thermostat.get("humCurValue")),
        exists_fn=_has_room_humidity,
    ),
    ThermostatSensorDescription(
        key="airDrumTempValue",
        name="Air Temperature",
        unique_suffix="air_temperature",
        icon="mdi:thermometer-lines",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda thermostat: decode_half_degree(thermostat.get("airDrumTempValue")),
        exists_fn=_has_air_temperature,
    ),
    ThermostatSensorDescription(
        key="airDrumHumValue",
        name="Air Humidity",
        unique_suffix="air_humidity",
        icon="mdi:air-humidifier",
        device_class=SensorDeviceClass.HUMIDITY,
        native_unit_of_measurement="%",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda thermostat: decode_number(thermostat.get("airDrumHumValue")),
        exists_fn=_has_air_humidity,
    ),
    ThermostatSensorDescription(
        key="airDrumPM2Value",
        name="PM2.5",
        unique_suffix="pm25",
        icon="mdi:blur",
        device_class=SensorDeviceClass.PM25,
        native_unit_of_measurement=CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda thermostat: decode_number(thermostat.get("airDrumPM2Value")),
        exists_fn=_has_pm25,
    ),
    ThermostatSensorDescription(
        key="airDrumCO2Value",
        name="CO2",
        unique_suffix="co2",
        icon="mdi:molecule-co2",
        device_class=SensorDeviceClass.CO2,
        native_unit_of_measurement="ppm",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda thermostat: decode_number(thermostat.get("airDrumCO2Value")),
        exists_fn=_has_co2,
    ),
    ThermostatSensorDescription(
        key="airDrumTVOCValue",
        name="TVOC",
        unique_suffix="tvoc",
        icon="mdi:chemical-weapon",
        native_unit_of_measurement=CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda thermostat: first_number(
            thermostat.get("airDrumTVOCValue"),
            thermostat.get("TVOCValue"),
        ),
        exists_fn=_has_tvoc,
    ),
    ThermostatSensorDescription(
        key="formaldehydeValue",
        name="Formaldehyde",
        unique_suffix="formaldehyde",
        icon="mdi:flask",
        native_unit_of_measurement=CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda thermostat: decode_number(thermostat.get("formaldehydeValue")),
        exists_fn=_has_formaldehyde,
    ),
)


@dataclass(frozen=True, kw_only=True)
class CenterSensorDescription(SensorEntityDescription):
    unique_suffix: str
    value_fn: Callable[[dict[str, Any]], str | int | float | None]


CENTER_SENSOR_DESCRIPTIONS: tuple[CenterSensorDescription, ...] = (
    CenterSensorDescription(
        key="HeatingMode",
        name="Heating Mode",
        unique_suffix="heating_mode",
        icon="mdi:heat-wave",
        value_fn=lambda center: HEATING_MODE_LABELS.get(center.get("HeatingMode")),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    entities: list[Entity] = []

    for thermostat in coordinator.data.get("thermostats", []):
        for description in THERMOSTAT_SENSOR_DESCRIPTIONS:
            if description.exists_fn(thermostat):
                entities.append(AOSmithThermostatSensorEntity(coordinator, thermostat, description))

    center = coordinator.data.get("centercontroller")
    if center:
        for description in CENTER_SENSOR_DESCRIPTIONS:
            entities.append(AOSmithCenterSensorEntity(coordinator, description))

    async_add_entities(entities)


class AOSmithThermostatSensorEntity(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator,
        thermostat: dict[str, Any],
        description: ThermostatSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self.device_id = thermostat["deviceId"]
        self._attr_unique_id = f"{self.device_id}_{description.unique_suffix}"
        self._attr_name = description.name
        self._attr_icon = description.icon
        self._attr_device_class = description.device_class
        self._attr_native_unit_of_measurement = description.native_unit_of_measurement
        self._attr_state_class = description.state_class
        self._attr_entity_category = description.entity_category

    @property
    def thermostat(self) -> dict[str, Any]:
        return get_thermostat(self.coordinator.data, self.device_id)

    @property
    def available(self) -> bool:
        return bool(self.thermostat)

    @property
    def device_info(self):
        return build_thermostat_device_info(self.thermostat, self.device_id)

    @property
    def suggested_object_id(self) -> str | None:
        return thermostat_object_id(
            self.thermostat,
            self.device_id,
            self.entity_description.unique_suffix,
        )

    @property
    def native_value(self) -> str | int | float | None:
        return self.entity_description.value_fn(self.thermostat)


class AOSmithCenterSensorEntity(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, description: CenterSensorDescription) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"centercontroller_{description.unique_suffix}"
        self._attr_name = description.name
        self._attr_icon = description.icon

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
        return center_object_id(self.entity_description.unique_suffix)

    @property
    def native_value(self) -> str | int | float | None:
        return self.entity_description.value_fn(self.center)
