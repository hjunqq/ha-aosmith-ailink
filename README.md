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
| `climate` | Room power, whole-home HVAC mode, target temperature, fan speed |
| `switch` | Fail-safe whole-home power-off switch |
| `fan` | Standalone fan speed control |
| `select` | Whole-home cooling/heating mode and four heating strategies |
| `sensor` | Room data and center-controller heating strategy status |
| `binary_sensor` | Power state, main thermostat flag |

### Shared HVAC safety

The original AiLink H5 uses a two-level model. The main thermostat first selects the
whole-home system mode: cooling or heating. While heating, the center controller
selects ECO, Max, boiler only, or heat pump only.

The integration follows that model directly. Only the main thermostat receives the
whole-home `SetThermostatModel(0/1)` command. `HeatingModeSet(0..3)` is a separate
HA-only select that can safely preset the next heating strategy without changing the
whole-home mode or powering on a room. Room power, target temperature, and fan speed
remain independent.

A generic turn-on is allowed only while the system is already cooling. When
switching to cooling, a stale target above 27°C is normalized to 26°C.

### HomeKit / Siri

Use a dedicated HomeKit Bridge containing room thermostats, room fan controls, and
the fail-safe whole-home power switch. The master switch can turn every room off,
but its turn-on action is deliberately disabled. Do not expose per-room mode
switches, `select` entities, or diagnostic sensors to HomeKit.

Always include the room, mode, and temperature in a command. Setting a room to heat
changes the whole-home system mode through the main thermostat but keeps the current
heating strategy. Siri cannot change that strategy because the strategy select is
not exposed to HomeKit. Avoid generic commands such as "turn on the air conditioner".

Generic thermostat turn-on and fan-speed commands are blocked while the whole-home
system is heating. Heating therefore requires an explicit HEAT command.

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
| `hvac_modes` | `off` `cool` `heat` |
| `fan_modes` | 自动 低 中 高 强劲 |
| `temperature_unit` | °C |
| `target_temperature_step` | 0.5 |

The active `cool` / `heat` state is derived from the main thermostat's whole-home
mode. Setting any room to `cool` or `heat` changes that shared mode first and then
turns on only the requested room.

### Selects

| Entity | Purpose |
|---|---|
| `select.ao_smith_system_mode` | Whole-home cooling or heating |
| `select.ao_smith_center_controller_heating_mode` | ECO, Max, boiler only, or heat pump only; can be preset while cooling |

Changing either select does not turn on a room. The fail-safe
`switch.ao_smith_whole_home_power` can turn all room thermostats off, but its
turn-on action intentionally does nothing.

### Sensors

Available sensors depend on hardware capabilities (air quality sensors require the optional air module):

`room_temperature` · `target_temperature` · `mode` · `fan_speed` · `humidity` ·
`air_temperature` · `air_humidity` · `pm25` · `co2` · `tvoc` · `formaldehyde`

The per-room `mode` sensor is the controller's raw diagnostic value and may retain
an old value while that room is off. Use the whole-home mode select for control and
status.

---

## Update Interval

Polls the AiLink cloud every **15 seconds**.

---

## Disclaimer

This integration is **not affiliated with or endorsed by A.O. Smith Corporation**. It uses a reverse-engineered API from the official AiLink Android application. Use at your own risk.

---

## License

[MIT](LICENSE)
