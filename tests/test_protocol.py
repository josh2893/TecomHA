"""Ground-truth protocol tests.

Every constant here came from a packet capture of the official CTPlus software
or of a panel driven through a known physical state. They are regression
guards: if one fails, either the protocol handling changed or an assumption
that was verified once has been quietly broken.

Run with:  python3 -m pytest tests/ -q
"""
from __future__ import annotations


import pytest

from tecom_cp import ctplus_protocol as proto  # noqa: E402  (see conftest.py)


# --------------------------------------------------------------------------
# Byte stuffing
#
# 0x5E is the frame sync marker and must be escaped everywhere after the sync
# byte, including the header and CRC. Two separate multi-hour comms stalls were
# caused by applying this too narrowly: once when a CRC contained 0x5E, and
# again when the sequence counter itself reached 0x5E.
# --------------------------------------------------------------------------

def test_crc_containing_sync_is_stuffed():
    # seq 0x36 produces CRC 0x5E9B; the high byte is the sync marker.
    assert proto.build_ack(0x36).to_bytes() == bytes.fromhex("5e738000369b5eff")


def test_sequence_byte_of_sync_value_is_stuffed():
    # When the counter reaches 0x5E the seq byte itself must be escaped.
    assert proto.build_ack(0x5E).to_bytes() == bytes.fromhex("5e7380005eff9ab0")


def test_panel_frame_with_stuffed_sequence_parses():
    # Captured from the panel while its event counter was at 0x5E.
    raw = bytes.fromhex("5e4080005eff0f0c09c9015eff97100001000000008e8d")
    frame = proto.parse_frame(raw)
    assert frame is not None
    assert frame.seq == 0x5E


@pytest.mark.parametrize("msg_type", [0x73, 0x64, 0x60, 0x40])
@pytest.mark.parametrize("body", [
    b"", bytes([0x5E]), bytes([0x5E, 0xFF]), bytes([0x5E, 0x5E]),
    bytes.fromhex("0f0c09c9015e97100001000000"),
])
def test_round_trip_never_emits_bare_sync(msg_type, body):
    for seq in range(256):
        wire = proto.Frame(msg_type, seq, body=body, type_offset=0x00).to_bytes()
        # No unescaped 0x5E may appear after the leading sync byte.
        assert 0x5E not in wire[1:].replace(b"\x5e\xff", b"")
        back = proto.parse_frame(wire)
        assert back is not None and back.seq == seq and back.body == body


# --------------------------------------------------------------------------
# Door status word
#
# Captured by driving one door through every combination of locked/unlocked and
# open/closed, polling status immediately after each change. The word is BIG
# endian; reading it little endian swaps the bytes and makes an open door
# report as closed.
# --------------------------------------------------------------------------

DOOR_STATES = [
    # (response body, open, unlocked, unsecured)
    ("6903120000", False, False, False),   # locked + closed
    ("6903120240", False, True,  True),    # unlocked + closed
    ("69031212c0", True,  True,  True),    # unlocked + open
    ("69031210c0", True,  False, True),    # locked + open
]


@pytest.mark.parametrize("body,is_open,unlocked,unsecured", DOOR_STATES)
def test_door_word_decode(body, is_open, unlocked, unsecured):
    door, word = proto.parse_door_status_response(bytes.fromhex(body))
    assert door == 18
    assert proto.door_word_is_open(word) is is_open
    assert proto.door_word_is_unlocked(word) is unlocked
    assert proto.door_word_is_unsecured(word) is unsecured


def test_door_word_is_big_endian():
    # The regression this guards: little endian put the contact bit in the
    # wrong half, so an open door decoded as closed.
    _, word = proto.parse_door_status_response(bytes.fromhex("69031212c0"))
    assert word == 0x12C0


# --------------------------------------------------------------------------
# Commands, each matched byte-for-byte against a capture of CTPlus
# --------------------------------------------------------------------------

@pytest.mark.parametrize("builder,arg,expected", [
    (proto.cmd_lock_door,      17, "04020111"),
    (proto.cmd_unlock_door,    17, "04020211"),
    (proto.cmd_open_door,      17, "04020411"),
    (proto.cmd_area_disarm,     4, "02020504"),
    (proto.cmd_area_force_arm,  4, "02020604"),
    (proto.cmd_area_arm,        1, "02020901"),
    (proto.cmd_area_arm_home,   4, "02020a04"),
])
def test_command_bytes(builder, arg, expected):
    assert builder(arg).hex() == expected


def test_area_commands_only_differ_by_action_and_number():
    # Guards against a builder being changed in isolation.
    assert proto.cmd_area_arm(7).hex() == "02020907"
    assert proto.cmd_area_arm_home(16).hex() == "02020a10"


