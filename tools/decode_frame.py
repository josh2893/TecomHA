#!/usr/bin/env python3
"""Decode CTPlus frames from hex, a pcapng capture, or a debug dump.

Protocol work in this project is almost entirely "what do these bytes mean",
so having one command that answers that saves writing throwaway scripts.

    python3 tools/decode_frame.py 5e4080000a6903120240
    python3 tools/decode_frame.py --pcap capture.pcapng
    python3 tools/decode_frame.py --debug tecom_challengerplus_debug_123.json
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _frames import proto, split_frame  # noqa: E402
from _pcap import udp_payloads  # noqa: E402

TYPE_NAMES = {0x40: "data/event", 0x41: "panel_ack", 0x60: "command",
              0x64: "heartbeat", 0x73: "host_ack"}

EVENT_NAMES = {
    0x00: "ALARM", 0x02: "Alarm restored", 0x0B: "Area secured (armed away)",
    0x0C: "Area accessed (disarmed)", 0x5A: "Comms restored", 0x6C: "Area secured stay",
    0x84: "Output active", 0x85: "Output normal", 0x86: "Door unlocked",
    0x87: "Door locked", 0x88: "Door auto unlocked", 0x89: "Door auto locked",
    0x92: "Access granted", 0x96: "Input unsealed", 0x97: "Input sealed",
    0x9D: "Access granted (egress)", 0xA5: "Door open", 0xA6: "Door closed",
    0xA7: "Door forced", 0xA9: "Door open too long", 0xAE: "Door unsecured",
    0xAF: "Door secured",
}


def describe(body: bytes) -> str:
    """Best description of a frame body, trying each known response shape."""
    if not body:
        return "(empty - acknowledgement)"

    door = proto.parse_door_status_response(body)
    if door:
        d, w = door
        return (f"door status: door {d} word=0x{w:04X} "
                f"[{'open' if proto.door_word_is_open(w) else 'closed'}, "
                f"{'unlocked' if proto.door_word_is_unlocked(w) else 'locked'}, "
                f"{'unsecured' if proto.door_word_is_unsecured(w) else 'secured'}]")

    inputs = proto.parse_input_status_response(body)
    if inputs:
        start, statuses = inputs
        shown = " ".join(f"{start+i}:0x{v:02X}" for i, v in enumerate(statuses[:12]))
        return f"input status from {start}: {shown}{' ...' if len(statuses) > 12 else ''}"

    area = proto.parse_area_status_response(body)
    if area:
        start, words = area
        return "area status: " + " ".join(
            f"{start+i}:0x{w:04X}{'(armed)' if w & 0x0080 else ''}" for i, w in enumerate(words))

    relay = proto.parse_relay_status_response(body)
    if relay:
        start, statuses = relay
        return f"relay status from {start}: {statuses}"

    users = proto.parse_user_records(body)
    if users:
        return f"user records: {len(users)} entries, numbers {[n for n, _ in users]}"

    fail = proto.parse_control_failed(body)
    if fail and fail.get("object_name"):
        return (f"control failed: action=0x{fail['action']:02X} reason=0x{fail['reason']:02X} "
                f"object={fail['object']} name={fail['object_name']!r}")

    ev = proto.parse_event_full(body)
    if ev:
        name = EVENT_NAMES.get(ev["code"], f"0x{ev['code']:02X}")
        extra = f" area={ev['area']}" if ev["area"] else ""
        extra += f" user={ev['user']}" if ev["user"] else ""
        anchored = "" if ev["anchored"] else "  (unanchored form)"
        return f"event: {name} object={ev['object']}{extra}{anchored}"

    return "(unrecognised)"


def show(raw: bytes, prefix: str = "") -> None:
    split = split_frame(raw)
    if not split:
        print(f"{prefix}UNPARSED {raw.hex()}")
        return
    msg_type, seq, body = split
    offset = 0x40 if msg_type >= 0x80 else 0x00
    base = (msg_type - offset) & 0xFF
    print(f"{prefix}type=0x{msg_type:02X} ({TYPE_NAMES.get(base, 'unknown')}) "
          f"seq=0x{seq:02X} body={body.hex()}")
    print(f"{prefix}    {describe(body)}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("hex", nargs="?", help="raw frame as hex")
    ap.add_argument("--pcap", help="pcapng capture to decode")
    ap.add_argument("--debug", help="integration debug dump to decode")
    ap.add_argument("--host", default=None,
                    help="host IP; frames from this address are labelled HOST in a pcap")
    args = ap.parse_args()

    if args.hex:
        show(bytes.fromhex(args.hex.replace(" ", "")))
    elif args.pcap:
        for pkt in udp_payloads(args.pcap):
            label = f"{pkt['src']:>15} "
            if args.host:
                label = "HOST  " if pkt["src"] == args.host else "PANEL "
            show(pkt["payload"], prefix=label)
    elif args.debug:
        from _frames import frames_from_debug
        for item in frames_from_debug(args.debug):
            show(bytes.fromhex(item["hex"]), prefix=f"{item['dir']:5} ")
    else:
        ap.print_help()
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
