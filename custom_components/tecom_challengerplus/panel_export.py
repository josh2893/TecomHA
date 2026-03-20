"""Helpers for importing friendly names from a CTPlus export.panel file."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import logging
from pathlib import Path
from typing import Any

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class PanelExportNames:
    areas: dict[int, str] = field(default_factory=dict)
    inputs: dict[int, str] = field(default_factory=dict)
    doors: dict[int, str] = field(default_factory=dict)
    relays: dict[int, str] = field(default_factory=dict)
    rases: dict[int, str] = field(default_factory=dict)

    @property
    def loaded(self) -> bool:
        return any((self.areas, self.inputs, self.doors, self.relays, self.rases))


def _decode_multi_json(text: str) -> list[Any]:
    dec = json.JSONDecoder()
    idx = 0
    objs: list[Any] = []
    while idx < len(text):
        while idx < len(text) and text[idx].isspace():
            idx += 1
        if idx >= len(text):
            break
        obj, end = dec.raw_decode(text, idx)
        objs.append(obj)
        idx = end
    return objs


def _resolve_path(path_str: str) -> Path:
    path = Path(path_str).expanduser()
    candidates = []
    if path.is_absolute():
        candidates.append(path)
        if str(path).startswith('/homeassistant/'):
            candidates.append(Path('/config') / path.relative_to('/homeassistant'))
    else:
        candidates.extend([
            Path(path_str),
            Path('/config') / path_str,
            Path('/config') / Path(path_str).name,
        ])
    for cand in candidates:
        if cand.exists():
            return cand
    return candidates[0] if candidates else path


def _normalize_name(value: Any) -> str | None:
    if value is None:
        return None
    name = str(value).strip()
    return name or None


def _extract_name(record: list[Any]) -> str | None:
    for item in record:
        if isinstance(item, dict) and 'tc_basedevice' in item:
            return _normalize_name(item['tc_basedevice'].get('devicedesc'))
    return None


def _extract_number(record: list[Any], table_key: str, number_key: str) -> int | None:
    for item in record:
        if isinstance(item, dict) and table_key in item:
            raw = item[table_key].get(number_key)
            try:
                return int(raw)
            except (TypeError, ValueError):
                return None
    return None


def _get_sections(doc: Any) -> dict[str, list[Any]]:
    if not isinstance(doc, dict):
        return {}
    # export.panel has a second top-level object that contains one key with a list of sections
    for value in doc.values():
        if isinstance(value, list):
            sections: dict[str, list[Any]] = {}
            for item in value:
                if isinstance(item, dict) and len(item) == 1:
                    key, section_value = next(iter(item.items()))
                    sections[str(key).lower()] = section_value
            if sections:
                return sections
    return {}


def _extract_named_map(records: list[Any], table_key: str, number_key: str) -> dict[int, str]:
    out: dict[int, str] = {}
    for record in records or []:
        if not isinstance(record, list):
            continue
        number = _extract_number(record, table_key, number_key)
        name = _extract_name(record)
        if number is None or not name:
            continue
        out[number] = name
    return out


def load_panel_export_names(path_str: str) -> PanelExportNames:
    if not path_str:
        return PanelExportNames()

    path = _resolve_path(path_str)
    if not path.exists():
        _LOGGER.warning('Configured panel export not found: %s', path)
        return PanelExportNames()

    try:
        text = path.read_text(encoding='utf-8-sig')
    except UnicodeDecodeError:
        text = path.read_text(encoding='latin-1')

    objs = _decode_multi_json(text)
    if not objs:
        _LOGGER.warning('No JSON documents found in panel export: %s', path)
        return PanelExportNames()

    sections: dict[str, list[Any]] = {}
    for obj in objs:
        sections = _get_sections(obj)
        if sections:
            break

    if not sections:
        _LOGGER.warning('Could not find export sections in panel export: %s', path)
        return PanelExportNames()

    names = PanelExportNames(
        areas=_extract_named_map(sections.get('areas', []), 'tc_area', 'areano'),
        inputs=_extract_named_map(sections.get('inputs', []), 'tc_input', 'inputno'),
        doors=_extract_named_map(sections.get('doors', []), 'tc_door', 'doorno'),
        relays=_extract_named_map(sections.get('relays', []), 'tc_relay', 'relayno'),
        rases=_extract_named_map(sections.get('rases', []), 'tc_ras', 'rasno'),
    )

    _LOGGER.info(
        'Loaded panel export names from %s (areas=%s, inputs=%s, doors=%s, relays=%s, rases=%s)',
        path,
        len(names.areas),
        len(names.inputs),
        len(names.doors),
        len(names.relays),
        len(names.rases),
    )
    return names
