"""Tecom ChallengerPlus integration."""

from __future__ import annotations

import asyncio
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN
from .hub import TecomHub

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[str] = ["sensor", "binary_sensor", "switch", "lock", "alarm_control_panel"]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Tecom ChallengerPlus from a config entry."""
    hub = TecomHub(hass, entry)
    await hub.async_start()

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
    await hass.config_entries.async_reload(entry.entry_id)

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    hub: TecomHub = hass.data[DOMAIN].pop(entry.entry_id)
    await hub.async_stop()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
