"""Binary sensors for inputs (zones) and door contacts."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
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
        self._attr_name = hub.entity_name("input", number, f"Input {number}")
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
        raw = getattr(self._hub.state, "input_words", {}).get(self._number)
        if raw is not None:
            decoded_state, _derived_from = self._hub.decode_input_status(raw)
            return decoded_state
        return self._hub.state.inputs.get(self._number)

    @property
    def extra_state_attributes(self):
        raw = getattr(self._hub.state, "input_words", {}).get(self._number)
        if raw is not None:
            state, derived_from = self._hub.decode_input_status(raw)
        else:
            state = self._hub.state.inputs.get(self._number)
            derived_from = "event_only"
        attrs = {
            "input_state": state,
            "last_event": getattr(self._hub.state, "last_event", None),
        }
        if raw is not None:
            attrs.update(
                {
                    "raw_status": raw,
                    "raw_status_hex": f"0x{raw:02X}",
                    "raw_status_binary": f"{raw:08b}",
                    "bit_0x01_set": bool(raw & 0x01),
                    "bit_0x02_set": bool(raw & 0x02),
                    "bit_0x04_set": bool(raw & 0x04),
                    "bit_0x08_set": bool(raw & 0x08),
                    "bit_0x10_set": bool(raw & 0x10),
                    "bit_0x20_sealed": bool(raw & 0x20),
                    "bit_0x40_set": bool(raw & 0x40),
                    "bit_0x80_set": bool(raw & 0x80),
                    "state_derived_from": derived_from,
                }
            )
        else:
            attrs["state_derived_from"] = derived_from
        return attrs


class TecomDoorContactBinarySensor(BinarySensorEntity):
    """Door contact derived from CTPlus door status words."""

    _attr_has_entity_name = True
    _attr_device_class = "door"
    _attr_icon = "mdi:door"

    def __init__(self, hub, door: int) -> None:
        self._hub = hub
        self._door = door
        self._attr_name = hub.contact_name(door, f"Door {door} Contact")
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
        state = getattr(self._hub.state, "doors", {}).get(self._door)
        if state == "open":
            return True
        if state == "closed":
            return False

        w = getattr(self._hub.state, "door_words", {}).get(self._door)
        if w is None:
            return None
        return bool(w & 0x0080)

    @property
    def extra_state_attributes(self):
        state = getattr(self._hub.state, "doors", {}).get(self._door)
        w = getattr(self._hub.state, "door_words", {}).get(self._door)

        attrs = {
            "door_state": state,
            "last_event": getattr(self._hub.state, "last_event", None),
        }
        if w is not None:
            attrs.update(
                {
                    "raw_status": w,
                    "raw_status_hex": f"0x{w:04X}",
                    "raw_status_binary": f"{w:016b}",
                    "bit_0x0080_open": bool(w & 0x0080),
                    "bit_0x0002_set": bool(w & 0x0002),
                    "bit_0x0010_set": bool(w & 0x0010),
                    "bit_0x0080_set": bool(w & 0x0080),
                    "contact_derived_from": (
                        "state.doors" if state in ("open", "closed") else "raw_status_bit_0x0080"
                    ),
                }
            )
        else:
            attrs["contact_derived_from"] = "state.doors"
        return attrs


class TecomRasContact(BinarySensorEntity):
    """RAS / keypad / simple door controller status surfaced as an opening sensor (best-effort)."""
    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.OPENING

    def __init__(self, hub, ras: int) -> None:
        self._hub = hub
        self._ras = ras
        self._attr_name = hub.contact_name(ras, f"RAS Door {ras} Contact")
        self._attr_unique_id = f"{hub.entry.entry_id}_ras_contact_{ras}"
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
        st = getattr(self._hub.state, "ras_status", {}).get(self._ras)
        if st is None:
            return None
        # Best-effort heuristic: 0x11 appears to be 'idle/normal' in captures.
        # Treat anything else as 'open/active' so changes are visible.
        return st != 0x11

    @property
    def extra_state_attributes(self):
        st = getattr(self._hub.state, "ras_status", {}).get(self._ras)
        if st is None:
            return {}
        return {"raw_status": st, "raw_status_hex": f"0x{st:02X}"}

