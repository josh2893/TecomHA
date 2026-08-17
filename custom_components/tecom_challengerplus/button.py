"""Buttons for on-demand panel actions."""

from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    hub = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([TecomSyncUsersButton(hub)])


class TecomSyncUsersButton(ButtonEntity):
    """Fetch the panel's user list on demand.

    Available regardless of whether scheduled syncing is enabled, so a one-off
    refresh after adding a user does not require turning on automatic syncing.
    """

    _attr_has_entity_name = True
    _attr_name = "Sync Users Now"
    _attr_icon = "mdi:account-sync"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, hub) -> None:
        self._hub = hub
        self._attr_unique_id = f"{hub.entry.entry_id}_sync_users"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._hub.entry.unique_id or self._hub.entry.entry_id)},
            name=self._hub.entry.title,
            manufacturer="Aritech / Tecom",
            model="ChallengerPlus",
        )

    @property
    def available(self) -> bool:
        return getattr(self._hub, "mode", "") == "ctplus"

    @property
    def extra_state_attributes(self):
        names = getattr(self._hub.state, "user_names", {}) or {}
        return {
            "known_users": len(names),
            "user_sync_enabled": getattr(self._hub, "user_sync_enabled", False),
        }

    async def async_press(self) -> None:
        count = await self._hub.async_download_users()
        _LOGGER.info("Sync Users Now: %d users known", count)
