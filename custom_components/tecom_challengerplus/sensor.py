"""Sensors for Tecom ChallengerPlus."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import Entity

from .const import DOMAIN

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    hub = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([TecomLastEventSensor(hub)], True)

class TecomLastEventSensor(Entity):
    _attr_has_entity_name = True
    _attr_name = "Last event"
    _attr_icon = "mdi:message-text"

    def __init__(self, hub) -> None:
        self._hub = hub
        self._attr_unique_id = f"{hub.entry.entry_id}_last_event"
        self._unsub = None

    async def async_added_to_hass(self) -> None:
        self._unsub = self._hub.add_listener(self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        if self._unsub:
            self._unsub()
            self._unsub = None

    @property
    def native_value(self):
        return self._hub.state.last_event
