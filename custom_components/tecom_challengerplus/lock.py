"""Door control entities.

Door contact, secure state, and lock/release state are not the same thing on
Challenger/CTPlus. In 3.0.1 we only expose the lock entity from explicit
lock/secure events (or the last confirmed value) instead of guessing from the
door contact/status word.
"""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.components.lock import LockEntity, LockEntityFeature

from .const import DOMAIN
from .exceptions import TecomNotSupported


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    hub = hass.data[DOMAIN][entry.entry_id]
    entities: list[LockEntity] = []
    # DGP doors (17+)
    entities += [TecomDoorLock(hub, i) for i in getattr(hub, "dgp_door_ids", [])]
    # RAS doors (1-16)
    entities += [TecomRasDoorLock(hub, i) for i in getattr(hub, "ras_door_ids", [])]
    async_add_entities(entities, True)


class TecomDoorLock(LockEntity, RestoreEntity):
    _attr_has_entity_name = True
    _attr_icon = "mdi:door"
    _attr_supported_features = LockEntityFeature.OPEN

    def __init__(self, hub, door: int) -> None:
        self._hub = hub
        self._door = door
        self._attr_name = hub.entity_name("door", door, f"Door {door}")
        self._attr_unique_id = f"{hub.entry.entry_id}_door_{door}"
        self._unsub = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._unsub = self._hub.add_listener(self.async_write_ha_state)
        last_state = await self.async_get_last_state()
        if last_state is None:
            return
        if self._door not in getattr(self._hub.state, "door_lock", {}):
            attrs = dict(last_state.attributes or {})
            lock_state = attrs.get("lock_state")
            secure_state = attrs.get("secure_state")
            if lock_state in ("locked", "auto_locked", "unlocked", "auto_unlocked"):
                self._hub.state.door_lock[self._door] = lock_state
            elif secure_state in ("secured", "unsecured"):
                self._hub.state.door_secure[self._door] = secure_state

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
    def is_locked(self):
        # Only trust explicit lock/secure semantics. The door status word is still useful
        # for the reed/contact entity, but it proved unreliable for deciding whether a
        # door is actually released. When CTPlus-style secure/lock events have not yet
        # been seen for this door, keep the lock state unknown instead of guessing.
        lock_state = getattr(self._hub.state, "door_lock", {}).get(self._door)
        if lock_state in ("locked", "auto_locked"):
            return True
        if lock_state in ("unlocked", "auto_unlocked"):
            return False

        secure_state = getattr(self._hub.state, "door_secure", {}).get(self._door)
        if secure_state == "secured":
            return True
        if secure_state == "unsecured":
            return False

        return None

    @property
    def extra_state_attributes(self):
        w = getattr(self._hub.state, "door_words", {}).get(self._door)
        attrs = {
            "door_state": getattr(self._hub.state, "doors", {}).get(self._door),
            "lock_state": getattr(self._hub.state, "door_lock", {}).get(self._door),
            "secure_state": getattr(self._hub.state, "door_secure", {}).get(self._door),
            "lock_derived_from": self._lock_state_source(),
            "last_event": getattr(self._hub.state, "last_event", None),
        }
        if w is not None:
            attrs.update({
                "raw_status": w,
                "raw_status_hex": f"0x{w:04X}",
                "raw_status_binary": f"{w:016b}",
                "bit_0x0002_set": bool(w & 0x0002),
                "bit_0x0010_set": bool(w & 0x0010),
                "bit_0x0080_set": bool(w & 0x0080),
            })
        return attrs

    async def async_lock(self, **kwargs):
        return

    async def async_unlock(self, **kwargs):
        if getattr(self._hub, "mode", "") != "ctplus":
            raise TecomNotSupported("Door control requires CTPlus/management mode")
        await self._hub.async_unlock_door(self._door)

    async def async_open(self, **kwargs):
        await self.async_unlock(**kwargs)

    def _lock_state_source(self) -> str:
        lock_state = getattr(self._hub.state, "door_lock", {}).get(self._door)
        if lock_state in ("locked", "auto_locked", "unlocked", "auto_unlocked"):
            return f"door_lock:{lock_state}"
        secure_state = getattr(self._hub.state, "door_secure", {}).get(self._door)
        if secure_state in ("secured", "unsecured"):
            return f"door_secure:{secure_state}"
        return "explicit_event_pending"


class TecomRasDoorLock(LockEntity):
    """Represents a RAS/Keypad/Simple Door Controller as a door entity.

    Control is intentionally disabled (no OPEN) because RAS devices may be keypads.
    We still surface a door-like state plus raw status for diagnostics.
    """
    _attr_has_entity_name = True
    _attr_icon = "mdi:door"
    _attr_supported_features = 0

    def __init__(self, hub, ras: int) -> None:
        self._hub = hub
        self._ras = ras
        self._attr_name = hub.entity_name("ras", ras, f"RAS Door {ras}")
        self._attr_unique_id = f"{hub.entry.entry_id}_ras_{ras}"
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
    def is_locked(self):
        st = getattr(self._hub.state, "ras_status", {}).get(self._ras)
        if st is None:
            return None
        # Best-effort: treat normal 'idle' (often 0x11) as closed/secure.
        return st == 0x11

    @property
    def extra_state_attributes(self):
        st = getattr(self._hub.state, "ras_status", {}).get(self._ras)
        attrs = {"last_event": getattr(self._hub.state, "last_event", None)}
        if st is None:
            return attrs
        attrs.update({"raw_status": st, "raw_status_hex": f"0x{st:02X}"})
        return attrs