def test_user_request_matches_capture():
    assert proto.cmd_request_users(1).hex() == "25051d0100ffff"
    assert proto.cmd_request_users(149).hex() == "25051d9500ffff"


# --------------------------------------------------------------------------
# Events
# --------------------------------------------------------------------------

def test_anchored_form_beats_loose_scan():
    # Event timestamps contain 0x8A. Scanning for it before checking the
    # anchored 0F 0C form decoded a door-open event as code 0x4D object 4517.
    body = bytes.fromhex("0f0c88488a4da511000000000000")
    assert proto.parse_event(body) == (0xA5, 17)


def test_alarm_event_carries_object_and_area():
    ev = proto.parse_event_full(bytes.fromhex("0f0c11c9d286001600010000 0000".replace(" ", "")))
    assert ev["code"] == proto.EVENT_ALARM
    assert ev["object"] == 22
    assert ev["area"] == 1


def test_area_events_report_area_not_object():
    # Area-scoped codes carry the area at byte 9; object is zero.
    ev = proto.parse_event_full(bytes.fromhex("0f0c1149e0816c00000400000000"))
    assert ev["code"] == proto.EVENT_AREA_SECURED_STAY
    assert ev["area"] == 4


def test_user_number_is_sixteen_bit():
    # A four-digit user truncated to its low byte under a single-byte read,
    # silently attributing the access to a different user. 4131 is 0x1023, so a
    # single-byte read would report user 35.
    ev = proto.parse_event_full(bytes.fromhex("0f0c11490eaa9211000023100000"))
    assert ev["user"] == 4131


@pytest.mark.parametrize("body", [
    "0f0c0f49f2635a10000000040000",   # comms restored
    "0f0c0f49f263ff24000000041000",   # sub-coded event
])
def test_user_is_not_inferred_on_non_access_events(body):
    # Bytes 10-11 hold unrelated fields on other codes; reading them as a user
    # invented users that do not exist.
    ev = proto.parse_event_full(bytes.fromhex(body))
    assert ev["code"] not in proto.ACCESS_EVENT_CODES
    assert ev["user"] == 0


# --------------------------------------------------------------------------
# Input seal state
#
# Bits 5 and 6 together carry the seal indication, and which one clears depends
# on the input's programmed type. Testing bit 0x20 alone left Type 20 inputs
# reporting permanently sealed.
# --------------------------------------------------------------------------

@pytest.mark.parametrize("raw,sealed", [
    (0x63, True),   # sealed
    (0x61, True),   # sealed, other flags differ
    (0x43, False),  # unsealed, standard input type
    (0x23, False),  # unsealed, Type 20
    (0x21, False),  # unsealed, Type 20
])
def test_input_seal_mask(raw, sealed):
    assert ((raw & 0x60) == 0x60) is sealed


# --------------------------------------------------------------------------
# Control failure
# --------------------------------------------------------------------------

def test_control_failure_parses_action_and_object():
    body = bytes.fromhex("0222094816004e6f7274682045677265737300000000000000000000000000")
    failure = proto.parse_control_failed(body)
    assert failure["action"] == proto.AREA_ACTION_ARM
    assert failure["object"] == 22
    assert failure["object_name"] == "North Egress"


def test_only_arm_actions_are_refusals():
    # Disarming an area in alarm also returns a 0x02 frame; treating it as a
    # refusal raised a false warning on every area card.
    assert proto.AREA_ACTION_DISARM not in proto.AREA_ARM_ACTIONS
    assert proto.AREA_ACTION_ARM in proto.AREA_ARM_ACTIONS
    assert proto.AREA_ACTION_FORCE_ARM in proto.AREA_ARM_ACTIONS
    assert proto.AREA_ACTION_ARM_STAY in proto.AREA_ARM_ACTIONS


# --------------------------------------------------------------------------
# User records
# --------------------------------------------------------------------------

def test_user_records_extract_number_and_name_only():
    # Synthetic record in the captured layout. Bytes 2-18 hold card and PIN
    # material and must never be extracted.
    rec = bytearray(43)
    rec[0:2] = (150).to_bytes(2, "little")
    rec[6:12] = bytes.fromhex("424200000004")     # credential bytes
    rec[19:19 + 8] = b"J. Smith"
    body = bytes([0x7D, 45, 0x1D, 43]) + bytes(rec)
    records = proto.parse_user_records(body)
    assert records == [(150, "J. Smith")]


def test_user_record_parser_ignores_other_frames():
    for body in ["6903120240", "0f0c1149e0816c00000400000000", "0a1b010063636363"]:
        assert proto.parse_user_records(bytes.fromhex(body)) is None
