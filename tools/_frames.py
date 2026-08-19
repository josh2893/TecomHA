"""Shared helpers for pulling CTPlus frames out of captures and debug dumps."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components" / "tecom_challengerplus"))

import ctplus_protocol as proto  # noqa: E402


def split_frame(raw: bytes):
    """Return (msg_type, seq, body) for a raw on-wire frame, or None.

    The frame length is not carried in the header, so the body length is found
    by trying each split until the CRC validates. Captures from the official
    software also carry trailing padding after the CRC, which this ignores.
    """
    if len(raw) < 7 or raw[0] != proto.SYNC:
        return None
    for body_len in range(0, min(len(raw), 400)):
        if 7 + body_len > len(raw):
            break
        body = raw[5:5 + body_len]
        crc = int.from_bytes(raw[5 + body_len:7 + body_len], "little")
        if crc == proto.crc16_modbus(raw[1:5] + body):
            return raw[1], raw[4], body
    return None


def frames_from_debug(path: str):
    """Yield {dir, hex, body} for frames recorded in a debug dump."""
    dump = json.load(open(path))
    for entry in dump.get("recent_frames", []):
        hexs = entry.get("hex") or ""
        if len(hexs) < 14:
            continue
        try:
            raw = bytes.fromhex(hexs)
        except ValueError:
            continue
        frame = proto.parse_frame(raw)
        if frame is None:
            continue
        yield {"dir": entry.get("dir"), "hex": hexs, "frame": frame}
