"""Tecom ChallengerPlus integration."""

from __future__ import annotations

import asyncio
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN

PENDING_RELOAD_TASK = "pending_reload_task"

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[str] = ["sensor", "binary_sensor", "switch", "lock", "alarm_control_panel"]


def _iter_hubs(hass: HomeAssistant):
    from .hub import TecomHub  # local import to keep config flow loadable

    for value in hass.data.get(DOMAIN, {}).values():
        if isinstance(value, TecomHub):
            yield value


def _resolve_service_hubs(hass: HomeAssistant, entry_id: str | None):
    hubs = [hub for hub in _iter_hubs(hass) if entry_id is None or hub.entry.entry_id == entry_id]
    if entry_id and not hubs:
        raise ServiceValidationError(f"No loaded Tecom ChallengerPlus entry matches entry_id '{entry_id}'")
    if not entry_id and len(hubs) > 1:
        raise ServiceValidationError("Multiple Tecom ChallengerPlus entries are loaded; provide entry_id")
    if not hubs:
        raise ServiceValidationError("No Tecom ChallengerPlus hubs are loaded")
    return hubs


def _ensure_services_registered(hass: HomeAssistant) -> None:
    async def _async_send_raw_hex(call):
        entry_id = call.data.get("entry_id")
        hex_str = (call.data.get("hex") or "").replace(" ", "")
        if not hex_str:
            raise ServiceValidationError("hex is required")
        try:
            payload = bytes.fromhex(hex_str)
        except ValueError as e:
            raise ServiceValidationError(f"Invalid hex: {e}") from e
        for hub in _resolve_service_hubs(hass, entry_id):
            await hub.async_send_bytes(payload)

    async def _async_dump_debug(call):
        entry_id = call.data.get("entry_id")
        hubs = _resolve_service_hubs(hass, entry_id) if entry_id else list(_iter_hubs(hass))
        if not hubs:
            raise ServiceValidationError("No Tecom ChallengerPlus hubs are loaded")
        for hub in hubs:
            await hub.async_dump_debug()

    async def _async_request_full_sync(call):
        entry_id = call.data.get("entry_id")
        for hub in _resolve_service_hubs(hass, entry_id):
            await hub.async_request_full_sync()

    async def _async_reset_comms_path_event_buffer(call):
        entry_id = call.data.get("entry_id")
        for hub in _resolve_service_hubs(hass, entry_id):
            await hub.async_reset_comms_path_event_buffer()

    async def _async_retrieve_events(call):
        entry_id = call.data.get("entry_id")
        for hub in _resolve_service_hubs(hass, entry_id):
            await hub.async_retrieve_events()

    async def _async_reinitialize_session(call):
        entry_id = call.data.get("entry_id")
        for hub in _resolve_service_hubs(hass, entry_id):
            await hub.async_reinitialize_session()

    async def _async_test_event(call):
        hass.bus.async_fire(f"{DOMAIN}_test", {"note": call.data.get("note")})

    if not hass.services.has_service(DOMAIN, "send_raw_hex"):
        hass.services.async_register(DOMAIN, "send_raw_hex", _async_send_raw_hex)
    if not hass.services.has_service(DOMAIN, "dump_debug"):
        hass.services.async_register(DOMAIN, "dump_debug", _async_dump_debug)
    if not hass.services.has_service(DOMAIN, "request_full_sync"):
        hass.services.async_register(DOMAIN, "request_full_sync", _async_request_full_sync)
    if not hass.services.has_service(DOMAIN, "reset_comms_path_event_buffer"):
        hass.services.async_register(DOMAIN, "reset_comms_path_event_buffer", _async_reset_comms_path_event_buffer)
    if not hass.services.has_service(DOMAIN, "retrieve_events"):
        hass.services.async_register(DOMAIN, "retrieve_events", _async_retrieve_events)
    if not hass.services.has_service(DOMAIN, "reinitialize_session"):
        hass.services.async_register(DOMAIN, "reinitialize_session", _async_reinitialize_session)
    if not hass.services.has_service(DOMAIN, "test_event"):
        hass.services.async_register(DOMAIN, "test_event", _async_test_event)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Tecom ChallengerPlus from a config entry."""
    from .hub import TecomHub  # local import to keep config flow loadable
    from .const import CONF_PANEL_EXPORT_PATH, DEFAULT_PANEL_EXPORT_PATH
    from .panel_export import load_panel_export_names

    cfg = {**entry.data, **entry.options}
    panel_export_path = str(cfg.get(CONF_PANEL_EXPORT_PATH, DEFAULT_PANEL_EXPORT_PATH) or '').strip()
    panel_export_names = await hass.async_add_executor_job(load_panel_export_names, panel_export_path)

    hub = TecomHub(hass, entry, panel_export_names=panel_export_names)
    await hub.async_start()

    _ensure_services_registered(hass)

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = hub

    # Register device
    device_reg = dr.async_get(hass)
    device_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.unique_id or entry.entry_id)},
        name=entry.title or "Tecom ChallengerPlus",
        manufacturer="Aritech / Tecom",
        model="ChallengerPlus",
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Reload platforms on options change
    entry.async_on_unload(entry.add_update_listener(_update_listener))
    return True


async def _update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    # Avoid rapid double-reloads causing UDP bind collisions.
    pending = hass.data.setdefault(DOMAIN, {}).get(PENDING_RELOAD_TASK)
    if pending and not pending.done():
        pending.cancel()

    async def _delayed_reload() -> None:
        await asyncio.sleep(0.5)
        await hass.config_entries.async_reload(entry.entry_id)

    task = hass.async_create_task(_delayed_reload())
    hass.data[DOMAIN][PENDING_RELOAD_TASK] = task


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    hub = hass.data[DOMAIN].pop(entry.entry_id)
    await hub.async_stop()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
