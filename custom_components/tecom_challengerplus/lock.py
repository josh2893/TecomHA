"""Door control entities.

ChallengerPlus "doors" are typically controlled via a momentary OPEN/UNLOCK action.
The panel does not necessarily support a distinct "lock" action, so we expose:
  - unlock/open -> sends the door open command
  - lock -> no-op (prevents noisy errors if the UI calls lock)
"""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.components.lock import LockEntity, LockEntityFeature

from .const import DOMAIN
from .exceptions import TecomNotSupported


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    hub = hass.data[DOMAIN][entry.entry_id]
    entities = [TecomDoorLock(hub, i) for i in getattr(hub, "door_ids", [])]
    async_add_entities(entities, True)


class TecomDoorLock(LockEntity):
    _attr_has_entity_name = True
    _attr_icon = "mdi:door"
    _attr_supported_features = LockEntityFeature.OPEN

    def __init__(self, hub, door: int) -> None:
        self._hub = hub
        self._door = door
        self._attr_name = f"Door {door}"
        self._attr_unique_id = f"{hub.entry.entry_id}_door_{door}"
        self._unsub = None

    async def async_added_to_hass(self) -> None:
        self._unsub = self._hub.add_listener(self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        if self._unsub:
            self._unsub()
            self._unsub = None

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._hub.entry.unique_id or self._hub.entry.entry_id)},
            name=self._hub.entry.title,
            manufacturer="Aritech / Tecom",
            model="ChallengerPlus",
        )

    @property
    def is_locked(self):
        # Door "locked" state isn't reliably known with current protocol mapping; return None/False-ish.
        return self._hub.state.doors.get(self._door) == "locked"

    async def async_lock(self, **kwargs):
        # No-op: avoid noisy errors if UI calls lock. If a distinct lock action is later mapped,
        # we can implement it here.
        return

    async def async_unlock(self, **kwargs):
        if self._hub.mode != "ctplus":
            raise TecomNotSupported("Door control requires CTPlus/management mode")
        await self._hub.async_unlock_door(self._door)

    async def async_open(self, **kwargs):
        # Treat OPEN the same as UNLOCK (momentary open)
        await self.async_unlock(**kwargs)
