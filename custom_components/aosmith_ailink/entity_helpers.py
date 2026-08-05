from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.util import slugify

from .const import (
    CENTER_HEATING_TO_THERMOSTAT_MODE,
    DOMAIN,
    HEAT_CAPABLE_MODES,
    THERMOSTAT_MODE_LABELS,
    THERMOSTAT_SUPPORT_LABELS,
    WIND_RATE_LABELS,
)


def center_heating_mode_for_thermostat_mode(
    data: dict[str, Any], thermostat_mode: int
) -> int | None:
    if thermostat_mode == 1:
        return 3
    if thermostat_mode == 3:
        return 2
    if thermostat_mode == 4:
        current = (data.get("centercontroller") or {}).get("HeatingMode")
        return current if current in (0, 1) else 0
    return None


def thermostat_mode_for_center_heating(data: dict[str, Any]) -> int:
    center_mode = (data.get("centercontroller") or {}).get("HeatingMode")
    return CENTER_HEATING_TO_THERMOSTAT_MODE.get(center_mode, 3)


async def async_set_whole_home_mode(
    coordinator,
    api,
    thermostat_mode: int,
    *,
    power_device_id: str | None = None,
    center_heating_mode: int | None = None,
) -> None:
    """Apply a shared mode to active rooms without changing inactive rooms."""
    data = coordinator.data
    center = data.get("centercontroller") or {}
    desired_center_mode = center_heating_mode
    if desired_center_mode is None:
        desired_center_mode = center_heating_mode_for_thermostat_mode(
            data, thermostat_mode
        )

    if (
        desired_center_mode is not None
        and center.get("deviceId")
        and center.get("HeatingMode") != desired_center_mode
    ):
        await api.async_set_heating_mode(center["deviceId"], desired_center_mode)

    if power_device_id is not None:
        await api.async_set_thermostat_power(power_device_id, True)

    for thermostat in data.get("thermostats", []):
        is_target = thermostat.get("deviceId") == power_device_id
        if not is_target and thermostat.get("powerStatus") != 1:
            continue
        if thermostat.get("workModelStatus") == thermostat_mode:
            continue
        await api.async_set_thermostat_mode(thermostat["deviceId"], thermostat_mode)

    await coordinator.async_request_refresh()


async def async_set_whole_home_heating_strategy(
    coordinator,
    api,
    center_heating_mode: int,
    thermostat_mode: int,
) -> None:
    """Select a heat source without converting active cooling rooms to heat."""
    data = coordinator.data
    center = data.get("centercontroller") or {}
    if (
        center.get("deviceId")
        and center.get("HeatingMode") != center_heating_mode
    ):
        await api.async_set_heating_mode(center["deviceId"], center_heating_mode)

    for thermostat in data.get("thermostats", []):
        current_mode = thermostat.get("workModelStatus")
        if thermostat.get("powerStatus") != 1 or current_mode not in HEAT_CAPABLE_MODES:
            continue
        if current_mode == thermostat_mode:
            continue
        await api.async_set_thermostat_mode(thermostat["deviceId"], thermostat_mode)

    await coordinator.async_request_refresh()


def get_thermostat(data: dict[str, Any], device_id: str) -> dict[str, Any]:
    for item in data.get("thermostats", []):
        if item.get("deviceId") == device_id:
            return item
    return {}


def decode_number(value: Any, *, divisor: float = 1) -> float | None:
    if isinstance(value, (int, float)):
        return float(value) / divisor
    if isinstance(value, str):
        try:
            return float(value) / divisor
        except ValueError:
            return None
    return None


def decode_half_degree(value: Any) -> float | None:
    return decode_number(value, divisor=2)


def first_number(*values: Any) -> float | None:
    for value in values:
        decoded = decode_number(value)
        if decoded is not None:
            return decoded
    return None


def enabled(value: Any) -> bool:
    return value == 1


def has_air_metrics(thermostat: dict[str, Any]) -> bool:
    return thermostat.get("airBoardVersion") not in (None, "", "v0.0")


def thermostat_supported_modes(thermostat: dict[str, Any]) -> list[str]:
    supported: list[str] = []
    for field, label in THERMOSTAT_SUPPORT_LABELS.items():
        if enabled(thermostat.get(field)):
            supported.append(label)
    return supported


def thermostat_common_attributes(thermostat: dict[str, Any]) -> dict[str, Any]:
    attrs: dict[str, Any] = {
        "device_id": thermostat.get("deviceId"),
        "room_name": thermostat.get("roomName"),
        "product_name": thermostat.get("productName"),
        "is_main_thermostat": enabled(thermostat.get("mainWenKongFlag")),
        "work_model_status": thermostat.get("workModelStatus"),
        "work_model_label": THERMOSTAT_MODE_LABELS.get(thermostat.get("workModelStatus")),
        "wind_model_status": thermostat.get("windModelStatus"),
        "wind_label": WIND_RATE_LABELS.get(thermostat.get("windModelStatus")),
        "supported_modes": thermostat_supported_modes(thermostat),
    }

    for field in (
        "supCold",
        "supWarm",
        "supWind",
        "supFloorWarm",
        "supDoubleEnergy",
        "supfunction1",
        "supfunction2",
        "supFloorCold",
        "withNewAir",
        "withAir",
        "withAirNut",
        "newAirDeviceStatus",
        "supSleep",
    ):
        if field in thermostat:
            attrs[field] = thermostat.get(field)

    for key, value in (
        ("room_temperature", decode_half_degree(thermostat.get("realTempStatus"))),
        ("target_temperature", decode_half_degree(thermostat.get("setTempStatus"))),
        ("room_humidity", decode_number(thermostat.get("humCurValue"))),
        ("air_temperature", decode_half_degree(thermostat.get("airDrumTempValue"))),
        ("air_humidity", decode_number(thermostat.get("airDrumHumValue"))),
        ("pm25", decode_number(thermostat.get("airDrumPM2Value"))),
        ("co2", decode_number(thermostat.get("airDrumCO2Value"))),
        ("tvoc", first_number(thermostat.get("airDrumTVOCValue"), thermostat.get("TVOCValue"))),
        ("formaldehyde", decode_number(thermostat.get("formaldehydeValue"))),
    ):
        if value is not None:
            attrs[key] = value

    return attrs


def build_thermostat_device_info(thermostat: dict[str, Any], default_name: str) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, thermostat.get("deviceId") or default_name)},
        manufacturer="A.O. Smith",
        model=thermostat.get("productName") or "AJCC-I1",
        name=thermostat.get("roomName") or thermostat.get("productName") or default_name,
    )


def build_center_device_info(center: dict[str, Any]) -> DeviceInfo:
    device_id = center.get("deviceId") or "centercontroller"
    return DeviceInfo(
        identifiers={(DOMAIN, device_id)},
        manufacturer="A.O. Smith",
        model=center.get("productName") or "Center Controller",
        name=center.get("roomName") or "AO Smith Center Controller",
    )


def thermostat_slug(thermostat: dict[str, Any], fallback: str) -> str:
    raw_name = thermostat.get("roomName") or thermostat.get("productName") or fallback
    slug = slugify(raw_name)
    if slug:
        return slug
    return slugify(fallback) or fallback.lower()


def thermostat_object_id(
    thermostat: dict[str, Any],
    fallback: str,
    suffix: str | None = None,
) -> str:
    base = thermostat_slug(thermostat, fallback)
    if suffix:
        return f"{base}_{suffix}"
    return base


def center_object_id(suffix: str) -> str:
    return f"ao_smith_center_controller_{suffix}"
