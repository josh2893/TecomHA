"""Config flow for Tecom ChallengerPlus integration."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.data_entry_flow import section

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
    CONF_AUTH_METHOD,
    CONF_ENCRYPTION_TYPE,
    ENC_AES_CBC_128,
    ENC_AES_CBC_256,
    ENC_TWOFISH_128,
    AUTH_METHOD_SECURITY_PASSWORD,
    AUTH_METHOD_CREDENTIALS,
    DEFAULT_AUTH_METHOD,
    DEFAULT_COMPUTER_PASSWORD,
    CONF_USER_NAME_ORDER,
    USER_NAME_ORDER_PANEL,
    USER_NAME_ORDER_GIVEN_FIRST,
    DEFAULT_USER_NAME_ORDER,
    CONF_ENCRYPTION_KEY,
    CONF_POLL_INTERVAL,
    CONF_INPUTS_COUNT,
    CONF_RELAYS_COUNT,
    CONF_DOORS_COUNT,
    CONF_DOOR_FIRST,
    CONF_DOOR_LAST,
    CONF_DGP_DOOR_RANGES,
    CONF_RAS_DOOR_RANGES,
    CONF_RELAY_RANGES,
    CONF_INPUT_RANGES,
    CONF_INPUT_MAPPING_MODE,
    INPUT_MAPPING_CTPLUS,
    INPUT_MAPPING_LEGACY_INVERTED,
    INPUT_MAPPING_STATUS_ONLY,
    CONF_SEND_ACKS,
    CONF_SEND_HEARTBEATS,
    CONF_HEARTBEAT_INTERVAL,
    CONF_MIN_SEND_INTERVAL_MS,
    CONF_PANEL_ACK_DELAY_MS,
    CONF_PANEL_FOLLOWUP_ACK_ENABLED,
    CONF_PANEL_FOLLOWUP_ACK_DELAY_MS,
    CONF_QUIET_MODE_ENABLED,
    CONF_PERIODIC_SESSION_REFRESH_ENABLED,
    CONF_PERIODIC_SESSION_REFRESH_HOURS,
    CONF_DOOR_STATUS_MODE,
    CONF_DOOR_STATUS_PER_CYCLE,
    CONF_RUNTIME_POLLING,
    CONF_RUNTIME_POLL_INPUTS,
    CONF_RUNTIME_POLL_AREAS,
    CONF_RUNTIME_POLL_RELAYS,
    CONF_RUNTIME_POLL_DOORS,
    CONF_RUNTIME_POLL_RAS,
    CONF_PANEL_EXPORT_PATH,
    CONF_PANEL_EXPORT_RENAME_AREAS,
    CONF_PANEL_EXPORT_RENAME_INPUTS,
    CONF_PANEL_EXPORT_RENAME_DOORS,
    CONF_PANEL_EXPORT_RENAME_RELAYS,
    CONF_PANEL_EXPORT_RENAME_RASES,
    DEFAULT_INPUT_MAPPING_MODE,
    DEFAULT_SEND_ACKS,
    DEFAULT_SEND_HEARTBEATS,
    DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
    DEFAULT_MIN_SEND_INTERVAL_MS,
    DEFAULT_PANEL_ACK_DELAY_MS,
    DEFAULT_PANEL_FOLLOWUP_ACK_ENABLED,
    DEFAULT_PANEL_FOLLOWUP_ACK_DELAY_MS,
    DEFAULT_QUIET_MODE_ENABLED,
    DEFAULT_PERIODIC_SESSION_REFRESH_ENABLED,
    DEFAULT_PERIODIC_SESSION_REFRESH_HOURS,
    DEFAULT_DOOR_STATUS_MODE,
    DEFAULT_DOOR_STATUS_PER_CYCLE,
    DEFAULT_RUNTIME_POLLING,
    DEFAULT_RUNTIME_POLL_INPUTS,
    DEFAULT_RUNTIME_POLL_AREAS,
    DEFAULT_RUNTIME_POLL_RELAYS,
    DEFAULT_RUNTIME_POLL_DOORS,
    DEFAULT_RUNTIME_POLL_RAS,
    DEFAULT_PANEL_EXPORT_PATH,
    DEFAULT_PANEL_EXPORT_RENAME_AREAS,
    DEFAULT_PANEL_EXPORT_RENAME_INPUTS,
    DEFAULT_PANEL_EXPORT_RENAME_DOORS,
    DEFAULT_PANEL_EXPORT_RENAME_RELAYS,
    DEFAULT_PANEL_EXPORT_RENAME_RASES,
    DEFAULT_DGP_DOOR_RANGES,
    DEFAULT_RAS_DOOR_RANGES,
    CONF_USER_SYNC_ENABLED,
    CONF_USER_SYNC_ON_STARTUP,
    CONF_USER_SYNC_PERIODIC_ENABLED,
    CONF_USER_SYNC_INTERVAL_HOURS,
    DEFAULT_USER_SYNC_ENABLED,
    DEFAULT_USER_SYNC_ON_STARTUP,
    DEFAULT_USER_SYNC_PERIODIC_ENABLED,
    DEFAULT_USER_SYNC_INTERVAL_HOURS,
    CONF_AREAS_COUNT,
)

MODE_SELECTOR = selector.SelectSelector(
    selector.SelectSelectorConfig(
        options=[
            {"label": "CTPlus / Management software", "value": MODE_CTPLUS},
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
            {"label": "AES CBC (128 bit)", "value": ENC_AES_CBC_128},
            {"label": "AES CBC (256 bit)", "value": ENC_AES_CBC_256},
            {"label": "TwoFish (128 bit)", "value": ENC_TWOFISH_128},
        ],
        mode=selector.SelectSelectorMode.DROPDOWN,
    )
)

USER_NAME_ORDER_SELECTOR = selector.SelectSelector(
    selector.SelectSelectorConfig(
        options=[
            {"label": "As stored on the panel", "value": USER_NAME_ORDER_PANEL},
            {"label": "Swap to given name first", "value": USER_NAME_ORDER_GIVEN_FIRST},
        ],
        mode=selector.SelectSelectorMode.DROPDOWN,
    )
)

AUTH_METHOD_SELECTOR = selector.SelectSelector(
    selector.SelectSelectorConfig(
        options=[
            {"label": "Security / computer password", "value": AUTH_METHOD_SECURITY_PASSWORD},
            {"label": "Path user name and password", "value": AUTH_METHOD_CREDENTIALS},
        ],
        mode=selector.SelectSelectorMode.DROPDOWN,
    )
)



DOOR_STATUS_MODE_SELECTOR = selector.SelectSelector(
    selector.SelectSelectorConfig(
        options=[
            {"label": "Round-robin (poll N doors per cycle)", "value": "round_robin"},
            {"label": "All doors each cycle (fastest, most traffic)", "value": "all_each_cycle"},
        ],
        mode=selector.SelectSelectorMode.DROPDOWN,
    )
)

INPUT_MAPPING_MODE_SELECTOR = selector.SelectSelector(
    selector.SelectSelectorConfig(
        options=[
            {"label": "CTPlus / official (Unsealed = on, Sealed = off)", "value": INPUT_MAPPING_CTPLUS},
            {"label": "Legacy 2.x inverted events", "value": INPUT_MAPPING_LEGACY_INVERTED},
            {"label": "Status word only (ignore live input event polarity)", "value": INPUT_MAPPING_STATUS_ONLY},
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
    d.setdefault(CONF_INPUT_RANGES, "")
    d.setdefault(CONF_INPUT_MAPPING_MODE, DEFAULT_INPUT_MAPPING_MODE)
    d.setdefault(CONF_SEND_ACKS, DEFAULT_SEND_ACKS)
    d.setdefault(CONF_SEND_HEARTBEATS, DEFAULT_SEND_HEARTBEATS)
    d.setdefault(CONF_HEARTBEAT_INTERVAL, DEFAULT_HEARTBEAT_INTERVAL_SECONDS)
    d.setdefault(CONF_MIN_SEND_INTERVAL_MS, DEFAULT_MIN_SEND_INTERVAL_MS)
    d.setdefault(CONF_PANEL_ACK_DELAY_MS, DEFAULT_PANEL_ACK_DELAY_MS)
    d.setdefault(CONF_PANEL_FOLLOWUP_ACK_ENABLED, DEFAULT_PANEL_FOLLOWUP_ACK_ENABLED)
    d.setdefault(CONF_PANEL_FOLLOWUP_ACK_DELAY_MS, DEFAULT_PANEL_FOLLOWUP_ACK_DELAY_MS)
    d.setdefault(CONF_QUIET_MODE_ENABLED, DEFAULT_QUIET_MODE_ENABLED)
    d.setdefault(CONF_PERIODIC_SESSION_REFRESH_ENABLED, DEFAULT_PERIODIC_SESSION_REFRESH_ENABLED)
    d.setdefault(CONF_PERIODIC_SESSION_REFRESH_HOURS, DEFAULT_PERIODIC_SESSION_REFRESH_HOURS)
    d.setdefault(CONF_DOOR_STATUS_MODE, DEFAULT_DOOR_STATUS_MODE)
    d.setdefault(CONF_DOOR_STATUS_PER_CYCLE, DEFAULT_DOOR_STATUS_PER_CYCLE)
    legacy_runtime = bool(d.get(CONF_RUNTIME_POLLING, False))
    d.setdefault(CONF_RUNTIME_POLL_INPUTS, legacy_runtime if legacy_runtime else DEFAULT_RUNTIME_POLL_INPUTS)
    d.setdefault(CONF_RUNTIME_POLL_AREAS, legacy_runtime if legacy_runtime else DEFAULT_RUNTIME_POLL_AREAS)
    d.setdefault(CONF_RUNTIME_POLL_RELAYS, legacy_runtime if legacy_runtime else DEFAULT_RUNTIME_POLL_RELAYS)
    d.setdefault(CONF_RUNTIME_POLL_DOORS, legacy_runtime if legacy_runtime else DEFAULT_RUNTIME_POLL_DOORS)
    d.setdefault(CONF_RUNTIME_POLL_RAS, legacy_runtime if legacy_runtime else DEFAULT_RUNTIME_POLL_RAS)
    d.setdefault(CONF_PANEL_EXPORT_PATH, DEFAULT_PANEL_EXPORT_PATH)
    d.setdefault(CONF_PANEL_EXPORT_RENAME_AREAS, DEFAULT_PANEL_EXPORT_RENAME_AREAS)
    d.setdefault(CONF_PANEL_EXPORT_RENAME_INPUTS, DEFAULT_PANEL_EXPORT_RENAME_INPUTS)
    d.setdefault(CONF_PANEL_EXPORT_RENAME_DOORS, DEFAULT_PANEL_EXPORT_RENAME_DOORS)
    d.setdefault(CONF_PANEL_EXPORT_RENAME_RELAYS, DEFAULT_PANEL_EXPORT_RENAME_RELAYS)
    d.setdefault(CONF_PANEL_EXPORT_RENAME_RASES, DEFAULT_PANEL_EXPORT_RENAME_RASES)
    d.setdefault(CONF_DGP_DOOR_RANGES, DEFAULT_DGP_DOOR_RANGES)
    d.setdefault(CONF_RAS_DOOR_RANGES, DEFAULT_RAS_DOOR_RANGES)
    d.setdefault(CONF_USER_SYNC_ENABLED, DEFAULT_USER_SYNC_ENABLED)
    d.setdefault(CONF_USER_SYNC_ON_STARTUP, DEFAULT_USER_SYNC_ON_STARTUP)
    d.setdefault(CONF_USER_SYNC_PERIODIC_ENABLED, DEFAULT_USER_SYNC_PERIODIC_ENABLED)
    d.setdefault(CONF_USER_SYNC_INTERVAL_HOURS, DEFAULT_USER_SYNC_INTERVAL_HOURS)
    return d


# Fields are grouped into collapsible sections so the form is scannable. Home
# Assistant returns section contents nested under the section key, but the hub
# reads a flat mapping and every existing config entry is stored flat, so
# flatten_sections() is applied before anything is saved.
SECTION_CONNECTION = "connection"
SECTION_AUTH = "authentication"
SECTION_OBJECTS = "objects"
SECTION_NAMING = "naming"
SECTION_POLLING = "polling"
SECTION_DOOR_POLLING = "door_polling"
SECTION_USER_SYNC = "user_sync"
SECTION_ADVANCED = "advanced"

SECTION_KEYS = (
    SECTION_CONNECTION, SECTION_AUTH, SECTION_OBJECTS, SECTION_NAMING,
    SECTION_POLLING, SECTION_DOOR_POLLING, SECTION_USER_SYNC, SECTION_ADVANCED,
)


def flatten_sections(user_input: dict) -> dict:
    """Collapse section dictionaries back into a flat mapping.

    Keeping stored options flat means the hub is unchanged and entries created
    before sections existed still load.
    """
    flat = {}
    for key, value in (user_input or {}).items():
        if key in SECTION_KEYS and isinstance(value, dict):
            flat.update(value)
        else:
            flat[key] = value
    return flat


def _num(minimum, maximum, step=1, unit=None):
    # unit_of_measurement is validated as a string, so it must be omitted
    # entirely rather than passed as None.
    config = {
        "min": minimum,
        "max": maximum,
        "step": step,
        "mode": selector.NumberSelectorMode.BOX,
    }
    if unit:
        config["unit_of_measurement"] = unit
    return selector.NumberSelector(selector.NumberSelectorConfig(**config))


def _text(password: bool = False):
    return selector.TextSelector(
        selector.TextSelectorConfig(
            type=selector.TextSelectorType.PASSWORD if password else selector.TextSelectorType.TEXT
        )
    )


def _schema(defaults: dict) -> vol.Schema:
    d = _normalized_defaults(defaults)
    g = d.get

    connection = {
        vol.Required(CONF_MODE, default=g(CONF_MODE, MODE_CTPLUS)): MODE_SELECTOR,
        vol.Required(CONF_HOST, default=g(CONF_HOST, "")): _text(),
        vol.Required(CONF_TRANSPORT, default=g(CONF_TRANSPORT, TRANSPORT_UDP)): TRANSPORT_SELECTOR,
        vol.Required(CONF_SEND_PORT, default=int(g(CONF_SEND_PORT, DEFAULT_SEND_PORT))): _num(1, 65535),
        vol.Required(CONF_LISTEN_PORT, default=int(g(CONF_LISTEN_PORT, DEFAULT_LISTEN_PORT))): _num(1, 65535),
        vol.Optional(CONF_BIND_HOST, default=g(CONF_BIND_HOST, "0.0.0.0")): _text(),
        vol.Optional(CONF_TCP_ROLE, default=g(CONF_TCP_ROLE, TCP_ROLE_CLIENT)): TCP_ROLE_SELECTOR,
    }

    authentication = {
        vol.Required(CONF_AUTH_METHOD, default=g(CONF_AUTH_METHOD, DEFAULT_AUTH_METHOD)): AUTH_METHOD_SELECTOR,
        vol.Optional(CONF_COMPUTER_PASSWORD, default=g(CONF_COMPUTER_PASSWORD, DEFAULT_COMPUTER_PASSWORD)): _text(password=True),
        vol.Optional(CONF_AUTH_USERNAME, default=g(CONF_AUTH_USERNAME, "")): _text(),
        vol.Optional(CONF_AUTH_PASSWORD, default=g(CONF_AUTH_PASSWORD, "")): _text(password=True),
        vol.Optional(CONF_ENCRYPTION_TYPE, default=g(CONF_ENCRYPTION_TYPE, ENC_NONE)): ENC_SELECTOR,
        vol.Optional(CONF_ENCRYPTION_KEY, default=g(CONF_ENCRYPTION_KEY, "")): _text(password=True),
    }

    objects = {
        vol.Required(CONF_INPUTS_COUNT, default=int(g(CONF_INPUTS_COUNT, 0))): _num(0, 4096),
        vol.Optional(CONF_INPUT_RANGES, default=str(g(CONF_INPUT_RANGES, ""))): _text(),
        vol.Required(CONF_AREAS_COUNT, default=int(g(CONF_AREAS_COUNT, 0))): _num(0, 256),
        vol.Optional(CONF_DGP_DOOR_RANGES, default=str(g(CONF_DGP_DOOR_RANGES, DEFAULT_DGP_DOOR_RANGES))): _text(),
        vol.Optional(CONF_RAS_DOOR_RANGES, default=str(g(CONF_RAS_DOOR_RANGES, DEFAULT_RAS_DOOR_RANGES))): _text(),
        vol.Optional(CONF_DOOR_FIRST, default=int(g(CONF_DOOR_FIRST, 1))): _num(0, 256),
        vol.Optional(CONF_DOOR_LAST, default=int(g(CONF_DOOR_LAST, 0))): _num(0, 256),
        vol.Optional(CONF_RELAY_RANGES, default=str(g(CONF_RELAY_RANGES, ""))): _text(),
        vol.Optional(CONF_RELAYS_COUNT, default=int(g(CONF_RELAYS_COUNT, 0))): _num(0, 1024),
    }

    naming = {
        vol.Optional(CONF_PANEL_EXPORT_PATH, default=str(g(CONF_PANEL_EXPORT_PATH, DEFAULT_PANEL_EXPORT_PATH))): _text(),
        vol.Optional(CONF_PANEL_EXPORT_RENAME_AREAS, default=bool(g(CONF_PANEL_EXPORT_RENAME_AREAS, DEFAULT_PANEL_EXPORT_RENAME_AREAS))): selector.BooleanSelector(),
        vol.Optional(CONF_PANEL_EXPORT_RENAME_INPUTS, default=bool(g(CONF_PANEL_EXPORT_RENAME_INPUTS, DEFAULT_PANEL_EXPORT_RENAME_INPUTS))): selector.BooleanSelector(),
        vol.Optional(CONF_PANEL_EXPORT_RENAME_DOORS, default=bool(g(CONF_PANEL_EXPORT_RENAME_DOORS, DEFAULT_PANEL_EXPORT_RENAME_DOORS))): selector.BooleanSelector(),
        vol.Optional(CONF_PANEL_EXPORT_RENAME_RELAYS, default=bool(g(CONF_PANEL_EXPORT_RENAME_RELAYS, DEFAULT_PANEL_EXPORT_RENAME_RELAYS))): selector.BooleanSelector(),
        vol.Optional(CONF_PANEL_EXPORT_RENAME_RASES, default=bool(g(CONF_PANEL_EXPORT_RENAME_RASES, DEFAULT_PANEL_EXPORT_RENAME_RASES))): selector.BooleanSelector(),
    }

    polling = {
        vol.Optional(CONF_POLL_INTERVAL, default=int(g(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL_SECONDS))): _num(1, 86400, unit="seconds"),
        vol.Optional(CONF_RUNTIME_POLL_INPUTS, default=bool(g(CONF_RUNTIME_POLL_INPUTS, False))): selector.BooleanSelector(),
        vol.Optional(CONF_RUNTIME_POLL_AREAS, default=bool(g(CONF_RUNTIME_POLL_AREAS, False))): selector.BooleanSelector(),
        vol.Optional(CONF_RUNTIME_POLL_RELAYS, default=bool(g(CONF_RUNTIME_POLL_RELAYS, False))): selector.BooleanSelector(),
        vol.Optional(CONF_RUNTIME_POLL_DOORS, default=bool(g(CONF_RUNTIME_POLL_DOORS, False))): selector.BooleanSelector(),
        vol.Optional(CONF_RUNTIME_POLL_RAS, default=bool(g(CONF_RUNTIME_POLL_RAS, False))): selector.BooleanSelector(),
    }

    door_polling = {
        vol.Optional(CONF_DOOR_STATUS_MODE, default=str(g(CONF_DOOR_STATUS_MODE, DEFAULT_DOOR_STATUS_MODE))): DOOR_STATUS_MODE_SELECTOR,
        vol.Optional(CONF_DOOR_STATUS_PER_CYCLE, default=int(g(CONF_DOOR_STATUS_PER_CYCLE, DEFAULT_DOOR_STATUS_PER_CYCLE))): _num(1, 64),
    }

    user_sync = {
        vol.Optional(CONF_USER_SYNC_ENABLED, default=bool(g(CONF_USER_SYNC_ENABLED, DEFAULT_USER_SYNC_ENABLED))): selector.BooleanSelector(),
        vol.Optional(CONF_USER_SYNC_ON_STARTUP, default=bool(g(CONF_USER_SYNC_ON_STARTUP, DEFAULT_USER_SYNC_ON_STARTUP))): selector.BooleanSelector(),
        vol.Optional(CONF_USER_SYNC_PERIODIC_ENABLED, default=bool(g(CONF_USER_SYNC_PERIODIC_ENABLED, DEFAULT_USER_SYNC_PERIODIC_ENABLED))): selector.BooleanSelector(),
        vol.Optional(CONF_USER_SYNC_INTERVAL_HOURS, default=int(g(CONF_USER_SYNC_INTERVAL_HOURS, DEFAULT_USER_SYNC_INTERVAL_HOURS))): _num(1, 720, unit="hours"),
        vol.Optional(CONF_USER_NAME_ORDER, default=str(g(CONF_USER_NAME_ORDER, DEFAULT_USER_NAME_ORDER))): USER_NAME_ORDER_SELECTOR,
    }

    advanced = {
        vol.Optional(CONF_SEND_ACKS, default=bool(g(CONF_SEND_ACKS, True))): selector.BooleanSelector(),
        vol.Optional(CONF_SEND_HEARTBEATS, default=bool(g(CONF_SEND_HEARTBEATS, True))): selector.BooleanSelector(),
        vol.Optional(CONF_HEARTBEAT_INTERVAL, default=int(g(CONF_HEARTBEAT_INTERVAL, DEFAULT_HEARTBEAT_INTERVAL_SECONDS))): _num(1, 3600, unit="seconds"),
        vol.Optional(CONF_MIN_SEND_INTERVAL_MS, default=int(g(CONF_MIN_SEND_INTERVAL_MS, DEFAULT_MIN_SEND_INTERVAL_MS))): _num(0, 5000, unit="ms"),
        vol.Optional(CONF_PANEL_ACK_DELAY_MS, default=float(g(CONF_PANEL_ACK_DELAY_MS, DEFAULT_PANEL_ACK_DELAY_MS))): _num(0, 1000, step=1, unit="ms"),
        vol.Optional(CONF_PERIODIC_SESSION_REFRESH_ENABLED, default=bool(g(CONF_PERIODIC_SESSION_REFRESH_ENABLED, DEFAULT_PERIODIC_SESSION_REFRESH_ENABLED))): selector.BooleanSelector(),
        vol.Optional(CONF_PERIODIC_SESSION_REFRESH_HOURS, default=float(g(CONF_PERIODIC_SESSION_REFRESH_HOURS, DEFAULT_PERIODIC_SESSION_REFRESH_HOURS))): _num(1, 168, step=1, unit="hours"),
        vol.Optional(CONF_QUIET_MODE_ENABLED, default=bool(g(CONF_QUIET_MODE_ENABLED, DEFAULT_QUIET_MODE_ENABLED))): selector.BooleanSelector(),
        vol.Optional(CONF_INPUT_MAPPING_MODE, default=str(g(CONF_INPUT_MAPPING_MODE, DEFAULT_INPUT_MAPPING_MODE))): INPUT_MAPPING_MODE_SELECTOR,
    }

    return vol.Schema({
        vol.Required(SECTION_CONNECTION): section(vol.Schema(connection), {"collapsed": False}),
        vol.Required(SECTION_AUTH): section(vol.Schema(authentication), {"collapsed": True}),
        vol.Required(SECTION_OBJECTS): section(vol.Schema(objects), {"collapsed": True}),
        vol.Required(SECTION_NAMING): section(vol.Schema(naming), {"collapsed": True}),
        vol.Required(SECTION_POLLING): section(vol.Schema(polling), {"collapsed": True}),
        vol.Required(SECTION_DOOR_POLLING): section(vol.Schema(door_polling), {"collapsed": True}),
        vol.Required(SECTION_USER_SYNC): section(vol.Schema(user_sync), {"collapsed": True}),
        vol.Required(SECTION_ADVANCED): section(vol.Schema(advanced), {"collapsed": True}),
    })


def _validate(cfg: dict) -> dict:
    """Check credential and key formats before they reach the panel.

    The panel does not report a bad credential -- it simply stops responding --
    so catching what we can here saves the user a silent failure.
    """
    errors: dict[str, str] = {}

    method = cfg.get(CONF_AUTH_METHOD, DEFAULT_AUTH_METHOD)
    if method == AUTH_METHOD_SECURITY_PASSWORD:
        pw = str(cfg.get(CONF_COMPUTER_PASSWORD, "") or "")
        if not pw.isdigit() or len(pw) != 10:
            errors[CONF_COMPUTER_PASSWORD] = "security_password_format"
    else:
        if not str(cfg.get(CONF_AUTH_USERNAME, "") or "").strip():
            errors[CONF_AUTH_USERNAME] = "required"
        if len(str(cfg.get(CONF_AUTH_USERNAME, "") or "")) > 30:
            errors[CONF_AUTH_USERNAME] = "too_long"
        if len(str(cfg.get(CONF_AUTH_PASSWORD, "") or "")) > 16:
            errors[CONF_AUTH_PASSWORD] = "too_long"

    enc = cfg.get(CONF_ENCRYPTION_TYPE, ENC_NONE)
    key = str(cfg.get(CONF_ENCRYPTION_KEY, "") or "")
    if enc != ENC_NONE:
        limit = 32 if enc == ENC_AES_CBC_256 else 16
        if not key:
            errors[CONF_ENCRYPTION_KEY] = "required"
        elif len(key) > limit:
            errors[CONF_ENCRYPTION_KEY] = "key_too_long"
        elif not key.isalnum():
            errors[CONF_ENCRYPTION_KEY] = "key_not_alphanumeric"
    return errors


class TecomChallengerPlusConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Tecom ChallengerPlus."""

    VERSION = 2

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            user_input = flatten_sections(user_input)
            errors = _validate(user_input)
            host = (user_input.get(CONF_HOST) or "").strip()
            if not host:
                errors[CONF_HOST] = "required"
            if not errors:
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
        errors = {}
        if user_input is not None:
            user_input = flatten_sections(user_input)
            errors = _validate(user_input)
            if not errors:
                # Updating options triggers the entry's update listener, which reloads.
                return self.async_create_entry(title="", data=user_input)

        defaults = {**self._entry.data, **self._entry.options}
        if user_input:
            defaults = {**defaults, **user_input}
        return self.async_show_form(step_id="init", data_schema=_schema(defaults), errors=errors)
