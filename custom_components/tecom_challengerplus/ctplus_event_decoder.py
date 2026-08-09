from __future__ import annotations

from .ctplus_eventtable_data import EVENTTABLE

# Hand-confirmed overrides from supplied captures / CTPlus UI. These take precedence
# over the bundled eventtable where field naming in the table is ambiguous for live UI.
_CONFIRMED_TEXT = {
    0x0B: "Secured",
    0x0C: "Accessed",
    0x84: "On",
    0x85: "Off",
    0x96: "Unsealed",
    0x97: "Sealed",
    0xA5: "Open",
    0xA6: "Closed",
    0xA7: "Forced",
    0xA8: "Forced restored",
    0xA9: "Open too long",
    0xAA: "Open too long restored",
    0xAE: "Unsecured",
    0xAF: "Secured",
    0x86: "Unlocked",
    0x87: "Locked",
    0x88: "Auto unlocked",
    0x89: "Auto locked",
    0x92: "Access granted",
    0x9D: "Access granted - egress",
    0x59: "Comms - path fail",
    0x5A: "Comms - path restored",
    0x5B: "Expander - comms fault",
    0x5C: "Expander - comms restored",
    0x5D: "Expander - hardware fail",
    0x5E: "Expander - hardware restored",
}

_DOOR_CODES = {0x86,0x87,0x88,0x89,0x92,0x9D,0xA5,0xA6,0xA7,0xA8,0xA9,0xAA,0xAE,0xAF}
_INPUT_CODES = {0x96,0x97}
_RELAY_CODES = {0x84,0x85}
_AREA_CODES = {0x0B,0x0C}

def _load_eventtable() -> dict[tuple[int, int], dict]:
    return EVENTTABLE


def _extract_sub_event(raw: bytes, code: int) -> int | None:
    # Common CTPlus body variants seen in captures.
    if len(raw) >= 8 and raw[0] == 0x0F and raw[1] == 0x0C and code == 0xFF:
        return raw[7]
    if 0x8A in raw:
        i = raw.index(0x8A)
        if i + 2 < len(raw) and code == 0xFF:
            return raw[i + 2]
    return None


def _label_prefix(code: int) -> str | None:
    if code in _AREA_CODES:
        return 'Area'
    if code in _INPUT_CODES:
        return 'Input'
    if code in _RELAY_CODES:
        return 'Relay'
    if code in _DOOR_CODES:
        return 'Door'
    return None


def _best_description(code: int, raw: bytes) -> tuple[str, dict | None, int | None]:
    table = _load_eventtable()
    sub = _extract_sub_event(raw, code)
    row = None
    if sub is not None:
        row = table.get((code, sub))
    if row is None:
        row = table.get((code, 0))
    if row is None and sub is not None:
        row = table.get((0xFF, sub))
    desc = _CONFIRMED_TEXT.get(code)
    if not desc and row is not None:
        desc = (row.get('Description') or '').strip()
    if not desc:
        desc = f'CTPlus event 0x{code:02X}' if sub is None else f'CTPlus event 0x{code:02X}/0x{sub:02X}'
    return desc, row, sub


def decode_ctplus_event(code: int, obj: int, raw_hex: str) -> dict:
    code_hex = f"0x{code:02X}"
    obj_hex = f"0x{obj:04X}"
    raw = bytes.fromhex(raw_hex) if raw_hex else b''
    desc, row, sub = _best_description(code, raw)

    prefix = _label_prefix(code)
    if prefix == 'Area':
        text = f"Area {obj} {desc}"
    elif prefix == 'Input':
        text = f"Input {obj} {desc}"
    elif prefix == 'Relay':
        text = f"Relay {obj} {desc}"
    elif prefix == 'Door':
        text = f"Door {obj} {desc}"
    else:
        # For path/expander/system events the object number is not always a user-facing ID.
        text = desc if obj == 0 else f"{desc} (object {obj})"

    payload = {
        'code': code,
        'code_hex': code_hex,
        'object': obj,
        'object_hex': obj_hex,
        'raw': raw_hex,
        'text': text,
        'message': text,
    }
    if sub is not None:
        payload['subcode'] = sub
        payload['subcode_hex'] = f"0x{sub:02X}"
    if row is not None:
        payload['eventtable_description'] = (row.get('Description') or '').strip() or desc
        payload['eventtable_event_code'] = int(row['EventCode']) if (row.get('EventCode') or '').isdigit() else row.get('EventCode')
        payload['eventtable_response_required'] = (row.get('ReponseRequired') or '0') == '1'
        payload['eventtable_required_2nd_response'] = (row.get('Required2ndResponse') or '0') == '1'
        payload['eventtable_send_reset_to_panel'] = (row.get('SendResetToPanel') or '0') == '1'
        payload['eventtable_restore_event_code'] = int(row['RestoreEventCode']) if (row.get('RestoreEventCode') or '').isdigit() else row.get('RestoreEventCode')
        payload['eventtable_update_status'] = (row.get('UpdateStatus') or '').strip()
        payload['eventtable_status_options'] = (row.get('StatusOptions') or '').strip()
    return payload
