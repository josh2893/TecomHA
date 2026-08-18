"""CTPlus/ChallengerPlus IP protocol helpers (experimental).

Implemented from observed CTPlus ↔ ChallengerPlus packet captures with Encryption=None.

Frame format observed:
  - Sync byte 0x5E
  - Header: type, 0x80, 0x00, seq
  - Body: variable length
  - CRC16/Modbus (little-endian) over bytes [type..end-of-body]
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

SYNC = 0x5E

TYPE_EVENT_OR_DATA = 0x40  # panel -> host, requires ACK
TYPE_COMMAND = 0x60        # host -> panel, requires panel ACK (0x41)
TYPE_PANEL_ACK = 0x41      # panel -> host, ACK for host command
TYPE_HOST_ACK = 0x73       # host -> panel, ACK for panel data/event frames
TYPE_HOST_HEARTBEAT = 0x64 # host -> panel, keepalive (observed, empty body)

FLAG1_DEFAULT = 0x80
FLAG2_DEFAULT = 0x00

def crc16_modbus(data: bytes, init: int = 0xFFFF) -> int:
    """CRC16/Modbus."""
    crc = init
    for b in data:
        crc ^= b
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc & 0xFFFF


def stuff_bytes(data: bytes) -> bytes:
    """Escape literal 0x5E bytes so they are not read as a frame sync marker.

    Everything transmitted after the leading sync byte is subject to this rule,
    including the type/flag/seq header fields.
    """
    return data.replace(b"\x5e", b"\x5e\xff")


def unstuff_bytes(data: bytes) -> bytes:
    """Inverse of stuff_bytes(): collapse 0x5E 0xFF back to a literal 0x5E."""
    return data.replace(b"\x5e\xff", b"\x5e")


@dataclass(frozen=True)
class Frame:
    msg_type: int
    seq: int
    flag1: int = FLAG1_DEFAULT
    flag2: int = FLAG2_DEFAULT
    body: bytes = b""
    # Some panel->host frames include an extra 0xFF marker immediately after the header.
    # In that case the CRC is computed excluding the 0xFF marker.
    has_ff: bool = False
    type_offset: int = 0  # 0 or 0x40 (panel variant)

    def to_bytes(self) -> bytes:
        msg_type = (self.msg_type + self.type_offset) & 0xFF
        crc_data = bytes([msg_type, self.flag1, self.flag2, self.seq]) + self.body
        crc = crc16_modbus(crc_data)
        if self.has_ff:
            payload = bytes([msg_type, self.flag1, self.flag2, self.seq]) + b"\xFF" + self.body + crc.to_bytes(2, "little")
        else:
            payload = crc_data + crc.to_bytes(2, "little")
        # Byte-stuff EVERY 0x5E after the sync byte so the panel receiver does not
        # mistake it for a new frame sync marker.  This covers the header fields as
        # well as the body/CRC: when the sequence counter reaches 0x5E the seq byte
        # itself must be stuffed, otherwise the panel truncates the frame there and
        # the ACK is silently dropped.  The panel applies the inverse transform
        # (0x5E 0xFF -> 0x5E) on receive; parse_frame() mirrors that below.
        return bytes([SYNC]) + stuff_bytes(payload)


def parse_frame(data: bytes) -> Optional[Frame]:
    if not data or data[0] != SYNC or len(data) < 7:
        return None

    def _build(payload: bytes) -> Optional[Frame]:
        """Try to interpret post-sync bytes as [type flag1 flag2 seq body crc]."""
        if len(payload) < 6:
            return None
        raw_type = payload[0]
        type_offset = 0x40 if raw_type >= 0x80 else 0x00
        msg_type = (raw_type - type_offset) & 0xFF
        flag1 = payload[1]
        flag2 = payload[2]
        seq = payload[3]
        recv_crc = int.from_bytes(payload[-2:], "little")

        # Normal form: CRC over [type..end-of-body]
        body = payload[4:-2]
        if recv_crc == crc16_modbus(payload[:-2]):
            return Frame(msg_type=msg_type, seq=seq, flag1=flag1, flag2=flag2,
                         body=body, has_ff=False, type_offset=type_offset)

        # Legacy FF-marker form: a 0xFF byte appears immediately after the header
        # and is excluded from CRC. Kept for compatibility with older captures.
        if len(body) >= 1 and payload[4] == 0xFF:
            body2 = payload[5:-2]
            if recv_crc == crc16_modbus(payload[:4] + body2):
                return Frame(msg_type=msg_type, seq=seq, flag1=flag1, flag2=flag2,
                             body=body2, has_ff=True, type_offset=type_offset)
        return None

    # Byte-stuffing applies to everything after the sync byte, including the
    # type/flag/seq header fields. When the panel's sequence counter reaches
    # 0x5E the seq byte itself arrives stuffed as 0x5E 0xFF, so unstuffing must
    # start at offset 1 -- not offset 5 -- or the escape byte is mistaken for
    # the first body byte and the CRC check fails.
    fr = _build(unstuff_bytes(data[1:]))
    if fr is not None:
        return fr

    # Fall back to the literal (unstuffed) interpretation for any capture where
    # 0x5E 0xFF legitimately appears as data rather than as an escape sequence.
    return _build(data[1:])

# -------------------------
# Frame builders
# -------------------------

def build_ack(seq: int, has_ff: bool = False, type_offset: int = 0) -> Frame:
    return Frame(TYPE_HOST_ACK, seq, FLAG1_DEFAULT, FLAG2_DEFAULT, b"", has_ff=has_ff, type_offset=type_offset)

def build_heartbeat(seq: int, type_offset: int = 0) -> Frame:
    return Frame(TYPE_HOST_HEARTBEAT, seq, FLAG1_DEFAULT, FLAG2_DEFAULT, b"", type_offset=type_offset)

# -------------------------
# Command builders (observed)
# -------------------------

def cmd_request_input_status(start: int, end: int) -> bytes:
    # Observed: 09 04 <start_lo> <start_hi> <end_lo> <end_hi>
    return bytes([0x09, 0x04]) + start.to_bytes(2, "little") + end.to_bytes(2, "little")

def cmd_request_relay_status(start: int, end: int) -> bytes:
    # Observed: 66 04 <start_lo> <start_hi> <end_lo> <end_hi>
    return bytes([0x66, 0x04]) + start.to_bytes(2, "little") + end.to_bytes(2, "little")

def cmd_set_relay(relay: int, on: bool) -> bytes:
    # Observed: 03 03 <action> <relay_lo> <relay_hi>
    # action 0x02 = Set (ON), 0x01 = Reset (OFF)
    action = 0x02 if on else 0x01
    return bytes([0x03, 0x03, action]) + relay.to_bytes(2, "little")

# Door control commands share the form 04 02 <action> <door_number>.
# Actions confirmed from CTPlus captures on Door 17:
#   0x01 lock      -> panel replies 0x87 (Door locked)   then 0xAF (Door secured)
#   0x02 unlock    -> panel replies 0x86 (Door unlocked) then 0xAE (Door unsecured)
#   0x04 momentary -> grants access without changing lock mode
DOOR_ACTION_LOCK = 0x01
DOOR_ACTION_UNLOCK = 0x02
DOOR_ACTION_OPEN = 0x04


def _cmd_door_action(door: int, action: int) -> bytes:
    if not (0 <= door <= 255):
        raise ValueError("Door must be 0-255 for this command form")
    return bytes([0x04, 0x02, action, door])


def cmd_open_door(door: int) -> bytes:
    """Momentary access grant. Does not change the door's lock mode."""
    return _cmd_door_action(door, DOOR_ACTION_OPEN)


