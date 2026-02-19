"""Config flow for Tecom ChallengerPlus integration."""

from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.helpers import selector

from .const import (
    DOMAIN,
    DEFAULT_SEND_PORT,
    DEFAULT_LISTEN_PORT,
    DEFAULT_POLL_INTERVAL_SECONDS,
    MODE_CTPLUS,
    MODE_PRINTER,
    TRANSPORT_TCP,
    TRANSPORT_UDP,
    TCP_ROLE_CLIENT,
    TCP_ROLE_SERVER,
    ENC_NONE,
    ENC_TWOFISH,
    ENC_AES128,
    ENC_AES256,
    CONF_MODE,
    CONF_HOST,
    CONF_TRANSPORT,
    CONF_SEND_PORT,
    CONF_LISTEN_PORT,
    CONF_BIND_HOST,
    CONF_TCP_ROLE,
    CONF_ACCOUNT_CODE,
    CONF_COMPUTER_PASSWORD,
    CONF_AUTH_USERNAME,
    CONF_AUTH_PASSWORD,
    CONF_ENCRYPTION_TYPE,
    CONF_ENCRYPTION_KEY,
    CONF_POLL_INTERVAL,
    CONF_INPUTS_COUNT,
    CONF_RELAYS_COUNT,
    CONF_DOORS_COUNT,
    CONF_DOOR_FIRST,
    CONF_DOOR_LAST,
    CONF_RELAY_RANGES,
    CONF_AREAS_COUNT,
)

MODE_SELECTOR = selector.SelectSelector(
    selector.SelectSelectorConfig(
        options=[
            {"label": "CTPlus / Management software (binary protocol – experimental)", "value": MODE_CTPLUS},
            {"label": "Printer / Computer Event Driven (text events only)", "value": MODE_PRINTER},
        ],
        mode=selector.SelectSelectorMode.DROPDOWN,
    )
)

TRANSPORT_SELECTOR = selector.SelectSelector(
    selector.SelectSelectorConfig(
        options=[
            {"label": "UDP/IP", "value": TRANSPORT_UDP},
            {"label": "TCP/IP", "value": TRANSPORT_TCP},
        ],
        mode=selector.SelectSelectorMode.DROPDOWN,
    )
)

TCP_ROLE_SELECTOR = selector.SelectSelector(
    selector.SelectSelectorConfig(
        options=[
            {"label": "Client (Home Assistant connects to panel)", "value": TCP_ROLE_CLIENT},
            {"label": "Server (panel connects to Home Assistant)", "value": TCP_ROLE_SERVER},
        ],
        mode=selector.SelectSelectorMode.DROPDOWN,
    )
)

ENC_SELECTOR = selector.SelectSelector(
    selector.SelectSelectorConfig(
        options=[
            {"label": "None", "value": ENC_NONE},
            {"label": "Twofish (management software)", "value": ENC_TWOFISH},
            {"label": "AES-128 (IP receiver)", "value": ENC_AES128},
            {"label": "AES-256 (IP receiver)", "value": ENC_AES256},
        ],
        mode=selector.SelectSelectorMode.DROPDOWN,
    )
)

def _normalized_defaults(defaults: dict) -> dict:
    """Normalize defaults for backward compatibility."""
    d = dict(defaults or {})
    # Door range: if not set, derive from legacy doors_count.
    if CONF_DOOR_FIRST not in d:
        d[CONF_DOOR_FIRST] = 1
    if int(d.get(CONF_DOOR_LAST, 0) or 0) == 0:
        try:
            dc = int(d.get(CONF_DOORS_COUNT, 0) or 0)
        except (TypeError, ValueError):
            dc = 0
        if dc > 0:
            d[CONF_DOOR_LAST] = int(d[CONF_DOOR_FIRST]) + dc - 1
        else:
            d.setdefault(CONF_DOOR_LAST, 0)
    d.setdefault(CONF_RELAY_RANGES, "")
    return d


