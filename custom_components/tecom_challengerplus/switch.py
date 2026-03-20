"""Switch entities for relays."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.switch import SwitchEntity

from .const import DOMAIN
from .exceptions import TecomNotSupported
from homeassistant.helpers.entity import DeviceInfo

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    hub = hass.data[DOMAIN][entry.entry_id]
    entities = [TecomRelaySwitch(hub, i) for i in getattr(hub, 'relay_ids', [])]
    async_add_entities(entities, True)

class TecomRelaySwitch(SwitchEntity):
    _attr_has_entity_name = True
    _attr_icon = "mdi:electric-switch"

    def __init__(self, hub, relay: int) -> None:
        self._hub = hub
        self._relay = relay
        self._attr_name = hub.entity_name("relay", relay, f"Relay {relay}")
        self._attr_unique_id = f"{hub.entry.entry_id}_relay_{relay}"
        self._unsub = None

    async def async_added_to_hass(self) -> None:
        self._unsub = self._hub.add_listener(self.async_write_ha_state)

    async def async_will_remove_from_hass(self) -> None:
        if self._unsub:
            self._unsub()
            self._unsub = None

    @property
    def is_on(self):
        return self._hub.state.relays.get(self._relay)

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._hub.entry.unique_id or self._hub.entry.entry_id)},
            name=self._hub.entry.title,
            manufacturer="Aritech / Tecom",
            model="ChallengerPlus",
        )

    @property
    def extra_state_attributes(self):
        state = self._hub.state.relays.get(self._relay)
        return {
            "relay_state": state,
            "last_event": getattr(self._hub.state, "last_event", None),
        }

    async def async_turn_on(self, **kwargs):
        try:
            await self._hub.async_set_relay(self._relay, True)
        except TecomNotSupported as e:
            raise

    async def async_turn_off(self, **kwargs):
        await self._hub.async_set_relay(self._relay, False)