def cmd_lock_door(door: int) -> bytes:
    """Set the door to locked/secured."""
    return _cmd_door_action(door, DOOR_ACTION_LOCK)


def cmd_unlock_door(door: int) -> bytes:
    """Set the door to unlocked/free access until locked again."""
    return _cmd_door_action(door, DOOR_ACTION_UNLOCK)


# Area control commands share the form 02 02 <action> <area>.
# Actions confirmed from CTPlus captures:
#   0x05 disarm     -> panel replies 0x0C (Area disarmed)
#   0x06 force arm  -> arms regardless of unsealed inputs
#   0x09 arm        -> validates first; refuses with a reason if inputs are unsealed
#   0x0A arm stay   -> panel replies 0x6C (Area secured stay)
AREA_ACTION_DISARM = 0x05
AREA_ACTION_FORCE_ARM = 0x06
AREA_ACTION_ARM = 0x09
AREA_ACTION_ARM_STAY = 0x0A

# Actions that arm. Only these can produce an "arm refused" condition; the panel
# also answers other commands with 0x02 frames, and treating those as refusals
# raised spurious warnings (notably when disarming an area that was in alarm).
AREA_ARM_ACTIONS = (AREA_ACTION_FORCE_ARM, AREA_ACTION_ARM, AREA_ACTION_ARM_STAY)
ARM_ACTION_NAMES = {
    AREA_ACTION_FORCE_ARM: "Force arm",
    AREA_ACTION_ARM: "Arm",
    AREA_ACTION_ARM_STAY: "Arm home",
}

