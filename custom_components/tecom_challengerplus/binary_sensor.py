"""Binary sensors for inputs (zones)."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.binary_sensor import BinarySensorEntity

from .const import DOMAIN

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    hub = hass.data[DOMAIN][entry.entry_id]

    entities = []
    for i in range(1, hub.inputs_count + 1):
        entities.append(TecomInputBinarySensor(hub, i))

    async_add_entities(entities, True)

class TecomInputBinarySensor(BinarySensorEntity):
    _attr_has_entity_name = True
    _attr_icon = "mdi:ray-vertex"

    def __init__(self, hub, number: int) -> None:
        self._hub = hub
        self._number = number
        self._attr_name = f"Input {number}"
        self._attr_unique_id = f"{hub.entry.entry_id}_input_{number}"
        self._unsub = None

    async def async_added_to_hass(self) -> None:
        self._unsub = self._hub.add_listener(self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        if self._unsub:
            self._unsub()
            self._unsub = None

    @property
    def is_on(self):
        return self._hub.state.inputs.get(self._number)
