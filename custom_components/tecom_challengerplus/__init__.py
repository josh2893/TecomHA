"""Tecom ChallengerPlus integration."""

from __future__ import annotations

import asyncio
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN

PENDING_RELOAD_TASK = "pending_reload_task"

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[str] = ["sensor", "binary_sensor", "switch", "lock", "alarm_control_panel"]


def _build_dump_debug_service(hass: HomeAssistant):
    """Create the dump_debug service handler bound to this hass instance."""

    async def _async_dump_debug_service(call):
        """Write a debug dump for all loaded Tecom hubs."""
        from .hub import TecomHub  # local import to keep config flow loadable

        hubs = []
        for value in hass.data.get(DOMAIN, {}).values():
            if isinstance(value, TecomHub):
                hubs.append(value)
        if not hubs:
            _LOGGER.warning("dump_debug called but no Tecom hubs are loaded")
            return
        for hub in hubs:
            await hub.async_dump_debug()

    return _async_dump_debug_service


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

    if not hass.services.has_service(DOMAIN, "dump_debug"):
        hass.services.async_register(DOMAIN, "dump_debug", _build_dump_debug_service(hass))

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
