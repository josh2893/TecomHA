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
        header = bytes([SYNC, msg_type, self.flag1, self.flag2, self.seq])
        crc_data = bytes([msg_type, self.flag1, self.flag2, self.seq]) + self.body
        crc = crc16_modbus(crc_data)
        if self.has_ff:
            return header + b"\xFF" + self.body + crc.to_bytes(2, "little")
        return header + self.body + crc.to_bytes(2, "little")


def parse_frame(data: bytes) -> Optional[Frame]:
    if not data or data[0] != SYNC or len(data) < 7:
        return None

    raw_type = data[1]
    type_offset = 0x40 if raw_type >= 0x80 else 0x00
    msg_type = (raw_type - type_offset) & 0xFF
    flag1 = data[2]
    flag2 = data[3]
    seq = data[4]
    recv_crc = int.from_bytes(data[-2:], "little")

    # Normal form: CRC over [type..end-of-body]
    body = data[5:-2]
    if recv_crc == crc16_modbus(data[1:-2]):
        return Frame(msg_type=msg_type, seq=seq, flag1=flag1, flag2=flag2, body=body, has_ff=False, type_offset=type_offset)

    # FF-marker form: a 0xFF byte appears at index 5 but is excluded from CRC.
    if len(body) >= 1 and data[5] == 0xFF:
        body2 = data[6:-2]
        if recv_crc == crc16_modbus(data[1:5] + body2):
            return Frame(msg_type=msg_type, seq=seq, flag1=flag1, flag2=flag2, body=body2, has_ff=True, type_offset=type_offset)

    return None

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

    # Variant A: ... 8A <code> <obj_lo> <obj_hi> ...
    if 0x8A in body:
        i = body.index(0x8A)
        if i + 2 < len(body):
            code = body[i + 1]
            obj = body[i + 2]
            if i + 3 < len(body):
                obj |= body[i + 3] << 8
            return code, obj

    # Variant B: 0F 0C ... (capture3)
    if len(body) >= 9 and body[0] == 0x0F and body[1] == 0x0C:
        code = body[6]
        if code in (0x0B, 0x0C) and len(body) >= 11:
            obj = body[9] | (body[10] << 8)
        else:
            obj = body[7] | (body[8] << 8)
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

def cmd_request_door_status_wrapped(door: int, group: int = 0x80) -> bytes:
    """Observed door status request (wrapped): 7E 07 <group> 7C 04 00 68 01 <door>."""
    if not (0 <= door <= 255):
        raise ValueError("Door must be 0-255")
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