# Event codes that describe an area rather than a point.
EVENT_AREA_SECURED = 0x0B        # armed (away)
EVENT_AREA_ACCESSED = 0x0C       # disarmed
EVENT_AREA_SECURED_STAY = 0x6C   # armed (stay/home)
AREA_EVENT_CODES = (EVENT_AREA_SECURED, EVENT_AREA_ACCESSED, EVENT_AREA_SECURED_STAY)

# Access events, which carry a user number in bytes 10-11 of the event body.
EVENT_ACCESS_GRANTED = 0x92
EVENT_ACCESS_GRANTED_EGRESS = 0x9D
ACCESS_EVENT_CODES = (EVENT_ACCESS_GRANTED, EVENT_ACCESS_GRANTED_EGRESS)

# Point-scoped alarm codes. The event carries both the offending object and the
# area it belongs to, so no zone-to-area mapping is required.
EVENT_ALARM = 0x00
EVENT_ALARM_RESTORED = 0x02
EVENT_SECURE_ALARM = 0x04
EVENT_SECURE_ALARM_RESTORED = 0x05
EVENT_MULTIBREAK_ALARM = 0x57
EVENT_MULTIBREAK_ALARM_RESTORED = 0x58
EVENT_EXIT_ALARM = 0x67
EVENT_EXIT_ALARM_RESTORED = 0x68
EVENT_LOCAL_ALARM = 0xC2
EVENT_LOCAL_ALARM_RESET = 0xC3

ALARM_EVENT_CODES = (
    EVENT_ALARM,
    EVENT_SECURE_ALARM,
    EVENT_MULTIBREAK_ALARM,
    EVENT_EXIT_ALARM,
    EVENT_LOCAL_ALARM,
)
ALARM_RESTORE_EVENT_CODES = (
    EVENT_ALARM_RESTORED,
    EVENT_SECURE_ALARM_RESTORED,
    EVENT_MULTIBREAK_ALARM_RESTORED,
    EVENT_EXIT_ALARM_RESTORED,
    EVENT_LOCAL_ALARM_RESET,
)


def _cmd_area_action(area: int, action: int) -> bytes:
    if not (0 <= area <= 255):
        raise ValueError("Area must be 0-255")
    return bytes([0x02, 0x02, action, area])


def cmd_request_users(start: int = 1) -> bytes:
    """Request the user database starting at a given user number.

    Observed form: 25 05 1D <start lo> <start hi> FF FF

    The panel replies with a batch of user records; ask again from the last
    returned number + 1 until it responds with an empty acknowledgement.
    """
    if not (0 <= start <= 0xFFFF):
        raise ValueError("Start user must be 0-65535")
    return bytes([0x25, 0x05, 0x1D, start & 0xFF, (start >> 8) & 0xFF, 0xFF, 0xFF])


USER_RECORD_NAME_OFFSET = 19
USER_RECORD_NAME_MAX = 16  # the panel truncates stored names to 16 characters


def parse_user_records(body: bytes) -> Optional[list]:
    """Decode a user-database response into [(user_number, name), ...].

    Observed form::

        7D <len> 1D 2B <record> <record> ...
                    ^^ record size (43)

    Each record carries the user number at bytes 0-1 and a null-padded ASCII
    name from byte 19.  Bytes in between hold per-user credential material
    (card and PIN data) which is deliberately NOT extracted -- only the number
    and name are needed to label access events, and the rest is sensitive.
    """
    if len(body) < 4 or body[0] != 0x7D or body[2] != 0x1D:
        return None
    rec_size = body[3]
    if rec_size < USER_RECORD_NAME_OFFSET + 1:
        return None
    payload = body[4:]
    out: list = []
    for off in range(0, len(payload) - rec_size + 1, rec_size):
        rec = payload[off:off + rec_size]
        number = rec[0] | (rec[1] << 8)
        if not number:
            continue
        raw_name = rec[USER_RECORD_NAME_OFFSET:USER_RECORD_NAME_OFFSET + USER_RECORD_NAME_MAX]
        name = raw_name.split(b"\x00", 1)[0].decode("ascii", errors="replace").strip()
        if name:
            out.append((number, name))
    return out or None


def cmd_area_disarm(area: int) -> bytes:
    return _cmd_area_action(area, AREA_ACTION_DISARM)


def cmd_area_arm(area: int) -> bytes:
    """Normal arm. The panel refuses and reports a reason if inputs are unsealed."""
    return _cmd_area_action(area, AREA_ACTION_ARM)


