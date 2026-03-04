"""CTPlus event decoder.

Goal: make Home Assistant event payloads readable (similar to Printer mode).
We keep everything best-effort and non-destructive: always include raw hex.

As we learn more codes from real panels, this can be expanded.
"""

from __future__ import annotations


def decode_ctplus_event(code: int, obj: int, raw_hex: str) -> dict:
    """Decode CTPlus event (code/object) into a friendly payload."""

    code_hex = f"0x{code:02X}"
    obj_hex = f"0x{obj:02X}"

    # Minimal mapping for common, already-handled codes in hub.py
    if code == 0x96:
        message = f"Input {obj} sealed (normal)"
    elif code == 0x97:
        message = f"Input {obj} unsealed (active)"
    elif code == 0x84:
        message = f"Relay {obj} ON"
    elif code == 0x85:
        message = f"Relay {obj} OFF"
    elif code == 0x0B:
        message = f"Area {obj} armed"
    elif code == 0x0C:
        message = f"Area {obj} disarmed"
    else:
        # Unknown event: still provide a human-readable summary
        message = f"CTPlus event {code_hex} object {obj} ({obj_hex})"

    return {
        "code": code,
        "code_hex": code_hex,
        "object": obj,
        "object_hex": obj_hex,
        "raw": raw_hex,
        # Printer-mode-like text to make listening in HA easy
        "message": message,
        "text": message,
    }
