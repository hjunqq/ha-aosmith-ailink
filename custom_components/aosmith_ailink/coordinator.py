from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import AOSmithApiError
from .const import DOMAIN, UPDATE_INTERVAL
from .entity_helpers import get_main_thermostat, system_mode_code


def plant_is_idle(data: dict[str, Any]) -> bool:
    """Require explicit idle telemetry before an HA seasonal changeover."""
    boilers = data.get("boilers", [])
    heat_pumps = data.get("heat_pumps", [])
    return (
        bool(boilers and heat_pumps)
        and all(boiler["warmStatus"] == 0 and boiler["fireStatus"] == 0 for boiler in boilers)
        and all(pump["compressorRealFrequency"] == 0 and pump["workStatus"] == 0 for pump in heat_pumps)
    )


class AOSmithDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    def __init__(self, hass: HomeAssistant, api, entry_id: str) -> None:
        super().__init__(
            hass,
            logger=hass.data[DOMAIN]["logger"],
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
        )
        self.api = api
        self.command_lock = asyncio.Lock()
        self.thermostat_ids: set[str] = set()
        self.boiler_count = 0
        self.stopped = False
        self.room_heat_modes: dict[str, int] = {}
        self._control_store = Store[dict[str, Any]](hass, 1, f"{DOMAIN}.{entry_id}.control")

    async def _async_setup(self) -> None:
        settings = await self._control_store.async_load() or {}
        self.stopped = settings.get("stopped", False)
        self.room_heat_modes = settings.get("room_heat_modes", {})

    async def async_save_controls(self) -> None:
        await self._control_store.async_save({
            "stopped": self.stopped,
            "room_heat_modes": self.room_heat_modes,
        })

    async def async_control_snapshot(self) -> dict[str, Any]:
        try:
            return await self.api.async_get_summary()
        except AOSmithApiError as exc:
            raise HomeAssistantError("Could not read current AO Smith state") from exc

    async def async_confirm(self, predicate: Callable[[dict[str, Any]], bool], message: str) -> None:
        for attempt in range(8):
            if attempt:
                await asyncio.sleep(2)
            if predicate(await self.async_control_snapshot()):
                return
        raise HomeAssistantError(message)

    def _all_rooms_off(self, data: dict[str, Any]) -> bool:
        rooms = {room["deviceId"]: room.get("powerStatus") for room in data["thermostats"]}
        return bool(self.thermostat_ids) and all(rooms.get(room) == 0 for room in self.thermostat_ids)

    async def _async_stop_rooms(self) -> None:
        self.stopped = True
        await self.async_save_controls()
        for device_id in sorted(self.thermostat_ids):
            try:
                await self.api.async_set_thermostat_power(device_id, False)
            except AOSmithApiError:
                self.logger.warning("Failed to switch off one AO Smith thermostat", exc_info=True)
        await self.async_confirm(self._all_rooms_off, "Could not confirm that all rooms stopped")

    async def async_stop_system(self) -> None:
        async with self.command_lock:
            try:
                await self._async_stop_rooms()
            finally:
                await self.async_request_refresh()

    async def async_change_system_mode(self, mode: int) -> None:
        async with self.command_lock:
            data = await self.async_control_snapshot()
            current = system_mode_code(data)
            main = get_main_thermostat(data)
            if current is None or not main.get("deviceId"):
                raise ServiceValidationError("Confirm the system mode on the AO Smith controller first")
            try:
                if current != mode:
                    for room in data["thermostats"]:
                        if room.get("workModelStatus") in (1, 3, 4):
                            self.room_heat_modes[room["deviceId"]] = room["workModelStatus"]
                    await self._async_stop_rooms()
                    await self.async_confirm(
                        lambda state: self._all_rooms_off(state)
                        and len(state["boilers"]) >= self.boiler_count
                        and plant_is_idle(state),
                        "The heat pump and boiler have not both reported idle. All room starts remain locked.",
                    )
                    await self.api.async_set_thermostat_mode(main["deviceId"], mode)
                    await self.async_confirm(
                        lambda state: system_mode_code(state) == mode and self._all_rooms_off(state),
                        "Could not confirm the new whole-home mode",
                    )
                elif self.stopped:
                    await self.async_confirm(self._all_rooms_off, "Could not confirm that all rooms stopped")
                self.stopped = False
                await self.async_save_controls()
            finally:
                await self.async_request_refresh()

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            data = await self.api.async_get_summary()
        except AOSmithApiError as exc:
            raise UpdateFailed(str(exc)) from exc
        self.thermostat_ids.update(room["deviceId"] for room in data["thermostats"] if room.get("deviceId"))
        self.boiler_count = max(self.boiler_count, len(data["boilers"]))
        return data