def cmd_area_force_arm(area: int) -> bytes:
    """Force arm. Arms regardless of unsealed inputs."""
    return _cmd_area_action(area, AREA_ACTION_FORCE_ARM)


# Retained for callers that predate the arm/force-arm split.
def cmd_area_arm_away(area: int) -> bytes:
    return _cmd_area_action(area, AREA_ACTION_FORCE_ARM)


def cmd_area_arm_home(area: int) -> bytes:
    """Arm stay / home. Confirmed as action 0x0A from CTPlus capture."""
    return _cmd_area_action(area, AREA_ACTION_ARM_STAY)


def parse_control_failed(body: bytes) -> Optional[dict]:
    """Decode a control-failure response to an area command.

    Observed when a normal arm (0x09) is refused because an input is unsealed::

        02 22 09 48 16 00 "<object name>" <null padding to 30 bytes>
        ^  ^  ^  ^  ^^^^^ ^
        |  |  |  |  |     object name, fixed 30-byte null-padded field
        |  |  |  |  object number (little endian) -- input 22
        |  |  |  reason code
        |  |  action that was attempted (0x09 arm)
        |  payload length
        response type
    """
    if len(body) < 6 or body[0] != 0x02:
        return None
    length = body[1]
    payload = body[2:2 + length]
    if len(payload) < 4:
        return None
    name = payload[4:].split(b"\x00", 1)[0].decode("ascii", errors="replace").strip()
    return {
        "action": payload[0],
        "reason": payload[1],
        "object": payload[2] | (payload[3] << 8),
        "object_name": name,
    }


def cmd_retrieve_events() -> bytes:
    """Request delivery of queued events for the current computer comms path.

    Observed when CTPlus uses the "Retrieve events" action:
      Host->Panel: 07 03 0E 03 03
      Panel->Host: 41/81 ACK, followed by one or more queued 0x40 events.
    """
    return b"\x07\x03\x0E\x03\x03"

# -------------------------
# Response / event parsing
# -------------------------

def parse_input_status_response(body: bytes) -> Optional[Tuple[int, bytes]]:
    # Observed: 0A <len> <start_lo> <start_hi> <status bytes...>
    if len(body) < 4 or body[0] != 0x0A:
        return None
    length = body[1]
    start = int.from_bytes(body[2:4], "little")
    status_bytes = body[4:4 + max(0, length - 2)]
    return start, status_bytes

def parse_relay_status_response(body: bytes) -> Optional[Tuple[int, bytes]]:
    # Observed: 67 <len> <start_lo> <start_hi> <status bytes...>
    if len(body) < 4 or body[0] != 0x67:
        return None
    length = body[1]
    start = int.from_bytes(body[2:4], "little")
    status_bytes = body[4:4 + max(0, length - 2)]
    return start, status_bytes

def parse_event_full(body: bytes) -> Optional[dict]:
    """Decode an event into its component fields.

    The anchored form is::

        0F 0C <timestamp x4> <code> <object lo> <object hi> <area> <extra>

    ``object`` identifies the input/door/relay the event refers to, and ``area``
    is the region it belongs to.  Doors and outputs report area 0.  The byte
    after the area carries an unrelated field (a user number on access-granted
    events), so the area is read as a single byte rather than a 16-bit value.

    Returns a dict with ``code``, ``object``, ``area`` and ``anchored`` keys, or
    None if the body cannot be interpreted as an event.
    """
    if not body:
        return None

    # Anchored form. Checked FIRST because it starts at offset 0 and is therefore
    # unambiguous. The 0x8A scan below is a free search over the whole body, and
    # event timestamps regularly contain 0x8A -- letting it run first silently
    # mis-decoded well-formed frames (e.g. a Door 17 open event read as code
    # 0x4D object 4517, and area codes landing on phantom area numbers built out
    # of timestamp bytes).
    if len(body) >= 9 and body[0] == 0x0F and body[1] == 0x0C:
        code = body[6]
        obj = body[7] | (body[8] << 8)
        area = body[9] if len(body) >= 10 else 0
        # Bytes 10-11 carry the user number as a little-endian 16-bit value, but
        # ONLY on access events -- other codes use those bytes for unrelated
        # fields, so reading them unconditionally invents users that do not
        # exist. Confirmed against a capture of a four-digit user number, which
        # a single-byte read would have truncated to its low byte.
        if code in ACCESS_EVENT_CODES and len(body) >= 12:
            user = body[10] | (body[11] << 8)
        else:
            user = 0
        return {"code": code, "object": obj, "area": area, "user": user, "anchored": True}

    # Legacy unanchored form: ... 8A <code> <obj_lo> <obj_hi> ...
    if 0x8A in body:
        i = body.index(0x8A)
        if i + 2 < len(body):
            code = body[i + 1]
            obj = body[i + 2]
            if i + 3 < len(body):
                obj |= body[i + 3] << 8
            return {"code": code, "object": obj, "area": 0, "user": 0, "anchored": False}

    return None


