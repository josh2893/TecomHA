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

    def to_bytes(self) -> bytes:
        header = bytes([SYNC, self.msg_type, self.flag1, self.flag2, self.seq])
        crc = crc16_modbus(bytes([self.msg_type, self.flag1, self.flag2, self.seq]) + self.body)
        return header + self.body + crc.to_bytes(2, "little")

def parse_frame(data: bytes) -> Optional[Frame]:
    if not data or data[0] != SYNC or len(data) < 7:
        return None
    msg_type = data[1]
    flag1 = data[2]
    flag2 = data[3]
    seq = data[4]
    body = data[5:-2]
    recv_crc = int.from_bytes(data[-2:], "little")
    calc_crc = crc16_modbus(data[1:-2])
    if recv_crc != calc_crc:
        return None
    return Frame(msg_type=msg_type, seq=seq, flag1=flag1, flag2=flag2, body=body)

# -------------------------
# Frame builders
# -------------------------

def build_ack(seq: int) -> Frame:
    return Frame(TYPE_HOST_ACK, seq, FLAG1_DEFAULT, FLAG2_DEFAULT, b"")

def build_heartbeat(seq: int) -> Frame:
    return Frame(TYPE_HOST_HEARTBEAT, seq, FLAG1_DEFAULT, FLAG2_DEFAULT, b"")

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
