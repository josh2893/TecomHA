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
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .access import DOOR_EVENT_TYPES, EVENT_ACCESS_ACTIVITY, describe_access


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
    """Fires on access grants, confirmed denials and door exceptions."""

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

    @callback
    def _handle_panel_event(self, event) -> None:
        data = event.data or {}
        code = data.get("code")
        if (data.get("entry_id") != self._hub.entry.entry_id
                or code not in DOOR_EVENT_TYPES or data.get("object") != self._door):
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
                "denial_reason": data.get("denial_reason"),
            },
        )
        self.async_write_ha_state()
        # HA filters Activity by entity/device BEFORE calling logbook.py. These
        # identifiers must therefore be present in the recorded bus event.
        message, icon = describe_access(data)
        state = self.hass.states.get(self.entity_id)
        activity = {
            "entry_id": self._hub.entry.entry_id,
            "entity_id": self.entity_id,
            "name": state.name if state else self.name,
            "message": message,
            "icon": icon,
            "code": code,
            "event_type": DOOR_EVENT_TYPES[code],
            "door": self._door,
        }
        registry_entry = er.async_get(self.hass).async_get(self.entity_id)
        if registry_entry and registry_entry.device_id:
            activity["device_id"] = registry_entry.device_id
        self.hass.bus.async_fire(EVENT_ACCESS_ACTIVITY, activity, context=event.context)
