"""Best-effort CTPlus event decoding to human-readable text.

This does not attempt to fully replicate CTPlus/Forcefield wording yet, but provides
useful messages for common event codes and keeps raw fields for debugging.
"""

from __future__ import annotations

def decode_ctplus_event(code: int, obj: int, raw_hex: str) -> dict:
    code_hex = f"0x{code:02X}"
    obj_hex = f"0x{obj:04X}"

    # Known/common mappings (expand as we confirm more from your logs)
    if code == 0x96:
        text = f"Input {obj} Sealed"
    elif code == 0x97:
        text = f"Input {obj} Unsealed"
    elif code == 0x84:
        text = f"Relay {obj} On"
    elif code == 0x85:
        text = f"Relay {obj} Off"
    elif code == 0x0B:
        text = f"Area {obj} Armed"
    elif code == 0x0C:
        text = f"Area {obj} Disarmed"
    else:
        text = f"CTPlus event {code_hex} object {obj} ({obj_hex})"

    return {
        "code": code,
        "code_hex": code_hex,
        "object": obj,
        "object_hex": obj_hex,
        "raw": raw_hex,
        "text": text,
        "message": text,
    }
