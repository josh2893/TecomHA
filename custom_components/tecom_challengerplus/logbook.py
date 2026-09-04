"""Activity descriptions from snapshots recorded by the door event entity."""
from __future__ import annotations

from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN
from .access import EVENT_ACCESS_ACTIVITY


@callback
def async_describe_events(hass: HomeAssistant, async_describe_event) -> None:
    """Register only displayable access events, including historical snapshots."""

    @callback
    def async_describe_access_event(event):
        data = event.data or {}
        # No live hub/name lookup: renaming a user or unloading a panel must not
        # alter earlier Activity. HA expects a dictionary for every event on a
        # registered stream; the general CTPlus stream also has unrelated events.
        return {
            "name": data.get("name", "Door"),
            "message": data.get("message", "Access event"),
            "entity_id": data.get("entity_id"),
            "icon": data.get("icon", "mdi:card-account-details-outline"),
        }

    async_describe_event(DOMAIN, EVENT_ACCESS_ACTIVITY, async_describe_access_event)