def _schema(defaults: dict) -> vol.Schema:
    defaults = _normalized_defaults(defaults)
    return vol.Schema(
        {
            vol.Required(CONF_MODE, default=defaults.get(CONF_MODE, MODE_CTPLUS)): MODE_SELECTOR,
            vol.Required(CONF_HOST, default=defaults.get(CONF_HOST, "")): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
            ),
            vol.Required(CONF_TRANSPORT, default=defaults.get(CONF_TRANSPORT, TRANSPORT_UDP)): TRANSPORT_SELECTOR,
            vol.Optional(CONF_TCP_ROLE, default=defaults.get(CONF_TCP_ROLE, TCP_ROLE_CLIENT)): TCP_ROLE_SELECTOR,
            vol.Required(CONF_SEND_PORT, default=int(defaults.get(CONF_SEND_PORT, DEFAULT_SEND_PORT))): selector.NumberSelector(
                selector.NumberSelectorConfig(min=1, max=65535, mode=selector.NumberSelectorMode.BOX)
            ),
            vol.Required(CONF_LISTEN_PORT, default=int(defaults.get(CONF_LISTEN_PORT, DEFAULT_LISTEN_PORT))): selector.NumberSelector(
                selector.NumberSelectorConfig(min=1, max=65535, mode=selector.NumberSelectorMode.BOX)
            ),
            vol.Optional(CONF_BIND_HOST, default=defaults.get(CONF_BIND_HOST, "0.0.0.0")): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
            ),
            vol.Optional(CONF_ACCOUNT_CODE, default=defaults.get(CONF_ACCOUNT_CODE, "1")): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
            ),
            vol.Optional(CONF_COMPUTER_PASSWORD, default=defaults.get(CONF_COMPUTER_PASSWORD, "0000000000")): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
            ),
            vol.Optional(CONF_AUTH_USERNAME, default=defaults.get(CONF_AUTH_USERNAME, "")): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
            ),
            vol.Optional(CONF_AUTH_PASSWORD, default=defaults.get(CONF_AUTH_PASSWORD, "")): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
            ),
            vol.Optional(CONF_ENCRYPTION_TYPE, default=defaults.get(CONF_ENCRYPTION_TYPE, ENC_NONE)): ENC_SELECTOR,
            vol.Optional(CONF_ENCRYPTION_KEY, default=defaults.get(CONF_ENCRYPTION_KEY, "")): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
            ),
            vol.Required(CONF_POLL_INTERVAL, default=int(defaults.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL_SECONDS))): selector.NumberSelector(
                selector.NumberSelectorConfig(min=1, max=3600, mode=selector.NumberSelectorMode.BOX)
            ),

            # Inputs / Areas are still simple contiguous ranges (1..N).
            vol.Required(CONF_INPUTS_COUNT, default=int(defaults.get(CONF_INPUTS_COUNT, 0))): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, max=4096, mode=selector.NumberSelectorMode.BOX)
            ),
            vol.Required(CONF_AREAS_COUNT, default=int(defaults.get(CONF_AREAS_COUNT, 0))): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, max=1024, mode=selector.NumberSelectorMode.BOX)
            ),

            # Doors: configure by first/last number (inclusive). Set last=0 to disable.
            vol.Required(CONF_DOOR_FIRST, default=int(defaults.get(CONF_DOOR_FIRST, 1))): selector.NumberSelector(
                selector.NumberSelectorConfig(min=1, max=2048, mode=selector.NumberSelectorMode.BOX)
            ),
            vol.Required(CONF_DOOR_LAST, default=int(defaults.get(CONF_DOOR_LAST, 0))): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, max=2048, mode=selector.NumberSelectorMode.BOX)
            ),

            # Relays: either contiguous (1..relays_count) or ranges via relay_ranges (overrides).
            vol.Required(CONF_RELAYS_COUNT, default=int(defaults.get(CONF_RELAYS_COUNT, 0))): selector.NumberSelector(
                selector.NumberSelectorConfig(min=0, max=2048, mode=selector.NumberSelectorMode.BOX)
            ),
            vol.Optional(CONF_RELAY_RANGES, default=str(defaults.get(CONF_RELAY_RANGES, ""))): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.TEXT)
            ),
        }
    )


class TecomChallengerPlusConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Tecom ChallengerPlus."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            host = (user_input.get(CONF_HOST) or "").strip()
            if not host:
                errors[CONF_HOST] = "required"
            else:
                # Make a deterministic unique_id based on host+ports
                uid = f"{host}:{user_input.get(CONF_TRANSPORT)}:{user_input.get(CONF_SEND_PORT)}"
                await self.async_set_unique_id(uid)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=f"ChallengerPlus ({host})", data=user_input)

        return self.async_show_form(step_id="user", data_schema=_schema({}), errors=errors)

    @staticmethod
    def async_get_options_flow(config_entry):
        return TecomChallengerPlusOptionsFlow(config_entry)

class TecomChallengerPlusOptionsFlow(config_entries.OptionsFlow):
    """Options flow."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._entry = config_entry

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        defaults = {**self._entry.data, **self._entry.options}
        return self.async_show_form(step_id="init", data_schema=_schema(defaults), errors={})
