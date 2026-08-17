"""Door access events.

Access activity previously reached the Home Assistant event bus but had nowhere
to surface: the logbook/activity feed shows entity state changes, and a card
swipe changes no entity.  An EventEntity gives each door a home for these
momentary occurrences so they appear in Activity alongside lock and contact
changes.
"""

from __future__ import annotations

from homeassistant.components.event import EventEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN

# Event codes surfaced per door, mapped to the event_type reported to HA.
# The two access codes match ctplus_protocol.ACCESS_EVENT_CODES, which are the
# only codes carrying a user number.
DOOR_EVENT_TYPES = {
    0x92: "access_granted",
    0x9D: "access_granted_egress",
    0xA7: "door_forced",
    0xA9: "door_open_too_long",
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    hub = hass.data[DOMAIN][entry.entry_id]
    entities = []
    for door in list(getattr(hub, "dgp_door_ids", [])) + list(getattr(hub, "ras_door_ids", [])):
        entities.append(TecomDoorAccessEvent(hub, door))
    if entities:
        async_add_entities(entities)


class TecomDoorAccessEvent(EventEntity):
    """Fires on access grants and door exceptions for one door."""

    _attr_has_entity_name = True
    _attr_event_types = list(DOOR_EVENT_TYPES.values())
    _attr_icon = "mdi:card-account-details-outline"

    def __init__(self, hub, door: int) -> None:
        self._hub = hub
        self._door = door
        base = hub.entity_name("door", door, f"Door {door}")
        self._attr_name = f"{base} Access"
        self._attr_unique_id = f"{hub.entry.entry_id}_door_{door}_access"
        self._unsub = None

    async def async_added_to_hass(self) -> None:
        self._unsub = self.hass.bus.async_listen(
            f"{DOMAIN}_ctplus_event", self._handle_panel_event
        )

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

    async def _handle_panel_event(self, event) -> None:
        data = event.data or {}
        code = data.get("code")
        if code not in DOOR_EVENT_TYPES or data.get("object") != self._door:
            return
        user = data.get("user")
        self._trigger_event(
            DOOR_EVENT_TYPES[code],
            {
                # user is None when the panel itself opened the door, e.g. a
                # macro-driven unlock rather than a presented credential.
                "user": user,
                "user_name": data.get("user_name"),
                # The most recent access that DID carry a credential. A card read
                # is often followed by a panel-initiated access reporting no user,
                # so this preserves who actually badged.
                "last_user": data.get("last_user"),
                "last_user_name": data.get("last_user_name"),
                "door": self._door,
                "message": data.get("message"),
            },
        )
        self.async_write_ha_state()