def parse_event(body: bytes) -> Optional[Tuple[int, int]]:
    """Return (event_code, object_number) where possible.

    Area-scoped events report the area as the object so that existing callers
    which expect a single identifier keep working.  Use parse_event_full() to
    get the object and area as separate fields.
    """
    ev = parse_event_full(body)
    if ev is None:
        return None
    if ev["anchored"] and ev["code"] in AREA_EVENT_CODES:
        return ev["code"], ev["area"]
    return ev["code"], ev["object"]


# -------------------------
# Area status (observed)
# -------------------------

def cmd_request_area_status(start_area: int, count: int = 4) -> bytes:
    """Request status for a range of Areas.

    Observed in CTPlus capture 'Zone Status 3 times in a row':
      Host->Panel: 60 02 <start_area> <count>
      Panel->Host: 6A <len> <start_area> <status_words...>

    Where status words are 16-bit little-endian per area.
    """
    if not (0 <= start_area <= 255 and 1 <= count <= 255):
        raise ValueError("Area range out of bounds")
    return bytes([0x60, 0x02, start_area & 0xFF, count & 0xFF])


def parse_area_status_response(body: bytes) -> Optional[Tuple[int, list[int]]]:
    """Parse an Area status response.

    Returns (start_area, [status_word...]).
    """
    if len(body) < 3 or body[0] != 0x6A:
        return None
    length = body[1]
    payload = body[2:2+length]
    if len(payload) < 1:
        return None
    start = payload[0]
    words = []
    rest = payload[1:]
    # each status word is 2 bytes LE
    for i in range(0, len(rest) - (len(rest) % 2), 2):
        words.append(int.from_bytes(rest[i:i+2], 'little'))
    return start, words


# -------------------------
# Session / init helpers (observed)
# -------------------------

def cmd_session_hello() -> bytes:
    """Observed CTPlus startup command: 25 01 92."""
    return b"\x25\x01\x92"

def cmd_session_params() -> bytes:
    """Observed CTPlus startup command: 01 06 0B 00 00 00 00 00."""
    return b"\x01\x06\x0B\x00\x00\x00\x00\x00"


# -------------------------
# Door status (observed)
# -------------------------

def cmd_door_status_init() -> bytes:
    """Observed one-time init before door status queries: 68 02 03 03."""
    return b"\x68\x02\x03\x03"

def cmd_request_door_status_wrapped(door: int, group: int | None = None) -> bytes:
    """Door status request (wrapped): 7E 07 <group> 7C 04 00 68 01 <door>.

    CTPlus uses a group byte that increments per DGP (4 doors per DGP), starting at door 17:
      17-20 -> 0x80, 21-24 -> 0x81, 25-28 -> 0x82, ...
    """
    if not (0 <= door <= 255):
        raise ValueError("Door must be 0-255")

    if group is None:
        if door >= 17:
            group = 0x80 + ((door - 17) // 4)
        else:
            group = 0x80

    if not (0 <= group <= 255):
        raise ValueError("Group must be 0-255")

    return bytes([0x7E, 0x07, group, 0x7C, 0x04, 0x00, 0x68, 0x01, door])

def parse_door_status_response(body: bytes) -> Optional[Tuple[int, int]]:
    """Parse door status response: 69 <len> <door> <status_lo> <status_hi>."""
    if len(body) < 5 or body[0] != 0x69:
        return None
    ln = body[1]
    payload = body[2:2+ln]
    if len(payload) < 3:
        return None
    door = payload[0]
    status = int.from_bytes(payload[1:3], "little")
    return door, status

def cmd_request_ras_status(ras: int) -> bytes:
    """Request status for a RAS / keypad / single-door controller (doors 1-16)."""
    r = ras & 0xFF
    return bytes([0x62, 0x02, r, r])

def parse_ras_status_response(body: bytes) -> tuple[int, int] | None:
    """Parse a RAS status response. Expected: 63 02 <ras> <status>."""
    if len(body) >= 4 and body[0] == 0x63 and body[1] == 0x02:
        return body[2], body[3]
    return None