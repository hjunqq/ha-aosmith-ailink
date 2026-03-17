from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import AOSmithApiError, AOSmithDirectClient, parse_session_payload
from .const import (
    CONF_AUTH_TOKEN,
    CONF_FAMILY_ID,
    CONF_FAMILY_UK,
    CONF_MOBILE,
    CONF_SESSION_PAYLOAD,
    CONF_USER_ID,
    DOMAIN,
)


class AOSmithAiLinkConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 2

    async def async_step_user(self, user_input: dict | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                session_data = parse_session_payload(user_input[CONF_SESSION_PAYLOAD])
            except AOSmithApiError as exc:
                errors["base"] = str(exc)
            except Exception:
                errors["base"] = "invalid_session_payload"
            else:
                session = async_get_clientsession(self.hass)
                api = AOSmithDirectClient(session, session_data)
                try:
                    await api.async_validate()
                except AOSmithApiError as exc:
                    errors["base"] = str(exc)
                except Exception:
                    errors["base"] = "cannot_connect"
                else:
                    await self.async_set_unique_id(f"direct:{session_data.user_id}:{session_data.family_id}")
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(
                        title="AO Smith AiLink",
                        data={
                            CONF_AUTH_TOKEN: session_data.auth_token,
                            CONF_USER_ID: session_data.user_id,
                            CONF_FAMILY_ID: session_data.family_id,
                            CONF_FAMILY_UK: session_data.family_uk,
                            CONF_MOBILE: session_data.mobile,
                        },
                    )

        schema = vol.Schema(
            {
                vol.Required(CONF_SESSION_PAYLOAD): str,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)
