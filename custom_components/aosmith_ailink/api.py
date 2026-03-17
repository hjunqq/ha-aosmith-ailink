from __future__ import annotations

import base64
import hashlib
import json
import random
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from aiohttp import ClientError, ClientResponseError, ClientSession

from .const import (
    AILINK_BASE_URL,
    CONF_AUTH_TOKEN,
    CONF_FAMILY_ID,
    CONF_FAMILY_UK,
    CONF_MOBILE,
    CONF_USER_ID,
    HEADER_VERSION,
    HEATING_MODE_LABELS,
    THERMOSTAT_MODE_LABELS,
)

SK = "ng957stzh4zy3dts"
AOSERCET_KEY = "AILink_2021#"
ANDROID_TAG = "01"


class AOSmithApiError(Exception):
    """Raised when the integration cannot talk to AO Smith backend/cloud."""


@dataclass
class AOSmithSessionData:
    auth_token: str
    user_id: str
    family_id: str
    family_uk: str
    mobile: str = ""


def build_client(session: ClientSession, entry_data: dict[str, Any]):
    return AOSmithDirectClient(
        session,
        AOSmithSessionData(
            auth_token=entry_data[CONF_AUTH_TOKEN],
            user_id=entry_data[CONF_USER_ID],
            family_id=entry_data[CONF_FAMILY_ID],
            family_uk=entry_data[CONF_FAMILY_UK],
            mobile=entry_data.get(CONF_MOBILE, ""),
        ),
    )


def parse_session_payload(raw: str) -> AOSmithSessionData:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise AOSmithApiError("invalid_session_payload") from exc

    session_obj: dict[str, Any] | None = None
    if isinstance(payload, dict) and _looks_like_session(payload):
        session_obj = payload
    elif isinstance(payload, dict):
        for value in payload.values():
            if isinstance(value, dict) and _looks_like_session(value):
                session_obj = value
                break

    if not session_obj:
        raise AOSmithApiError("invalid_session_payload")

    auth_token = str(session_obj.get("auth_token", "")).strip()
    if auth_token and not auth_token.startswith("Bearer "):
        auth_token = f"Bearer {auth_token}"

    session_data = AOSmithSessionData(
        auth_token=auth_token,
        user_id=str(session_obj.get("user_id", "")).strip(),
        family_id=str(session_obj.get("family_id", "")).strip(),
        family_uk=str(session_obj.get("family_uk", "")).strip(),
        mobile=str(session_obj.get("mobile", "")).strip(),
    )
    if not all([session_data.auth_token, session_data.user_id, session_data.family_id, session_data.family_uk]):
        raise AOSmithApiError("invalid_session_payload")
    return session_data


def _looks_like_session(value: dict[str, Any]) -> bool:
    return all(key in value for key in ("auth_token", "user_id", "family_id", "family_uk"))


