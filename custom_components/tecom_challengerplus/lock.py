"""Lock entities for doors."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.lock import LockEntity

from .const import DOMAIN
from .exceptions import TecomNotSupported

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    hub = hass.data[DOMAIN][entry.entry_id]
    entities = [TecomDoorLock(hub, i) for i in getattr(hub, 'door_ids', [])]
    async_add_entities(entities, True)

class TecomDoorLock(LockEntity):
    _attr_has_entity_name = True
    _attr_icon = "mdi:door"

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
    def is_locked(self):
        # doors dict can store "locked"/"unlocked"/"unknown"
        return self._hub.state.doors.get(self._door) == "locked"

    async def async_lock(self, **kwargs):
        if self._hub.mode != "ctplus":
            raise TecomNotSupported("Door control requires CTPlus/management mode")
        # ChallengerPlus doors are typically momentary unlock/open. "Lock" isn't a defined action here.
        raise TecomNotSupported("Door lock action is not supported; use unlock/open")

    async def async_unlock(self, **kwargs):
        await self._hub.async_unlock_door(self._door)
