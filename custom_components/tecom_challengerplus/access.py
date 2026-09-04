"""Door Activity types and presentation, independent of live name caches."""
from __future__ import annotations

from .const import DOMAIN
from . import ctplus_protocol as proto

EVENT_ACCESS_ACTIVITY = f"{DOMAIN}_access_activity"
DOOR_EVENT_TYPES = {
    proto.EVENT_ACCESS_GRANTED: "access_granted",
    proto.EVENT_ACCESS_GRANTED_EGRESS: "access_granted_egress",
    proto.EVENT_ACCESS_DENIED_CARD: "access_denied",
    proto.EVENT_ACCESS_DENIED_VOID: "access_denied_void",
    0xA7: "door_forced",
    0xA9: "door_open_too_long",
}


def describe_access(data: dict) -> tuple[str, str]:
    """Describe this event, never attributing it to a previous successful user."""
    code = data.get("code")
    user = data.get("user")
    who = (data.get("user_name") or f"User {user}") if user else None
    if code == proto.EVENT_ACCESS_GRANTED:
        return f"Access granted - {who or 'System'}", "mdi:card-account-details-outline"
    if code == proto.EVENT_ACCESS_GRANTED_EGRESS:
        action = "Access granted (exit button)"
        return (f"{action} - {who}" if who else action), "mdi:exit-run"
    if code == proto.EVENT_ACCESS_DENIED_CARD:
        return "Access denied - Card rejected", "mdi:card-account-details-outline"
    if code == proto.EVENT_ACCESS_DENIED_VOID:
        return (f"Access denied - {who} (void)" if who else "Access denied - Void"), "mdi:card-account-details-outline"
    if code == 0xA7:
        return "Door forced", "mdi:door-open"
    if code == 0xA9:
        return "Door open too long", "mdi:timer-alert-outline"
    raise ValueError(f"Unsupported door Activity code: {code}")
