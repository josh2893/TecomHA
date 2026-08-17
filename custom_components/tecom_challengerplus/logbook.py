"""Logbook descriptions for panel events.

Home Assistant's Activity feed renders an event entity's `event_type` and
nothing more, so a card swipe shows only "access_granted" even though the user
is sitting in the entity's attributes. A logbook platform lets the integration
write its own Activity lines, so who badged appears where people actually look.
"""

from __future__ import annotations

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN

try:  # pragma: no cover - constant names are stable, import guarded for safety
    from homeassistant.components.logbook import (
        LOGBOOK_ENTRY_ENTITY_ID,
        LOGBOOK_ENTRY_ICON,
        LOGBOOK_ENTRY_MESSAGE,
        LOGBOOK_ENTRY_NAME,
    )
except ImportError:  # pragma: no cover
    LOGBOOK_ENTRY_ENTITY_ID = "entity_id"
    LOGBOOK_ENTRY_ICON = "icon"
    LOGBOOK_ENTRY_MESSAGE = "message"
    LOGBOOK_ENTRY_NAME = "name"

# Codes worth a dedicated Activity line, with how to phrase them.
DESCRIBED_CODES = {
    0x92: ("Access granted", "mdi:card-account-details-outline"),
    0x9D: ("Access granted (exit button)", "mdi:exit-run"),
    0xA7: ("Door forced", "mdi:door-open"),
    0xA9: ("Door open too long", "mdi:timer-alert-outline"),
}


@callback
def async_describe_events(hass: HomeAssistant, async_describe_event) -> None:
    """Register Activity descriptions for panel access events."""

    @callback
    def async_describe_access_event(event):
        data = event.data or {}
        code = data.get("code")
        described = DESCRIBED_CODES.get(code)
        if not described:
            return None

        action, icon = described
        door = data.get("object")

        # Name the user where one was presented. A missing user on an access
        # grant means the panel opened the door itself rather than a credential
        # being read. Door exceptions (forced, open too long) have no user by
        # nature, so they get no attribution at all.
        user = data.get("user")
        user_name = data.get("user_name")
        if code == 0x92:
            if user_name:
                who = user_name
            elif user:
                who = f"user {user}"
            else:
                who = "system"
        elif code == 0x9D and (user_name or user):
            who = user_name or f"user {user}"
        else:
            who = None

        message = action if who is None else f"{action} - {who}"

        entry = {
            LOGBOOK_ENTRY_NAME: _door_name(hass, door),
            LOGBOOK_ENTRY_MESSAGE: message,
            LOGBOOK_ENTRY_ICON: icon,
        }
        entity_id = _door_event_entity_id(hass, door)
        if entity_id:
            entry[LOGBOOK_ENTRY_ENTITY_ID] = entity_id
        return entry

    async_describe_event(
        DOMAIN, f"{DOMAIN}_ctplus_event", async_describe_access_event
    )


def _door_event_entity_id(hass: HomeAssistant, door) -> str | None:
    """Resolve the access event entity for a door, so the line is filterable."""
    if door is None:
        return None
    registry = er.async_get(hass)
    for entry_id in hass.data.get(DOMAIN, {}):
        entity_id = registry.async_get_entity_id(
            "event", DOMAIN, f"{entry_id}_door_{door}_access"
        )
        if entity_id:
            return entity_id
    return None


def _door_name(hass: HomeAssistant, door) -> str:
    """Friendly door name, falling back to the number."""
    for hub in hass.data.get(DOMAIN, {}).values():
        namer = getattr(hub, "entity_name", None)
        if callable(namer) and door is not None:
            try:
                return namer("door", door, f"Door {door}")
            except Exception:  # pragma: no cover - naming is best effort
                break
    return f"Door {door}" if door is not None else "Door"
