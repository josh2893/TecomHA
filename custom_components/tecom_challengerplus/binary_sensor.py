"""Binary sensors for inputs (zones) and door contacts."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    hub = hass.data[DOMAIN][entry.entry_id]

    entities = []
    for i in getattr(hub, 'input_ids', list(range(1, hub.inputs_count + 1))):
        entities.append(TecomInputBinarySensor(hub, i))


    # Door contacts (best-effort): ON when door status word is non-zero.
    for door in getattr(hub, 'door_ids', []):
        entities.append(TecomDoorContactBinarySensor(hub, door))

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
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._hub.entry.unique_id or self._hub.entry.entry_id)},
            name=self._hub.entry.title,
            manufacturer="Aritech / Tecom",
            model="ChallengerPlus",
        )

    @property
    def is_on(self):
        return self._hub.state.inputs.get(self._number)


class TecomDoorContactBinarySensor(BinarySensorEntity):
    """Door contact derived from CTPlus door status words."""

    _attr_has_entity_name = True
    _attr_device_class = "door"
    _attr_icon = "mdi:door"

    def __init__(self, hub, door: int) -> None:
        self._hub = hub
        self._door = door
        self._attr_name = f"Door {door} Contact"
        self._attr_unique_id = f"{hub.entry.entry_id}_door_contact_{door}"
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
    def is_on(self):
        w = getattr(self._hub.state, "door_words", {}).get(self._door)
        if w is None:
            return None
        return w != 0
