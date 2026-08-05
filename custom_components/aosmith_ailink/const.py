from datetime import timedelta

from homeassistant.const import Platform

DOMAIN = "aosmith_ailink"

CONF_SESSION_PAYLOAD = "session_payload"
CONF_AUTH_TOKEN = "auth_token"
CONF_USER_ID = "user_id"
CONF_FAMILY_ID = "family_id"
CONF_FAMILY_UK = "family_uk"
CONF_MOBILE = "mobile"

AILINK_BASE_URL = "https://ailink-api.hotwater.com.cn/AiLinkService"
HEADER_VERSION = "V1.0.1"
UPDATE_INTERVAL = timedelta(seconds=15)

PLATFORMS = [
    Platform.CLIMATE,
    Platform.FAN,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.SWITCH,
]

HEATING_MODE_LABELS = {
    0: "ECO模式",
    1: "Max模式",
    2: "单壁挂炉采暖",
    3: "单热泵空调采暖",
}

SYSTEM_MODE_LABELS = {
    0: "制冷",
    1: "采暖",
}

THERMOSTAT_MODE_LABELS = {
    0: "制冷",
    1: "风暖",
    2: "通风",
    3: "地暖",
    4: "双能",
    5: "除湿",
    6: "等温除湿",
}

HEAT_CAPABLE_MODES = {1, 3, 4}

WIND_RATE_LABELS = {
    0: "自动",
    1: "低",
    2: "中",
    3: "高",
    4: "强劲",
}

THERMOSTAT_SUPPORT_LABELS = {
    "supCold": "制冷",
    "supWarm": "风暖",
    "supWind": "通风",
    "supFloorWarm": "地暖",
    "supDoubleEnergy": "双能",
    "supfunction1": "除湿",
    "supfunction2": "等温除湿",
    "supFloorCold": "地板制冷",
}

WIND_LABEL_TO_RATE = {label: rate for rate, label in WIND_RATE_LABELS.items()}
HEATING_LABEL_TO_MODE = {label: mode for mode, label in HEATING_MODE_LABELS.items()}
SYSTEM_LABEL_TO_MODE = {label: mode for mode, label in SYSTEM_MODE_LABELS.items()}
