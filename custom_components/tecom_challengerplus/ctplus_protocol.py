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

def cmd_open_door(door: int) -> bytes:
    # Observed: 04 02 04 <door_number (byte)>
    if not (0 <= door <= 255):
        raise ValueError("Door must be 0-255 for this command form")
    return bytes([0x04, 0x02, 0x04, door])

def cmd_area_disarm(area: int) -> bytes:
    # Observed: 02 02 05 <area>
    if not (0 <= area <= 255):
        raise ValueError("Area must be 0-255")
    return bytes([0x02, 0x02, 0x05, area])

def cmd_area_arm_away(area: int) -> bytes:
    # Observed: 02 02 06 <area>
    if not (0 <= area <= 255):
        raise ValueError("Area must be 0-255")
    return bytes([0x02, 0x02, 0x06, area])

def cmd_area_arm_home(area: int) -> bytes:
    # Observed: 02 02 09 <area>
    if not (0 <= area <= 255):
        raise ValueError("Area must be 0-255")
    return bytes([0x02, 0x02, 0x09, area])


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

def parse_event(body: bytes) -> Optional[Tuple[int, int]]:
    """Return (event_code, object_number) where possible."""
    if not body:
        return None

    # Variant B: 0F 0C <timestamp x4> <code> <obj_lo> <obj_hi>
    # Checked FIRST because it is anchored at offset 0 and therefore unambiguous.
    # The 0x8A scan below is a free search over the whole body, and event
    # timestamps regularly contain 0x8A -- letting it run first silently
    # mis-decoded well-formed frames (e.g. a Door 17 open event read as code
    # 0x4D object 4517, and area arm/disarm codes landing on phantom area
    # numbers built out of timestamp bytes).
    if len(body) >= 9 and body[0] == 0x0F and body[1] == 0x0C:
        code = body[6]
        if code in (0x0B, 0x0C) and len(body) >= 11:
            obj = body[9] | (body[10] << 8)
        else:
            obj = body[7] | (body[8] << 8)
        return code, obj

    # Variant A: ... 8A <code> <obj_lo> <obj_hi> ...
    if 0x8A in body:
        i = body.index(0x8A)
        if i + 2 < len(body):
            code = body[i + 1]
            obj = body[i + 2]
            if i + 3 < len(body):
                obj |= body[i + 3] << 8
            return code, obj

    return None


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