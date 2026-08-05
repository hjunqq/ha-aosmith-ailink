# AO Smith AiLink — Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![HA Version](https://img.shields.io/badge/Home%20Assistant-2024.1%2B-blue.svg)](https://www.home-assistant.io/)

A custom Home Assistant integration for **AO Smith (史密斯) AiLink** central HVAC / floor-heating systems. Controls and monitors your devices through the AiLink cloud.

---

## Supported Devices

| Product type | Description |
|---|---|
| `32` | AJCC-I1 Smart Thermostat (wall controller) |
| `37` | AiLink Center Controller |

Each thermostat in your AiLink family is discovered automatically.

---

## Features

| Entity type | What it exposes |
|---|---|
| `climate` | Power, HVAC mode, preset mode, target temperature, fan speed |
| `switch` | Per-mode controls and whole-home heating strategies |
| `fan` | Standalone fan speed control |
| `select` | Heating mode for center controller (ECO / Max / 单壁挂炉 / 单热泵) |
| `sensor` | Room temp, target temp, humidity, PM2.5, CO₂, TVOC, formaldehyde |
| `binary_sensor` | Power state, main thermostat flag |

### Shared HVAC safety

The heat pump, boiler, and cooling source are shared by every room. Room power,
target temperature, and fan speed remain independent, but the underlying operating
mode is synchronized across all thermostats. This prevents impossible combinations
such as one room cooling while another requests boiler or heat-pump heating.

Heating is selected through four mutually exclusive whole-home strategies:

- ECO dual source
- Max dual source
- Boiler only / floor heating
- Heat pump only / warm air

A generic turn-on preserves the active whole-home mode instead of forcing heating.
When switching to cooling, a stale target above 27°C is normalized to 26°C.

### HomeKit / Siri

Use a dedicated HomeKit Bridge containing only room thermostats, room fan controls,
and the four whole-home heating strategy switches. Do not expose the per-room mode
switches, `select` entities, or diagnostic sensors to HomeKit.

Always include the room, mode, and temperature in a cooling command. For heating,
select the whole-home source first and then set the required room thermostats to
heat. Avoid generic commands such as "turn on the air conditioner" because Siri may
match more than one accessory.

See [HomeKit and Siri setup](docs/HOMEKIT_SIRI.md) for the recommended entity filter,
accessory names, exact Chinese Siri phrases, fan-speed mapping, and safety rules.

---

## Installation

### HACS (recommended)

1. Open HACS → Integrations → **⋮** → Custom repositories
2. Add `https://github.com/hjunqq/ha-aosmith-ailink` with category **Integration**
3. Install **AO Smith AiLink** and restart Home Assistant

### Manual

```bash
cp -r custom_components/aosmith_ailink /config/custom_components/aosmith_ailink
```

Restart Home Assistant.

---

## Configuration

The integration authenticates using a **session token** extracted from the AiLink mobile app. You only need to capture this once — the integration handles token refresh automatically.

### Step 1 — Capture the session token

Use an HTTP proxy (e.g. mitmproxy, Charles, or HttpCanary) to intercept a request from the AiLink app after login, then collect the following fields from the response:

```json
{
  "auth_token": "Bearer eyJ...",
  "user_id": "123456",
  "family_id": "654321",
  "family_uk": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
}
```

> The `mobile` field is optional but can be included if present.

### Step 2 — Add the integration

1. Settings → Devices & Services → **Add Integration**
2. Search for **AO Smith AiLink**
3. Paste the JSON object (or the full response body) into the **Session JSON** field

---

## Entities Reference

### Climate (`climate.<room_name>`)

| Attribute | Values |
|---|---|
| `hvac_modes` | `off` `cool` `heat` `fan_only` `dry` |
| `preset_modes` | 制冷 风暖 通风 地暖 双能 除湿 等温除湿 |
| `fan_modes` | 自动 低 中 高 强劲 |
| `temperature_unit` | °C |
| `target_temperature_step` | 0.5 |

### Mode Switches (`switch.<room_name>_<mode>`)

Each switch corresponds to one preset mode. Turning a switch **on** powers the device and sets that mode. Turning it **off** powers off the device.

These switches should not be exposed directly to HomeKit / Siri.

### Sensors

Available sensors depend on hardware capabilities (air quality sensors require the optional air module):

`room_temperature` · `target_temperature` · `humidity` · `air_temperature` · `air_humidity` · `pm25` · `co2` · `tvoc` · `formaldehyde`

---

## Update Interval

Polls the AiLink cloud every **15 seconds**.

---

## Disclaimer

This integration is **not affiliated with or endorsed by A.O. Smith Corporation**. It uses a reverse-engineered API from the official AiLink Android application. Use at your own risk.

---

## License

[MIT](LICENSE)