def _md5(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def _generate_trace_id(user_id: str = "") -> str:
    ts = str(int(time.time() * 1000))
    rand = str(int(random.random() * 10000))
    return f"{ts}-{rand}-{user_id or ''}-{ANDROID_TAG}"


def _compute_encode(params: dict[str, Any]) -> str:
    concat = "".join(str(params[key]) for key in sorted(params.keys()))
    return _md5(concat + AOSERCET_KEY)


def _compute_anti_replay(params: dict[str, Any]) -> dict[str, str]:
    timestamp = str(int(time.time() * 1000))
    nonce = str(uuid.uuid4())

    if params:
        concat = ""
        for key in params.keys():
            concat = str(params[key]) + concat
        md5data = _md5(concat)
    else:
        md5data = _md5(timestamp)

    sign = _md5(md5data + timestamp + nonce + SK)
    return {"timestamp": timestamp, "nonce": nonce, "md5data": md5data, "sign": sign}


def _decode_jwt_exp(auth_header: str) -> int | None:
    token = auth_header.strip()
    if token.startswith("Bearer "):
        token = token[7:]
    parts = token.split(".")
    if len(parts) < 2:
        return None
    payload = parts[1] + "=" * ((4 - len(parts[1]) % 4) % 4)
    try:
        raw = base64.urlsafe_b64decode(payload.encode("utf-8"))
        obj = json.loads(raw.decode("utf-8", "replace"))
    except Exception:
        return None
    exp = obj.get("exp")
    return exp if isinstance(exp, int) else None


def _parse_status_info(status_info_raw: Any) -> dict[str, Any]:
    if not isinstance(status_info_raw, str) or not status_info_raw:
        return {}
    try:
        obj = json.loads(status_info_raw)
    except Exception:
        return {}
    return obj if isinstance(obj, dict) else {}


def _find_post_output(status_info: dict[str, Any]) -> dict[str, Any]:
    for item in status_info.get("events", []):
        if isinstance(item, dict) and item.get("identifier") == "post" and isinstance(item.get("outputData"), dict):
            return item["outputData"]
    return {}


def _build_summary(homepage: dict[str, Any]) -> dict[str, Any]:
    info = homepage.get("info", {}) if isinstance(homepage, dict) else {}
    devs = info.get("devInfoItemInfoList", []) if isinstance(info, dict) else []

    thermostats: list[dict[str, Any]] = []
    main_thermostat: dict[str, Any] | None = None
    center: dict[str, Any] | None = None

    for item in devs if isinstance(devs, list) else []:
        si = _parse_status_info(item.get("statusInfo", ""))
        profile = si.get("profile", {}) if isinstance(si, dict) else {}
        post = _find_post_output(si)
        ptype = str(profile.get("productType", ""))
        if ptype == "32":
            thermostat = {
                "deviceId": item.get("deviceId"),
                "roomName": item.get("roomName"),
                "productName": item.get("productName"),
                "mainWenKongFlag": item.get("mainWenKongFlag"),
                "powerStatus": post.get("powerStatus"),
                "workModelStatus": post.get("workModelStatus"),
                "workModelLabel": THERMOSTAT_MODE_LABELS.get(post.get("workModelStatus"))
                if isinstance(post.get("workModelStatus"), int)
                else None,
                "setTempStatus": post.get("setTempStatus"),
                "realTempStatus": post.get("realTempStatus"),
                "windModelStatus": post.get("windModelStatus"),
                "humCurValue": post.get("humCurValue"),
                "humSetValue": post.get("humSetValue"),
                "deHumSetValue": post.get("deHumSetValue"),
                "airDrumTempValue": post.get("airDrumTempValue"),
                "airDrumHumValue": post.get("airDrumHumValue"),
                "airDrumPM2Value": post.get("airDrumPM2Value"),
                "airDrumCO2Value": post.get("airDrumCO2Value"),
                "airDrumTVOCValue": post.get("airDrumTVOCValue"),
                "TVOCValue": post.get("TVOCValue"),
                "formaldehydeValue": post.get("formaldehydeValue"),
                "airBoardVersion": post.get("airBoardVersion") or profile.get("airBoardVersion"),
                "sensorBoardVersion": post.get("sensorBoardVersion") or profile.get("sensorBoardVersion"),
                "supDoubleEnergy": post.get("supDoubleEnergy"),
                "supCold": post.get("supCold"),
                "supWarm": post.get("supWarm"),
                "supWind": post.get("supWind"),
                "supFloorWarm": post.get("supFloorWarm"),
                "supFloorCold": post.get("supFloorCold"),
                "supfunction1": post.get("supfunction1"),
                "supfunction2": post.get("supfunction2"),
                "withNewAir": post.get("withNewAir"),
                "withAir": post.get("withAir"),
                "withAirNut": post.get("withAirNut"),
                "newAirDeviceStatus": post.get("newAirDeviceStatus"),
                "supSleep": post.get("supSleep"),
                "errorCode": post.get("errorCode"),
            }
            thermostats.append(thermostat)
            if item.get("mainWenKongFlag") == 1:
                main_thermostat = thermostat
        elif ptype == "37":
            center = {
                "deviceId": item.get("deviceId"),
                "roomName": item.get("roomName"),
                "productName": item.get("productName"),
                "HeatingMode": post.get("HeatingMode"),
                "HeatingModeLabel": HEATING_MODE_LABELS.get(post.get("HeatingMode"))
                if isinstance(post.get("HeatingMode"), int)
                else None,
                "specialMode": post.get("specialMode"),
                "ecoWarm": post.get("ecoWarm"),
                "speedWarm": post.get("speedWarm"),
                "powerStatus": post.get("powerStatus"),
                "deviceStatus": post.get("deviceStatus"),
            }

    return {
        "status": 200,
        "centercontroller": center,
        "mainThermostat": main_thermostat,
        "thermostats": sorted(
            thermostats,
            key=lambda x: (0 if x.get("mainWenKongFlag") == 1 else 1, x.get("roomName") or ""),
        ),
    }


class AOSmithDirectClient:
    def __init__(self, session: ClientSession, session_data: AOSmithSessionData) -> None:
        self._session = session
        self._session_data = session_data

    async def async_validate(self) -> dict[str, Any]:
        return await self.async_get_summary()

    async def async_get_summary(self) -> dict[str, Any]:
        homepage = await self._call_upstream_json(
            "appDevice/getHomepageV2",
            {
                "userId": self._session_data.user_id,
                "familyId": self._session_data.family_id,
                "homePageVersion": "3",
            },
        )
        return _build_summary(homepage)

    async def async_set_thermostat_power(self, device_id: str, on: bool) -> None:
        await self._invoke_method(
            device_id=device_id,
            product_type="32",
            device_type="AJCC-I1",
            identifier="SetTCU",
            input_data={"OnOff": "1" if on else "0"},
        )

    async def async_set_thermostat_mode(self, device_id: str, mode: int) -> None:
        input_data: dict[str, Any] = {"CommandValue": str(mode)}
        if mode == 5:
            input_data["Temperature"] = "56"
        await self._invoke_method(
            device_id=device_id,
            product_type="32",
            device_type="AJCC-I1",
            identifier="SetThermostatModel",
            input_data=input_data,
        )

    async def async_set_thermostat_setpoint(self, device_id: str, temp_c: float) -> None:
        command_value = int(round(temp_c * 2))
        await self._invoke_method(
            device_id=device_id,
            product_type="32",
            device_type="AJCC-I1",
            identifier="SetRoomTemperature",
            input_data={"CommandValue": str(command_value)},
        )

    async def async_set_thermostat_wind_rate(self, device_id: str, rate: int) -> None:
        await self._invoke_method(
            device_id=device_id,
            product_type="32",
            device_type="AJCC-I1",
            identifier="SetWindRate",
            input_data={"CommandValue": str(rate)},
        )

    async def async_set_heating_mode(self, device_id: str, mode: int) -> None:
        await self._invoke_method(
            device_id=device_id,
            product_type="37",
            device_type="37",
            identifier="HeatingModeSet",
            input_data={"CommandValue": str(mode)},
        )

    async def _invoke_method(
        self,
        *,
        device_id: str,
        product_type: str,
        device_type: str,
        identifier: str,
        input_data: dict[str, Any],
    ) -> None:
        payload = {
            "userId": self._session_data.user_id,
            "familyId": self._session_data.family_id,
            "deviceId": device_id,
            "currUserMobile": self._session_data.mobile or "",
            "appSource": "0",
            "commandSource": "1",
            "invokeTime": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "payLoad": json.dumps(
                {
                    "profile": {
                        "productType": str(product_type),
                        "deviceType": str(device_type),
                        "deviceId": device_id,
                    },
                    "service": {"identifier": identifier, "inputData": input_data},
                },
                ensure_ascii=False,
            ),
        }
        await self._call_upstream_json("device/invokeMethod", payload)

    async def _call_upstream_json(self, endpoint: str, body_json: dict[str, Any]) -> dict[str, Any]:
        await self._ensure_fresh_token()
        data, status = await self._upstream_request(endpoint, body_json)
        if status in (401, 403):
            await self._refresh_token()
            data, status = await self._upstream_request(endpoint, body_json)

        if status in (401, 403):
            raise AOSmithApiError("invalid_auth")
        if status >= 400:
            raise AOSmithApiError("cannot_connect")
        return data

    async def _upstream_request(self, endpoint: str, body_json: dict[str, Any]) -> tuple[dict[str, Any], int]:
        relay_body = dict(body_json)
        relay_body["encode"] = _compute_encode(body_json)
        relay_body = dict(sorted(relay_body.items()))

        anti_replay = _compute_anti_replay(body_json)
        headers = {
            "traceId": _generate_trace_id(self._session_data.user_id),
            "Authorization": self._session_data.auth_token,
            "Content-Type": "application/json;charset=UTF-8",
            "timestamp": anti_replay["timestamp"],
            "nonce": anti_replay["nonce"],
            "md5data": anti_replay["md5data"],
            "sign": anti_replay["sign"],
            "userId": self._session_data.user_id,
            "familyId": self._session_data.family_id,
            "version": HEADER_VERSION,
            "source": "Android",
            "familyUk": self._session_data.family_uk,
        }

        try:
            async with self._session.post(
                f"{AILINK_BASE_URL}/{endpoint.lstrip('/')}",
                json=relay_body,
                headers=headers,
                timeout=30,
            ) as resp:
                auth_header = resp.headers.get("Authorization", "")
                if auth_header.startswith("Bearer "):
                    self._session_data.auth_token = auth_header
                data = await resp.json(content_type=None)
                return data if isinstance(data, dict) else {}, resp.status
        except ClientResponseError as exc:
            raise AOSmithApiError("cannot_connect") from exc
        except (ClientError, TimeoutError, ValueError) as exc:
            raise AOSmithApiError("cannot_connect") from exc

    async def _ensure_fresh_token(self) -> None:
        exp = _decode_jwt_exp(self._session_data.auth_token)
        if not exp:
            return
        now = int(datetime.now(tz=timezone.utc).timestamp())
        if exp - now > 90:
            return
        await self._refresh_token()

    async def _refresh_token(self) -> None:
        body_json = {"token": self._session_data.auth_token}
        data, status = await self._upstream_request("api/getLastToken", body_json)
        if status != 200:
            return
        token = (data.get("info") or {}).get("token")
        if isinstance(token, str) and token:
            self._session_data.auth_token = token if token.startswith("Bearer ") else f"Bearer {token}"
