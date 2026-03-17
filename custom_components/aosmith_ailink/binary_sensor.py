from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .entity_helpers import (
    build_center_device_info,
    build_thermostat_device_info,
    center_object_id,
    enabled,
    get_thermostat,
    thermostat_object_id,
)


@dataclass(frozen=True, kw_only=True)
class ThermostatBinarySensorDescription(BinarySensorEntityDescription):
    key: str
    unique_suffix: str
    value_fn: Callable[[dict[str, Any]], bool]


THERMOSTAT_BINARY_SENSOR_DESCRIPTIONS: tuple[ThermostatBinarySensorDescription, ...] = (
    ThermostatBinarySensorDescription(
        key="power",
        name="Power",
        unique_suffix="power",
        icon="mdi:power",
        device_class=BinarySensorDeviceClass.POWER,
        value_fn=lambda thermostat: enabled(thermostat.get("powerStatus")),
    ),
    ThermostatBinarySensorDescription(
        key="main_thermostat",
        name="Main Thermostat",
        unique_suffix="main_thermostat",
        icon="mdi:star-circle",
        value_fn=lambda thermostat: enabled(thermostat.get("mainWenKongFlag")),
    ),
)


@dataclass(frozen=True, kw_only=True)
class CenterBinarySensorDescription(BinarySensorEntityDescription):
    key: str
    unique_suffix: str
    value_fn: Callable[[dict[str, Any]], bool]


CENTER_BINARY_SENSOR_DESCRIPTIONS: tuple[CenterBinarySensorDescription, ...] = (
    CenterBinarySensorDescription(
        key="eco_warm",
        name="Eco Warm",
        unique_suffix="eco_warm",
        icon="mdi:leaf",
        value_fn=lambda center: enabled(center.get("ecoWarm")),
    ),
    CenterBinarySensorDescription(
        key="speed_warm",
        name="Speed Warm",
        unique_suffix="speed_warm",
        icon="mdi:rocket-launch",
        value_fn=lambda center: enabled(center.get("speedWarm")),
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
        for description in THERMOSTAT_BINARY_SENSOR_DESCRIPTIONS:
            entities.append(AOSmithThermostatBinarySensorEntity(coordinator, thermostat, description))

    if coordinator.data.get("centercontroller"):
        for description in CENTER_BINARY_SENSOR_DESCRIPTIONS:
            entities.append(AOSmithCenterBinarySensorEntity(coordinator, description))

    async_add_entities(entities)


class AOSmithThermostatBinarySensorEntity(CoordinatorEntity, BinarySensorEntity):
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator,
        thermostat: dict[str, Any],
        description: ThermostatBinarySensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self.device_id = thermostat["deviceId"]
        self._attr_unique_id = f"{self.device_id}_{description.unique_suffix}"
        self._attr_name = description.name
        self._attr_icon = description.icon
        self._attr_device_class = description.device_class

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
    def is_on(self) -> bool:
        return self.entity_description.value_fn(self.thermostat)


class AOSmithCenterBinarySensorEntity(CoordinatorEntity, BinarySensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, description: CenterBinarySensorDescription) -> None:
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
    def is_on(self) -> bool:
        return self.entity_description.value_fn(self.center)
