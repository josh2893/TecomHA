"""Central hub: manages transport, parsing, shared state, and services."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import re
import time
import json
from collections import deque
from dataclasses import dataclass
from typing import Callable

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ServiceValidationError

from .const import (
    DOMAIN,
    MODE_CTPLUS,
    MODE_PRINTER,
    TRANSPORT_UDP,
    TRANSPORT_TCP,
    TCP_ROLE_CLIENT,
    TCP_ROLE_SERVER,
    ENC_NONE,
    CONF_MODE,
    CONF_HOST,
    CONF_TRANSPORT,
    CONF_SEND_PORT,
    CONF_LISTEN_PORT,
    CONF_BIND_HOST,
    CONF_TCP_ROLE,
    CONF_POLL_INTERVAL,
    CONF_INPUTS_COUNT,
    CONF_RELAYS_COUNT,
    CONF_DOORS_COUNT,
    CONF_DOOR_FIRST,
    CONF_DOOR_LAST,
    CONF_RELAY_RANGES,
    CONF_AREAS_COUNT,
    CONF_ENCRYPTION_TYPE,
    CONF_INPUT_RANGES,
    CONF_INPUT_MAPPING_MODE,
    INPUT_MAPPING_CTPLUS,
    INPUT_MAPPING_LEGACY_INVERTED,
    INPUT_MAPPING_STATUS_ONLY,
    CONF_SEND_ACKS,
    CONF_SEND_HEARTBEATS,
    CONF_HEARTBEAT_INTERVAL,
    CONF_MIN_SEND_INTERVAL_MS,
    CONF_DOOR_STATUS_MODE,
    CONF_DOOR_STATUS_PER_CYCLE,
    CONF_DOOR_POLL_STARTUP_ONLY,
    CONF_PANEL_EXPORT_PATH,
    CONF_PANEL_EXPORT_RENAME_AREAS,
    CONF_PANEL_EXPORT_RENAME_INPUTS,
    CONF_PANEL_EXPORT_RENAME_DOORS,
    CONF_PANEL_EXPORT_RENAME_RELAYS,
    CONF_PANEL_EXPORT_RENAME_RASES,
    DEFAULT_INPUT_MAPPING_MODE,
    DEFAULT_SEND_ACKS,
    DEFAULT_SEND_HEARTBEATS,
    DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
    DEFAULT_MIN_SEND_INTERVAL_MS,
    DEFAULT_DOOR_STATUS_MODE,
    DEFAULT_DOOR_STATUS_PER_CYCLE,
    DEFAULT_DOOR_POLL_STARTUP_ONLY,
    DEFAULT_PANEL_EXPORT_PATH,
    DEFAULT_PANEL_EXPORT_RENAME_AREAS,
    DEFAULT_PANEL_EXPORT_RENAME_INPUTS,
    DEFAULT_PANEL_EXPORT_RENAME_DOORS,
    DEFAULT_PANEL_EXPORT_RENAME_RELAYS,
    DEFAULT_PANEL_EXPORT_RENAME_RASES,
    DEFAULT_DGP_DOOR_RANGES,
    DEFAULT_RAS_DOOR_RANGES,
    CONF_DGP_DOOR_RANGES,
    CONF_RAS_DOOR_RANGES,
)
from .exceptions import TecomNotSupported, TecomConnectionError
from .transport import TecomTCPPrinterClient, TecomTCPPrinterServer, TecomUDPRaw, TecomTCPRaw
from . import ctplus_protocol as proto
from .ctplus_event_decoder import decode_ctplus_event
from .panel_export import PanelExportNames

_LOGGER = logging.getLogger(__name__)

UpdateCallback = Callable[[], None]


def parse_ranges(spec: str) -> list[tuple[int, int]]:
    """Parse relay range specification like '1-16,21-24,49-56,72'."""
    if not spec:
        return []
    parts = re.split(r"[\n,]+", spec)
    ranges: list[tuple[int, int]] = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        if '-' in p:
            a, b = p.split('-', 1)
            try:
                start = int(a.strip()); end = int(b.strip())
            except ValueError:
                continue
        else:
            try:
                start = end = int(p)
            except ValueError:
                continue
        if start <= 0 or end <= 0:
            continue
        if end < start:
            start, end = end, start
        ranges.append((start, end))
    ranges.sort()
    merged: list[tuple[int, int]] = []
    for s, e in ranges:
        if not merged:
            merged.append((s, e)); continue
        ps, pe = merged[-1]
        if s <= pe + 1:
            merged[-1] = (ps, max(pe, e))
        else:
            merged.append((s, e))
    return merged

def expand_ranges(ranges: list[tuple[int, int]]) -> list[int]:
    ids: list[int] = []
    for s, e in ranges:
        ids.extend(range(s, e + 1))
    seen: set[int] = set()
    out: list[int] = []
    for x in ids:
        if x in seen:
            continue
        seen.add(x)
        out.append(x)
    return out


@dataclass
class TecomState:
    last_event: str | None = None
    last_event_code: int | None = None
    last_event_object: int | None = None
    last_event_raw: str | None = None
    inputs: dict[int, bool] = None
    input_words: dict[int, int] = None
    relays: dict[int, bool] = None
    doors: dict[int, str] = None
    areas: dict[int, str] = None
    area_words: dict[int, int] = None
    door_words: dict[int, int] = None
    ras_status: dict[int, int] = None
    door_secure: dict[int, str] = None
    door_lock: dict[int, str] = None

    def __post_init__(self):
        self.inputs = self.inputs or {}
        self.input_words = self.input_words or {}
        self.relays = self.relays or {}
        self.doors = self.doors or {}
        self.areas = self.areas or {}
        self.area_words = self.area_words or {}
        self.door_words = self.door_words or {}
        self.ras_status = self.ras_status or {}
        self.door_secure = self.door_secure or {}
        self.door_lock = self.door_lock or {}


class TecomHub:
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, panel_export_names: PanelExportNames | None = None) -> None:
        self.hass = hass
        self.entry = entry

        cfg = {**entry.data, **entry.options}

        self.mode: str = cfg.get(CONF_MODE, MODE_CTPLUS)
        self.host: str = cfg.get(CONF_HOST)
        self.transport: str = cfg.get(CONF_TRANSPORT, TRANSPORT_UDP)
        self.send_port: int = int(cfg.get(CONF_SEND_PORT))
        self.listen_port: int = int(cfg.get(CONF_LISTEN_PORT))
        self.bind_host: str = cfg.get(CONF_BIND_HOST, "0.0.0.0")
        self.tcp_role: str = cfg.get(CONF_TCP_ROLE, TCP_ROLE_CLIENT)
        self.poll_interval: int = int(cfg.get(CONF_POLL_INTERVAL, 10))

        # Diagnostics / tuning options (Options Flow).
        self.send_acks: bool = bool(cfg.get(CONF_SEND_ACKS, DEFAULT_SEND_ACKS))
        self.send_heartbeats: bool = bool(cfg.get(CONF_SEND_HEARTBEATS, DEFAULT_SEND_HEARTBEATS))
        self.heartbeat_interval: int = int(cfg.get(CONF_HEARTBEAT_INTERVAL, DEFAULT_HEARTBEAT_INTERVAL_SECONDS))
        self.min_send_interval_ms: int = int(cfg.get(CONF_MIN_SEND_INTERVAL_MS, DEFAULT_MIN_SEND_INTERVAL_MS))
        self.door_status_mode: str = str(cfg.get(CONF_DOOR_STATUS_MODE, DEFAULT_DOOR_STATUS_MODE) or DEFAULT_DOOR_STATUS_MODE)
        self.door_status_per_cycle: int = int(cfg.get(CONF_DOOR_STATUS_PER_CYCLE, DEFAULT_DOOR_STATUS_PER_CYCLE))
        _door_poll_startup_only_cfg = cfg.get(CONF_DOOR_POLL_STARTUP_ONLY, DEFAULT_DOOR_POLL_STARTUP_ONLY)
        if isinstance(_door_poll_startup_only_cfg, str):
            _door_poll_startup_only_cfg = _door_poll_startup_only_cfg.strip().lower() in ("1", "true", "yes", "on")
        self.door_poll_startup_only: bool = bool(_door_poll_startup_only_cfg)

        # Optional CTPlus export.panel import for friendly naming only.
        self.panel_export_path: str = str(cfg.get(CONF_PANEL_EXPORT_PATH, DEFAULT_PANEL_EXPORT_PATH) or "").strip()
        self.panel_export_rename_areas: bool = bool(cfg.get(CONF_PANEL_EXPORT_RENAME_AREAS, DEFAULT_PANEL_EXPORT_RENAME_AREAS))
        self.panel_export_rename_inputs: bool = bool(cfg.get(CONF_PANEL_EXPORT_RENAME_INPUTS, DEFAULT_PANEL_EXPORT_RENAME_INPUTS))
        self.panel_export_rename_doors: bool = bool(cfg.get(CONF_PANEL_EXPORT_RENAME_DOORS, DEFAULT_PANEL_EXPORT_RENAME_DOORS))
        self.panel_export_rename_relays: bool = bool(cfg.get(CONF_PANEL_EXPORT_RENAME_RELAYS, DEFAULT_PANEL_EXPORT_RENAME_RELAYS))
        self.panel_export_rename_rases: bool = bool(cfg.get(CONF_PANEL_EXPORT_RENAME_RASES, DEFAULT_PANEL_EXPORT_RENAME_RASES))
        self.panel_export_names: PanelExportNames = panel_export_names or PanelExportNames()

        self.inputs_count = int(cfg.get(CONF_INPUTS_COUNT, 0))
        # Inputs can be non-contiguous; input_ranges overrides inputs_count when set.
        self.input_ranges_spec = str(cfg.get(CONF_INPUT_RANGES, '') or '').strip()
        if self.input_ranges_spec:
            self.input_poll_ranges = parse_ranges(self.input_ranges_spec)
            self.input_ids = expand_ranges(self.input_poll_ranges)
            self.inputs_max = max(self.input_ids, default=0)
        else:
            self.input_poll_ranges = [(1, self.inputs_count)] if self.inputs_count > 0 else []
            self.input_ids = list(range(1, self.inputs_count + 1)) if self.inputs_count > 0 else []
            self.inputs_max = self.inputs_count
        self.input_mapping_mode: str = str(cfg.get(CONF_INPUT_MAPPING_MODE, DEFAULT_INPUT_MAPPING_MODE) or DEFAULT_INPUT_MAPPING_MODE)

        self.relays_count = int(cfg.get(CONF_RELAYS_COUNT, 0))
        # Relay numbering can be non-contiguous; relay_ranges overrides relays_count when set.
        self.relay_ranges_spec = str(cfg.get(CONF_RELAY_RANGES, '') or '').strip()
        if self.relay_ranges_spec:
            self.relay_poll_ranges = parse_ranges(self.relay_ranges_spec)
            self.relay_ids = expand_ranges(self.relay_poll_ranges)
            self.relays_max = max(self.relay_ids, default=0)
        else:
            self.relay_poll_ranges = [(1, self.relays_count)] if self.relays_count > 0 else []
            self.relay_ids = list(range(1, self.relays_count + 1)) if self.relays_count > 0 else []
            self.relays_max = self.relays_count
        # Doors can be offset (e.g. 1-16 are RAS, 17+ are access doors). Configure by first/last inclusive.
        self.door_first = int(cfg.get(CONF_DOOR_FIRST, 1) or 1)
        self.door_last = int(cfg.get(CONF_DOOR_LAST, 0) or 0)
        if self.door_last <= 0:
            # Backward compatibility: derive from legacy doors_count if present.
            legacy_dc = int(cfg.get(CONF_DOORS_COUNT, 0) or 0)
            if legacy_dc > 0:
                self.door_last = self.door_first + legacy_dc - 1
        self.door_ids = list(range(self.door_first, self.door_last + 1)) if self.door_last >= self.door_first and self.door_last > 0 else []
        self.doors_count = len(self.door_ids)
        self.doors_max = self.door_last if self.door_last > 0 else max(self.door_ids, default=0)
        self.areas_count = int(cfg.get(CONF_AREAS_COUNT, 0))

        self.encryption_type = cfg.get(CONF_ENCRYPTION_TYPE, ENC_NONE)

        self.state = TecomState()
        self._area_override_until: dict[int, float] = {}
        # When a live door event arrives, prefer it briefly over polled replies so
        # queued/stale poll responses do not make door contacts appear to lag.
        self._door_event_prefer_until: dict[int, float] = {}

        self._listeners: set[UpdateCallback] = set()

        self._transport_obj = None  # runtime transport
        self._udp_last_peer = None  # last UDP peer (ip, port)
        self._seq_out = 1
        self._poll_task: asyncio.Task | None = None
        self._heartbeat_task: asyncio.Task | None = None
        self._tcp_buf: bytes = b""  # only used for TCP
        self._door_status_inited: bool = False
        self._dgp_door_poll_idx: int = 0
        self._type_offset: int = 0
        self._type_offset_known: bool = False
        self._send_lock = asyncio.Lock()
        self._last_send_monotonic: float = 0.0
        self._min_send_interval: float = max(0.0, float(self.min_send_interval_ms) / 1000.0)  # seconds
        # Door selection: DGP doors (17+) can be specified as ranges, e.g. 17-20,21-24,33-36.
        self.dgp_door_ranges_spec = str(cfg.get(CONF_DGP_DOOR_RANGES, DEFAULT_DGP_DOOR_RANGES) or '').strip()
        if self.dgp_door_ranges_spec:
            self.dgp_door_ranges = parse_ranges(self.dgp_door_ranges_spec)
            self.dgp_door_ids = [d for d in expand_ranges(self.dgp_door_ranges) if d >= 17]
        else:
            self.dgp_door_ranges = [(self.door_first, self.door_last)] if self.door_last >= self.door_first and self.door_last > 0 else []
            self.dgp_door_ids = [d for d in range(self.door_first, self.door_last + 1) if d >= 17] if self.dgp_door_ranges else []

        # RAS / keypad / single door controller selection (doors 1-16). e.g. 3,6,8 or 1-16
        self.ras_door_ranges_spec = str(cfg.get(CONF_RAS_DOOR_RANGES, DEFAULT_RAS_DOOR_RANGES) or '').strip()
        if self.ras_door_ranges_spec:
            self.ras_door_ranges = parse_ranges(self.ras_door_ranges_spec)
            self.ras_door_ids = [d for d in expand_ranges(self.ras_door_ranges) if 1 <= d <= 16]
        else:
            self.ras_door_ranges = []
            self.ras_door_ids = []

        # Combined 'doors' list used by platforms (DGP doors + RAS doors).
        self.door_ids = self.dgp_door_ids + self.ras_door_ids

        # Debug ring buffer (last N frames).
        self._debug_frames = deque(maxlen=500)
        # Retransmitted panel events can repeat if the ACK is not seen quickly enough.
        # Keep a short cache so duplicates do not flood the HA event bus.
        self._recent_event_keys: dict[tuple[int, str], float] = {}
        # Limited queue recovery for clearly stuck retransmits only.
        self._event_repeat_counts: dict[tuple[int, str], int] = {}
        self._retrieve_events_task: asyncio.Task | None = None
        self._last_retrieve_events_monotonic: float = 0.0
        self._last_retrieve_events_key: tuple[int, str] | None = None
        # Per-input targeted refresh tasks. CTPlus issues a narrow input status query
        # right after 0x96/0x97 input events on the active computer comms path.
        # Doing the same helps bursts of egress+door events keep flowing without using
        # the more disruptive global "Retrieve events" command.
        self._input_refresh_tasks: dict[int, asyncio.Task] = {}
        self._last_input_refresh_monotonic: dict[int, float] = {}
        self._door_refresh_tasks: dict[int, asyncio.Task] = {}
        self._last_door_refresh_monotonic: dict[int, float] = {}
        self._poll_backoff_until: float = 0.0
        # On connect/reload, let the panel stream any queued events first before we
        # start broad polling. This keeps host-initiated status recalls from competing
        # with backlog delivery/ACKs on the command queue.
        self._startup_backlog_drain: bool = True
        self._startup_backlog_started_monotonic: float = 0.0
        self._last_unsolicited_event_monotonic: float = 0.0
        self._startup_backlog_quiet_seconds: float = 2.5
        self._startup_backlog_max_seconds: float = 20.0
        # Quiet-mode recovery: when the panel starts retrying the same queue-head event
        # or returns short error-style replies, stop host-initiated recalls for a while and
        # let only heartbeats + immediate panel ACKs flow. This matches CTPlus/ARES style
        # behaviour much more closely than continuing to poll through the retry storm.
        self._quiet_mode_until: float = 0.0
        self._quiet_reason: str | None = None
        self._quiet_reinit_pending: bool = False
        self._last_panel_event_seq: int | None = None
        self._panel_retry_event_threshold: int = 3
        self._quiet_mode_seconds: float = max(90.0, float(self.poll_interval) * 3.0)


    def contact_name(self, number: int, default: str, *, kind: str = "door") -> str:
        """Return a friendly display name for contact-style entities.

        Door and RAS contact sensors should use the imported friendly base name
        when available, while still keeping the explicit "Contact" suffix so the
        entity purpose stays obvious in Home Assistant.
        """

        suffix = " Contact"
        default_str = str(default)
        if default_str.endswith(suffix):
            base_default = default_str[: -len(suffix)]
        else:
            base_default = default_str

        base_name = self.entity_name(kind, number, base_default)
        if base_name.endswith(suffix):
            return base_name
        return f"{base_name}{suffix}"

    def entity_name(self, kind: str, number: int, default: str) -> str:
        """Return a friendly display name for an entity.

        When an imported CTPlus export.panel name is available and the matching
        rename option is enabled, we keep the Home Assistant UI organised by
        prefixing the imported name with the object type and number. This keeps
        alphabetical sorting aligned with the panel numbering, for example:
        ``Door 17 - Front Door - 17B`` or ``Input 19 - Front Door Egress - 17B``.

        Only entities that the integration has already loaded are renamed. Entity
        IDs / unique IDs remain unchanged.
        """

        kind = str(kind or '').lower()
        mapping: dict[int, str] | None = None
        enabled = False
        label: str | None = None

        if kind == 'area':
            mapping = self.panel_export_names.areas
            enabled = self.panel_export_rename_areas
            label = 'Area'
        elif kind == 'input':
            mapping = self.panel_export_names.inputs
            enabled = self.panel_export_rename_inputs
            label = 'Input'
        elif kind == 'door':
            mapping = self.panel_export_names.doors
            enabled = self.panel_export_rename_doors
            label = 'Door'
        elif kind == 'relay':
            mapping = self.panel_export_names.relays
            enabled = self.panel_export_rename_relays
            label = 'Relay'
        elif kind == 'ras':
            mapping = self.panel_export_names.rases
            enabled = self.panel_export_rename_rases
            label = 'RAS'

        if enabled and mapping and label:
            name = mapping.get(int(number))
            if name:
                prefix = f"{label} {int(number)}"
                lowered = name.lower()
                if lowered == prefix.lower() or lowered.startswith(prefix.lower() + " -"):
                    return name
                return f"{prefix} - {name}"
        return default

    def _next_seq(self) -> int:
        self._seq_out = (self._seq_out + 1) & 0xFF
        if self._seq_out == 0:
            self._seq_out = 1
        return self._seq_out

    def _input_state_from_status(self, raw: int) -> bool:
        """Return HA boolean state from an input status byte.

        CTPlus event/status material consistently points to bit 0x20 meaning the input is
        sealed/normal. In HA we surface inputs as ON when active/tripped, so sealed maps to
        OFF and unsealed maps to ON.
        """
        return not bool(int(raw) & 0x20)

    def _input_event_state(self, code: int) -> bool | None:
        """Return HA boolean state for input event codes 0x96/0x97.

        Modes:
          - ctplus: 0x96=Unsealed/ON, 0x97=Sealed/OFF
          - legacy_inverted: preserve older 2.x behaviour
          - status_only: do not trust event polarity; wait for targeted status refresh
        """
        if self.input_mapping_mode == INPUT_MAPPING_STATUS_ONLY:
            return None
        if self.input_mapping_mode == INPUT_MAPPING_LEGACY_INVERTED:
            if code == 0x96:
                return False
            if code == 0x97:
                return True
            return None
        if code == 0x96:
            return True
        if code == 0x97:
            return False
        return None

    def input_state_source(self, number: int) -> str:
        raw = self.state.input_words.get(number)
        if raw is not None:
            return "raw_status_bit_0x20"
        if self.input_mapping_mode == INPUT_MAPPING_STATUS_ONLY:
            return "event_refresh_pending"
        return f"event_mapping:{self.input_mapping_mode}"


    def add_listener(self, cb: UpdateCallback) -> Callable[[], None]:
        self._listeners.add(cb)

        def _unsub():
            self._listeners.discard(cb)

        return _unsub

    @callback
    def _notify(self) -> None:
        for cb in list(self._listeners):
            try:
                cb()
            except Exception:  # pragma: no cover
                _LOGGER.exception("Listener error")

    def _in_quiet_mode(self) -> bool:
        return asyncio.get_running_loop().time() < self._quiet_mode_until

    def _cancel_pending_refresh_tasks(self) -> None:
        for task in list(self._input_refresh_tasks.values()):
            task.cancel()
        self._input_refresh_tasks.clear()
        for task in list(self._door_refresh_tasks.values()):
            task.cancel()
        self._door_refresh_tasks.clear()
        if self._retrieve_events_task and not self._retrieve_events_task.done():
            self._retrieve_events_task.cancel()
        self._retrieve_events_task = None

    def _enter_quiet_mode(self, reason: str, *, duration: float | None = None, reinitialize: bool = True) -> None:
        loop = asyncio.get_running_loop()
        now = loop.time()
        quiet_for = max(15.0, float(duration if duration is not None else self._quiet_mode_seconds))
        until = now + quiet_for
        self._quiet_mode_until = max(self._quiet_mode_until, until)
        self._quiet_reason = reason
        self._quiet_reinit_pending = self._quiet_reinit_pending or reinitialize
        self._poll_backoff_until = max(self._poll_backoff_until, self._quiet_mode_until)
        self._cancel_pending_refresh_tasks()
        self.state.last_event = f"Quiet mode: {reason}"
        self._debug_frames.append({
            'ts': time.time(),
            'dir': 'note',
            'peer': str(self._udp_last_peer),
            'hex': '',
            'note': f'quiet_mode:{reason}',
        })
        self._notify()

    async def async_start(self) -> None:
        """Start transport and register services."""
        if self.mode == MODE_CTPLUS and self.encryption_type != ENC_NONE:
            raise TecomNotSupported(
                "Encryption is configured but not implemented yet; set encryption to None"
            )

        await self._start_transport()

        if self.mode == MODE_CTPLUS:
            await self.async_reinitialize_session(log_errors=False)

            # Start heartbeats immediately so the panel keeps the path alive, but hold
            # broad polling until queued events have had a chance to drain first.
            self._startup_backlog_started_monotonic = asyncio.get_running_loop().time()
            self._last_unsolicited_event_monotonic = self._startup_backlog_started_monotonic
            self._startup_backlog_drain = True

            self._poll_task = asyncio.create_task(self._poll_loop())
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
    async def async_stop(self) -> None:
        if self._poll_task:
            self._poll_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._poll_task
            self._poll_task = None
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._heartbeat_task
            self._heartbeat_task = None

        for task in list(self._input_refresh_tasks.values()):
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._input_refresh_tasks.clear()
        for task in list(self._door_refresh_tasks.values()):
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._door_refresh_tasks.clear()

        if self._transport_obj:
            await self._transport_obj.async_stop()
            self._transport_obj = None

    async def _start_transport(self) -> None:
        if self.mode == MODE_PRINTER:
            if self.transport == TRANSPORT_UDP:
                self._transport_obj = TecomUDPRaw(
                    hass=self.hass,
                    bind_host=self.bind_host,
                    bind_port=self.listen_port,
                    remote_host=self.host,
                    remote_port=self.send_port,
                    on_datagram=self._on_printer_datagram,
                )
                await self._transport_obj.async_start()
                _LOGGER.info("Started Tecom printer listener (udp)")
                return

            if self.tcp_role == TCP_ROLE_SERVER:
                self._transport_obj = TecomTCPPrinterServer(
                    hass=self.hass,
                    bind_host=self.bind_host,
                    bind_port=self.listen_port,
                    on_line=self._on_printer_line,
                )
            else:
                self._transport_obj = TecomTCPPrinterClient(
                    hass=self.hass,
                    host=self.host,
                    port=self.send_port,
                    on_line=self._on_printer_line,
                )
            await self._transport_obj.async_start()
            _LOGGER.info("Started Tecom printer listener (%s)", self.tcp_role)
            return

        # CTPlus / management
        if self.transport == TRANSPORT_UDP:
            self._transport_obj = TecomUDPRaw(
                hass=self.hass,
                bind_host=self.bind_host,
                bind_port=self.listen_port,
                remote_host=self.host,
                remote_port=self.send_port,
                on_datagram=self._on_ctplus_datagram,
            )
        else:
            self._transport_obj = TecomTCPRaw(
                hass=self.hass,
                host=self.host,
                port=self.send_port,
                role=self.tcp_role,
                bind_host=self.bind_host,
                bind_port=self.listen_port,
                on_bytes=self._on_ctplus_bytes,
            )
        await self._transport_obj.async_start()
        _LOGGER.info("Started Tecom CTPlus transport (%s/%s)", self.transport, self.tcp_role)

    def _register_services(self) -> None:
        async def async_send_raw(call):
            hex_str = (call.data.get("hex") or "").replace(" ", "")
            if not hex_str:
                raise ServiceValidationError("hex is required")
            try:
                payload = bytes.fromhex(hex_str)
            except ValueError as e:
                raise ServiceValidationError(f"Invalid hex: {e}") from e
            await self.async_send_bytes(payload)

        if not self.hass.services.has_service(DOMAIN, "send_raw_hex"):
            self.hass.services.async_register(DOMAIN, "send_raw_hex", async_send_raw)

    async def async_send_bytes(self, payload: bytes, addr=None) -> None:  # noqa: ANN001
        if not self._transport_obj:
            raise TecomConnectionError("Transport not started")
        if addr is not None and hasattr(self._transport_obj, 'async_sendto'):
            await self._transport_obj.async_sendto(payload, addr)
        else:
            await self._transport_obj.async_send(payload)

    async def _send_frame(self, frame: proto.Frame) -> None:
        payload = frame.to_bytes()
        self._debug_frames.append({'ts': time.time(), 'dir': 'tx', 'peer': str(self._udp_last_peer), 'hex': payload.hex()})
        await self.async_send_bytes(payload)

    async def _send_frame_paced(self, frame: proto.Frame) -> None:
        """Send a host-initiated CTPlus frame with pacing.

        We intentionally do *not* use this for ACKs to panel-originated 0x40 frames, because
        those should be returned immediately. Everything else (polling, control, heartbeat,
        startup/session init) is paced so door-status polling behaves more like CTPlus.
        """
        async with self._send_lock:
            if self._min_send_interval > 0:
                now = asyncio.get_running_loop().time()
                wait_for = (self._last_send_monotonic + self._min_send_interval) - now
                if wait_for > 0:
                    await asyncio.sleep(wait_for)
            await self._send_frame(frame)
            self._last_send_monotonic = asyncio.get_running_loop().time()

    async def _send_command(self, body: bytes, type_offset: int | None = None, *, bypass_quiet: bool = False) -> None:
        if self._in_quiet_mode() and not bypass_quiet:
            self._debug_frames.append({
                'ts': time.time(),
                'dir': 'note',
                'peer': str(self._udp_last_peer),
                'hex': body.hex(),
                'note': 'command_suppressed_quiet_mode',
            })
            return
        seq = self._next_seq()
        # If panel type offset isn't known yet, send both variants (0x00 and 0x40).
        if type_offset is None and not self._type_offset_known:
            await self._send_frame_paced(proto.Frame(proto.TYPE_COMMAND, seq, body=body, type_offset=0x00))
            await self._send_frame_paced(proto.Frame(proto.TYPE_COMMAND, seq, body=body, type_offset=0x40))
            return
        if type_offset is None:
            type_offset = self._type_offset
        await self._send_frame_paced(proto.Frame(proto.TYPE_COMMAND, seq, body=body, type_offset=type_offset))
    async def _heartbeat_loop(self) -> None:
        """Send CTPlus keepalive frequently so panel does not declare path down."""
        while True:
            try:
                if not self.send_heartbeats:
                    await asyncio.sleep(1)
                    continue

                if not self._type_offset_known:
                    await self._send_frame_paced(proto.build_heartbeat(self._next_seq(), type_offset=0x00))
                    await self._send_frame_paced(proto.build_heartbeat(self._next_seq(), type_offset=0x40))
                else:
                    await self._send_frame_paced(proto.build_heartbeat(self._next_seq(), type_offset=self._type_offset))

                await asyncio.sleep(max(1, int(self.heartbeat_interval or DEFAULT_HEARTBEAT_INTERVAL_SECONDS)))
            except asyncio.CancelledError:
                return
            except Exception:
                _LOGGER.exception("Heartbeat loop error")
    async def _poll_loop(self) -> None:
        while True:
            try:
                # When the panel is actively streaming queued events, back off host-initiated
                # polling briefly so we do not occupy the command queue and starve event delivery.
                now = asyncio.get_running_loop().time()

                if now < self._quiet_mode_until:
                    await asyncio.sleep(min(1.0, self._quiet_mode_until - now))
                    continue

                if self._quiet_reinit_pending:
                    try:
                        await self.async_reinitialize_session(log_errors=False)
                    except Exception:
                        _LOGGER.debug("Quiet-mode reinitialisation failed (will retry)", exc_info=True)
                    else:
                        self._quiet_reinit_pending = False
                        self._startup_backlog_started_monotonic = asyncio.get_running_loop().time()
                        self._last_unsolicited_event_monotonic = self._startup_backlog_started_monotonic
                        self._startup_backlog_drain = True
                    await asyncio.sleep(max(2.0, self._startup_backlog_quiet_seconds))
                    continue

                if self._startup_backlog_drain:
                    quiet_for = now - self._last_unsolicited_event_monotonic
                    drain_for = now - self._startup_backlog_started_monotonic
                    if drain_for < self._startup_backlog_max_seconds and quiet_for < self._startup_backlog_quiet_seconds:
                        await asyncio.sleep(min(0.5, self._startup_backlog_quiet_seconds - quiet_for))
                        continue
                    try:
                        await self._async_initial_sync()
                    except Exception:
                        _LOGGER.debug("Initial sync after backlog drain failed (will retry)", exc_info=True)
                    else:
                        self._startup_backlog_drain = False
                    await asyncio.sleep(self.poll_interval)
                    continue

                if now < self._poll_backoff_until:
                    await asyncio.sleep(min(0.5, self._poll_backoff_until - now))
                    continue

                # Poll first, then sleep (so state updates quickly after reload/startup).
                if getattr(self, 'input_poll_ranges', None):
                    for rs, re_ in self.input_poll_ranges:
                        await self.async_request_inputs(rs, re_)

                if getattr(self, 'relay_poll_ranges', None):
                    for rs, re_ in self.relay_poll_ranges:
                        await self.async_request_relays(rs, re_)

                if getattr(self, 'areas_count', 0) and self.areas_count > 0:
                    await self.async_request_areas(1, self.areas_count)
                if getattr(self, 'ras_door_ids', None):
                    for ras in self.ras_door_ids:
                        await self._send_command(proto.cmd_request_ras_status(ras))

                if not getattr(self, "door_poll_startup_only", False):
                    await self.async_request_doors()

                await asyncio.sleep(self.poll_interval)
            except asyncio.CancelledError:
                return
            except Exception:
                _LOGGER.exception("Poll loop error")
    async def async_request_inputs(self, start: int, end: int) -> None:
        max_chunk = 128
        cur = start
        while cur <= end:
            chunk_end = min(end, cur + max_chunk - 1)
            await self._send_command(proto.cmd_request_input_status(cur, chunk_end))
            cur = chunk_end + 1

    async def async_request_relays(self, start: int, end: int) -> None:
        max_chunk = 128
        cur = start
        while cur <= end:
            chunk_end = min(end, cur + max_chunk - 1)
            await self._send_command(proto.cmd_request_relay_status(cur, chunk_end))
            cur = chunk_end + 1

    # -------------------------
    # Printer mode parsing
    # -------------------------


    async def async_request_areas(self, start: int, end: int) -> None:
        """Request Area status in blocks (CTPlus observed: up to 4 areas per request)."""
        cur = start
        while cur <= end:
            count = min(4, end - cur + 1)
            await self._send_command(proto.cmd_request_area_status(cur, count))
            cur += count

    async def _async_initial_sync(self) -> None:
        """Perform one broad status sync after backlog drain / on demand.

        When "door poll startup only" is enabled, the one-shot startup door sweep needs to be
        more patient than the normal continuous round-robin loop. In practice, firing all door
        recalls in one burst can leave later doors unknown even though the panel/path is healthy.
        So for startup-only mode we do a few paced passes over the still-unknown DGP doors until
        they populate or we hit a small retry limit.
        """
        if getattr(self, "input_poll_ranges", None):
            for rs, re_ in self.input_poll_ranges:
                await self.async_request_inputs(rs, re_)

        if getattr(self, "relay_poll_ranges", None):
            for rs, re_ in self.relay_poll_ranges:
                await self.async_request_relays(rs, re_)

        if getattr(self, "areas_count", 0) and self.areas_count > 0:
            await self.async_request_areas(1, self.areas_count)

        if getattr(self, 'ras_door_ids', None):
            for ras in self.ras_door_ids:
                await self._send_command(proto.cmd_request_ras_status(ras))

        if getattr(self, "door_poll_startup_only", False):
            await self._async_startup_door_sweep()
        else:
            await self.async_request_doors(force_all=True)

    async def _async_startup_door_sweep(self) -> None:
        """Populate DGP door states once at startup without relying on later polling.

        We intentionally poll in small paced passes instead of one large burst so the panel's
        command queue has time to return every door status. This avoids the common symptom where
        Door 17/18 populate but later doors stay Unknown after reload.
        """
        if not getattr(self, "dgp_door_ids", None):
            return

        # Ensure the observed door-status init has been sent before any per-door recall.
        if not self._door_status_inited:
            await self._send_command(proto.cmd_door_status_init())
            self._door_status_inited = True

        batch_size = max(1, min(int(self.door_status_per_cycle or 1), len(self.dgp_door_ids)))
        max_passes = max(3, len(self.dgp_door_ids) * 2)

        for _ in range(max_passes):
            unknown = [door for door in self.dgp_door_ids if self.state.door_words.get(door) is None]
            if not unknown:
                break

            for idx in range(0, len(unknown), batch_size):
                batch = unknown[idx:idx + batch_size]
                for door in batch:
                    await self._send_command(proto.cmd_request_door_status_wrapped(door))
                # Give the panel a moment to answer this small batch before asking for more.
                await asyncio.sleep(max(0.35, self._min_send_interval * 3.0))

            # Allow trailing replies from the last batch to arrive before the next pass.
            await asyncio.sleep(max(0.6, self._min_send_interval * 6.0))

    async def async_request_doors(self, force_all: bool = False) -> None:
        """Request status for DGP doors (17+) only.

        Behavior:
          - startup / explicit full sync: poll every configured DGP door once
          - all_each_cycle: poll every DGP door every cycle
          - round_robin: prioritise still-unknown doors first, then resume round-robin

        The goal is to populate door contacts promptly after HA reloads without turning every
        cycle into a full burst of door requests.
        """
        if not getattr(self, "dgp_door_ids", None):
            return
        if not self._door_status_inited:
            await self._send_command(proto.cmd_door_status_init())
            self._door_status_inited = True

        doors_to_poll: list[int] = []
        mode = (self.door_status_mode or DEFAULT_DOOR_STATUS_MODE).lower()
        per = max(1, int(self.door_status_per_cycle or 1))
        now = asyncio.get_running_loop().time()

        def _eligible(door: int) -> bool:
            if force_all:
                return True
            return now >= self._door_event_prefer_until.get(door, 0.0)

        eligible_doors = [door for door in self.dgp_door_ids if _eligible(door)]
        if not eligible_doors and not force_all:
            return

        if force_all or mode == "all_each_cycle":
            doors_to_poll = list(eligible_doors if not force_all else self.dgp_door_ids)
        else:
            unknown = [door for door in eligible_doors if self.state.door_words.get(door) is None]
            if unknown:
                doors_to_poll.extend(unknown[:per])

            while len(doors_to_poll) < min(per, len(eligible_doors)):
                door = self.dgp_door_ids[self._dgp_door_poll_idx % len(self.dgp_door_ids)]
                self._dgp_door_poll_idx = (self._dgp_door_poll_idx + 1) % len(self.dgp_door_ids)
                if door in doors_to_poll or door not in eligible_doors:
                    continue
                doors_to_poll.append(door)

        for door in doors_to_poll:
            await self._send_command(proto.cmd_request_door_status_wrapped(door))

    def _decode_door_contact_state(self, status: int) -> str:
        """Best-effort contact decoding from observed CTPlus door status words.

        Observations from supplied captures so far:
          - 0x0000  => physically closed / secure
          - 0xC010  => physically closed while not secure/locked
          - 0xC090  => physically open

        The 0x0080 bit appears to track contact-open state, so keep the mapping narrow and
        contact-focused here. Raw words are still preserved separately for diagnostics/UI.
        """
        return "open" if (status & 0x0080) else "closed"
    def _on_printer_datagram(self, data: bytes, addr=None) -> None:  # noqa: ANN001
        try:
            text = data.decode("utf-8", errors="ignore")
        except Exception:
            return
        for line in [ln.strip() for ln in text.splitlines() if ln.strip()]:
            self._on_printer_line(line)

    def _on_printer_line(self, line: str) -> None:
        self.state.last_event = line
        self.hass.bus.async_fire(f"{DOMAIN}_event", {"raw": line})
        self._notify()

    # -------------------------
    # CTPlus parsing
    # -------------------------

    def _scan_ctplus_frames(self, buf: bytes) -> tuple[list[proto.Frame], bytes]:
        """Extract one or more CTPlus frames from a bytes buffer.

        CTPlus is framed by a SYNC byte (0x5E) + CRC16/Modbus.
        Some UDP datagrams (and TCP reads) can contain multiple frames.
        Returns (frames, remaining_bytes).
        """
        if not buf:
            return [], b""

        frames: list[proto.Frame] = []
        i = 0
        sync = bytes([proto.SYNC])

        while True:
            j = buf.find(sync, i)
            if j < 0:
                # No more sync bytes; drop everything before i (already consumed)
                return frames, buf[i:]

            found = False
            # Minimum frame length is 7 (sync + 4 header bytes + crc16)
            # Try progressively longer slices until CRC matches.
            max_end = min(len(buf), j + 2048)
            for end in range(j + 7, max_end + 1):
                fr = proto.parse_frame(buf[j:end])
                if fr:
                    frames.append(fr)
                    i = end
                    found = True
                    break

            if not found:
                # Keep from the sync byte onward (could be a partial frame in TCP buffer)
                return frames, buf[j:]

    def _on_ctplus_bytes(self, data: bytes) -> None:
        # TCP support via sync+CRC scan (supports multiple frames per read)
        if not data:
            return
        self._tcp_buf += data
        frames, rem = self._scan_ctplus_frames(self._tcp_buf)
        self._tcp_buf = rem
        for fr in frames:
            self._handle_ctplus_frame(fr)

    def _on_ctplus_datagram(self, data: bytes, addr=None) -> None:  # noqa: ANN001
        self._debug_frames.append({'ts': time.time(), 'dir': 'rx', 'peer': str(addr), 'hex': data.hex()})
        if addr is not None:
            self._udp_last_peer = addr
        # UDP datagrams can contain multiple CTPlus frames.
        frames, rem = self._scan_ctplus_frames(data)
        if not frames:
            self.state.last_event = f"RAW {data.hex()}"
            self.hass.bus.async_fire(f"{DOMAIN}_raw", {"hex": data.hex(), "len": len(data)})
            self._notify()
            return

        for fr in frames:
            # Track CTPlus msg_type variant (some panels use +0x40 type bytes).
            off = getattr(fr, 'type_offset', 0)
            if off != self._type_offset:
                self._type_offset = off
            self._type_offset_known = True
            self._handle_ctplus_frame(fr)

        # If there's leftover bytes that didn't parse, surface them for troubleshooting.
        if rem and rem != data:
            self.hass.bus.async_fire(f"{DOMAIN}_raw", {"hex": rem.hex(), "len": len(rem)})

    def _send_panel_ack_immediate(self, fr: proto.Frame) -> None:
        """Send a panel ACK immediately for unsolicited 0x40 frames.

        CTPlus/ARES expect these ACKs to go out as quickly as possible so the panel
        retires the current queue item and keeps the comms path flowing. This applies
        to both UDP and TCP transports.
        """
        if not self.send_acks:
            return
        payload = proto.build_ack(
            fr.seq,
            has_ff=getattr(fr, 'has_ff', False),
            type_offset=getattr(fr, 'type_offset', self._type_offset),
        ).to_bytes()
        peer = self._udp_last_peer
        self._debug_frames.append({'ts': time.time(), 'dir': 'tx', 'peer': str(peer), 'hex': payload.hex(), 'note': 'panel_ack'})
        try:
            if peer is not None and hasattr(self._transport_obj, 'sendto_nowait'):
                self._transport_obj.sendto_nowait(payload, peer)
                return
            if hasattr(self._transport_obj, 'send_nowait'):
                self._transport_obj.send_nowait(payload)
                return
        except Exception as err:  # pragma: no cover - defensive logging
            _LOGGER.debug("Immediate panel ACK failed, falling back to async send: %s", err)

        asyncio.create_task(self.async_send_bytes(payload, addr=peer if peer is not None else None))




    def _schedule_input_status_refresh(self, input_no: int, *, delay: float = 0.25) -> None:
        """Send a narrow input status query shortly after an input event.

        Debounced/cooldown behaviour is important: during a backlog drain the panel can emit
        many 0x96/0x97 input events in a short burst. If we immediately fire a refresh for each
        one, we can occupy the command queue and make later queued events appear to stall.
        """
        if self.mode != MODE_CTPLUS or input_no <= 0 or self._in_quiet_mode():
            return
        now = asyncio.get_running_loop().time()
        self._poll_backoff_until = max(self._poll_backoff_until, now + 1.5)
        last = self._last_input_refresh_monotonic.get(input_no, 0.0)
        if now - last < 1.0:
            return
        task = self._input_refresh_tasks.get(input_no)
        if task and not task.done():
            return

        async def _runner() -> None:
            try:
                if delay > 0:
                    await asyncio.sleep(delay)
                while asyncio.get_running_loop().time() < self._poll_backoff_until:
                    await asyncio.sleep(min(0.1, self._poll_backoff_until - asyncio.get_running_loop().time()))
                await self._send_command(proto.cmd_request_input_status(input_no, input_no))
                self._last_input_refresh_monotonic[input_no] = asyncio.get_running_loop().time()
                self._debug_frames.append({
                    'ts': time.time(),
                    'dir': 'note',
                    'peer': str(self._udp_last_peer),
                    'hex': '',
                    'note': f'input_refresh:{input_no}',
                })
            except asyncio.CancelledError:
                raise
            except Exception:
                _LOGGER.debug("input status refresh failed for input %s", input_no, exc_info=True)
            finally:
                self._input_refresh_tasks.pop(input_no, None)

        self._input_refresh_tasks[input_no] = asyncio.create_task(_runner())

    def _schedule_door_status_refresh(self, door_no: int, *, delay: float = 0.25) -> None:
        """Coalesced targeted door status refresh after door/access events."""
        if self.mode != MODE_CTPLUS or door_no <= 0 or self._in_quiet_mode():
            return
        now = asyncio.get_running_loop().time()
        self._poll_backoff_until = max(self._poll_backoff_until, now + 1.5)
        last = self._last_door_refresh_monotonic.get(door_no, 0.0)
        if now - last < 1.0:
            return
        task = self._door_refresh_tasks.get(door_no)
        if task and not task.done():
            return

        async def _runner() -> None:
            try:
                if delay > 0:
                    await asyncio.sleep(delay)
                while asyncio.get_running_loop().time() < self._poll_backoff_until:
                    await asyncio.sleep(min(0.1, self._poll_backoff_until - asyncio.get_running_loop().time()))
                if door_no >= 17:
                    await self._send_command(proto.cmd_request_door_status_wrapped(door_no))
                else:
                    await self._send_command(proto.cmd_request_ras_status(door_no))
                self._last_door_refresh_monotonic[door_no] = asyncio.get_running_loop().time()
                self._debug_frames.append({
                    'ts': time.time(),
                    'dir': 'note',
                    'peer': str(self._udp_last_peer),
                    'hex': '',
                    'note': f'door_refresh:{door_no}',
                })
            except asyncio.CancelledError:
                raise
            except Exception:
                _LOGGER.debug("door status refresh failed for door %s", door_no, exc_info=True)
            finally:
                self._door_refresh_tasks.pop(door_no, None)

        self._door_refresh_tasks[door_no] = asyncio.create_task(_runner())

    def _schedule_retrieve_events(self, *, delay: float = 0.05, reason: str = "event") -> None:
        """Ask the panel for the next queued event, like CTPlus "Retrieve events".

        This is used as a queue-drain nudge after live 0x40 events. Captures show CTPlus
        issuing 07 03 0E 03 03 on the same comms path to pull/advance queued events.
        Without this, some panels keep retransmitting the same queued access/door event even
        though the immediate 0x73/0xB3 ACK is on the wire.
        """
        if self.mode != MODE_CTPLUS or self._in_quiet_mode():
            return
        if self._retrieve_events_task and not self._retrieve_events_task.done():
            return

        async def _runner() -> None:
            try:
                if delay > 0:
                    await asyncio.sleep(delay)
                now = asyncio.get_running_loop().time()
                cooldown = max(10.0, float(self.poll_interval) * 2.0, self._min_send_interval * 10.0)
                wait_for = (self._last_retrieve_events_monotonic + cooldown) - now
                if wait_for > 0:
                    await asyncio.sleep(wait_for)
                await self._send_command(proto.cmd_retrieve_events())
                self._last_retrieve_events_monotonic = asyncio.get_running_loop().time()
                self._debug_frames.append({'ts': time.time(), 'dir': 'note', 'peer': str(self._udp_last_peer), 'hex': '', 'note': f'retrieve_events:{reason}'})
            except asyncio.CancelledError:
                raise
            except Exception:
                _LOGGER.debug("retrieve_events command failed", exc_info=True)
            finally:
                self._retrieve_events_task = None

        self._retrieve_events_task = asyncio.create_task(_runner())

    def _note_panel_event_retransmit(self, fr: proto.Frame) -> int:
        """Track repeated identical panel events and return the current seen count."""
        key = (fr.seq, fr.body.hex())
        now = time.monotonic()
        for k, until in list(self._recent_event_keys.items()):
            if until <= now:
                self._recent_event_keys.pop(k, None)
                self._event_repeat_counts.pop(k, None)
        if key in self._recent_event_keys:
            self._event_repeat_counts[key] = self._event_repeat_counts.get(key, 1) + 1
            return self._event_repeat_counts[key]
        self._recent_event_keys[key] = now + max(20.0, float(self.poll_interval) * 4.0)
        self._event_repeat_counts[key] = 1
        return 1


    def _is_duplicate_panel_event(self, fr: proto.Frame) -> bool:
        """Return True when an unsolicited panel event is a recent retransmit."""
        return self._note_panel_event_retransmit(fr) > 1

    def _handle_ctplus_frame(self, fr: proto.Frame) -> None:
        if fr.msg_type == 0x49:
            self._enter_quiet_mode("panel returned 0x49 for a host recall", duration=max(60.0, float(self.poll_interval) * 2.0))
            self.state.last_event = f"Panel 0x49 {fr.body.hex()}"
            self._notify()
            return

        if fr.msg_type == proto.TYPE_EVENT_OR_DATA:
            # Always ACK 0x40 frames immediately (panel expects this for comms path health
            # and to dequeue access/alarm events).
            self._send_panel_ack_immediate(fr)

            # Attempt to classify this 0x40 payload as a status response or event.
            resp_in = proto.parse_input_status_response(fr.body)
            resp_rel = proto.parse_relay_status_response(fr.body)
            resp_area = proto.parse_area_status_response(fr.body)
            resp_door = proto.parse_door_status_response(fr.body)
            ev = proto.parse_event(fr.body)

            # input status response
            if resp_in:
                start, statuses = resp_in
                for i, s in enumerate(statuses):
                    inp = start + i
                    self.state.input_words[inp] = int(s)
                    self.state.inputs[inp] = self._input_state_from_status(int(s))
                self.state.last_event = f"Inputs {start}-{start+len(statuses)-1}"
                self._notify()
                return

            # relay status response
            if resp_rel:
                start, statuses = resp_rel
                for i, s in enumerate(statuses):
                    relay = start + i
                    self.state.relays[relay] = bool(s & 0x01)  # observed bit
                self.state.last_event = f"Relays {start}-{start+len(statuses)-1}"
                self._notify()
                return
                        # area status response
            if resp_area:
                start_area, words = resp_area
                now = asyncio.get_running_loop().time()
                for i, w in enumerate(words):
                    area = start_area + i
                    self.state.area_words[area] = w

                    # Briefly preserve optimistic UI state after an HA-issued arm/disarm,
                    # then resume reflecting panel-reported words/events.
                    until = self._area_override_until.get(area, 0.0)
                    if now < until:
                        continue

                    # Confirmed from captures on this panel: 0x0000 and 0x0006 are disarmed.
                    # Treat any other observed word as armed for now so CTPlus/RAS-initiated
                    # changes are visible in HA without needing a reload.
                    if w in (0x0000, 0x0003, 0x0006):
                        self.state.areas[area] = "disarmed"
                    else:
                        self.state.areas[area] = "armed"

                self.state.last_event = f"Areas {start_area}-{start_area+len(words)-1}"
                self._notify()
                return
            # door status response
            if resp_door:
                door, status = resp_door
                decoded = self._decode_door_contact_state(status)
                now = asyncio.get_running_loop().time()
                # Prefer a just-received unsolicited door event over a queued poll reply.
                # This prevents stale/open poll responses from delaying an immediate close
                # (and vice versa) when the user is actively operating a door.
                if now < self._door_event_prefer_until.get(door, 0.0):
                    current = self.state.doors.get(door)
                    if current in ("open", "closed") and decoded != current:
                        _LOGGER.debug(
                            "Ignoring polled Door %s status 0x%04X during live-event preference window (current=%s)",
                            door,
                            status,
                            current,
                        )
                        return
                self.state.door_words[door] = status
                self.state.doors[door] = decoded
                self.state.last_event = f"Door {door} status 0x{status:04X}"
                self._notify()
                return
            # RAS status response (doors 1-16 / keypads / single door controllers)
            resp_ras = proto.parse_ras_status_response(fr.body)
            if resp_ras:
                ras, status = resp_ras
                self.state.ras_status[ras] = status
                self.state.last_event = f"RAS {ras} status"
                self._notify()
                return


            # events
            if ev:
                code, obj = ev
                loop_now = asyncio.get_running_loop().time()
                self._last_unsolicited_event_monotonic = loop_now
                # Any unsolicited event means the panel is actively streaming queue items.
                # Back off normal polling briefly so ACKs/events can flow without extra chatter.
                self._poll_backoff_until = max(self._poll_backoff_until, loop_now + 2.5)

                payload = decode_ctplus_event(code, obj, fr.body.hex())

                prev_seq = self._last_panel_event_seq
                self._last_panel_event_seq = fr.seq
                if prev_seq is not None and prev_seq < 0xF0 and fr.seq <= 0x03 and prev_seq > 0x03:
                    self._enter_quiet_mode("panel event sequence restarted", duration=max(45.0, float(self.poll_interval) * 2.0))

                # Suppress retransmitted duplicates on the HA event bus *and* avoid spawning
                # extra targeted refreshes for the same repeated queue-head event.
                repeat_count = self._note_panel_event_retransmit(fr)
                if repeat_count >= self._panel_retry_event_threshold:
                    self._enter_quiet_mode(
                        f"repeated panel event retries for code 0x{code:02X} object {obj}",
                        duration=max(90.0, float(self.poll_interval) * 3.0),
                    )
                if repeat_count > 1:
                    self.state.last_event = f"Duplicate event suppressed: {payload.get('text') or payload.get('message')}"
                    self._notify()
                    return

                if code == 0x96:
                    mapped = self._input_event_state(code)
                    if mapped is not None:
                        self.state.inputs[obj] = mapped
                    self._schedule_input_status_refresh(obj)
                elif code == 0x97:
                    mapped = self._input_event_state(code)
                    if mapped is not None:
                        self.state.inputs[obj] = mapped
                    self._schedule_input_status_refresh(obj)
                elif code == 0x84:
                    self.state.relays[obj] = True
                elif code == 0x85:
                    self.state.relays[obj] = False
                elif code == 0x0B:
                    self.state.areas[obj] = "armed"
                elif code == 0x0C:
                    self.state.areas[obj] = "disarmed"
                # Door event mappings confirmed from supplied CTPlus captures:
                #   0xA5 on door 17 when physically opened
                #   0xA6 / 0xAF on door 17 when physically closed/secured
                # The entities only distinguish zero/non-zero today, so keep this conservative.
                elif code == 0xA5:
                    self.state.door_words[obj] = 1
                    self.state.doors[obj] = "open"
                    self._door_event_prefer_until[obj] = loop_now + 15.0
                    self._schedule_door_status_refresh(obj)
                elif code == 0xA6:
                    self.state.door_words[obj] = 0
                    self.state.doors[obj] = "closed"
                    self._door_event_prefer_until[obj] = loop_now + 15.0
                    self._schedule_door_status_refresh(obj)
                elif code == 0xAF:
                    # "Secured" is a lock/secure-state event, not necessarily a contact-close event.
                    self.state.door_secure[obj] = "secured"
                    self._schedule_door_status_refresh(obj)
                elif code == 0xAE:
                    self.state.door_secure[obj] = "unsecured"
                    self._schedule_door_status_refresh(obj)
                elif code == 0x86:
                    self.state.door_lock[obj] = "unlocked"
                    self._schedule_door_status_refresh(obj)
                elif code == 0x87:
                    self.state.door_lock[obj] = "locked"
                    self._schedule_door_status_refresh(obj)
                elif code == 0x88:
                    self.state.door_lock[obj] = "auto_unlocked"
                    self._schedule_door_status_refresh(obj)
                elif code == 0x89:
                    self.state.door_lock[obj] = "auto_locked"
                    self._schedule_door_status_refresh(obj)
                elif code in (0x92, 0x9D, 0xA7, 0xA8, 0xA9, 0xAA):
                    self._schedule_door_status_refresh(obj)

                # Do not automatically fire the global "Retrieve events" command here:
                # captures show that command is useful as a manual recovery tool, but when
                # injected into normal event flow on path 3 it causes "path event reset"
                # churn and missed close-together events.
                self._last_retrieve_events_key = None

                self.state.last_event = payload.get('text') or payload.get('message')
                self.state.last_event_code = code
                self.state.last_event_object = obj
                self.state.last_event_raw = payload.get('raw')
                self.hass.bus.async_fire(f"{DOMAIN}_event", payload)
                # Extra event name to make filtering easier in HA
                self.hass.bus.async_fire(f"{DOMAIN}_ctplus_event", payload)
                self._notify()
                return

            # Unknown 0x40 frame (data but not parsed)
            self.state.last_event = f"CTPlus 0x40 {fr.body.hex()}"
            self.hass.bus.async_fire(f"{DOMAIN}_raw", {"hex": fr.body.hex(), "len": len(fr.body)})
            self._notify()
            return

        if fr.msg_type == proto.TYPE_PANEL_ACK:
            self.state.last_event = f"ACK seq {fr.seq}"
            self._notify()
            return

        self.state.last_event = f"CTPlus {fr.msg_type:02X} {fr.body.hex()}"
        self._notify()

    async def async_dump_debug(self) -> str:
        """Dump recent RX/TX frames and current state to /config for support/debugging."""
        try:
            path = self.hass.config.path(f"tecom_challengerplus_debug_{int(time.time())}.json")
            data = {
                "ts": time.time(),
                "host": self.host,
                "mode": self.mode,
                "transport": self.transport,
                "peer": str(getattr(self, "_udp_last_peer", None)),
                "config": {
                    "poll_interval": self.poll_interval,
                    "door_status_mode": self.door_status_mode,
                    "door_status_per_cycle": self.door_status_per_cycle,
                    "door_poll_startup_only": getattr(self, "door_poll_startup_only", False),
                    "min_send_interval_ms": self.min_send_interval_ms,
                    "dgp_door_ids": list(self.dgp_door_ids),
                    "ras_door_ids": list(self.ras_door_ids),
                    "input_ids": list(self.input_ids),
                    "areas_count": self.areas_count,
                    "input_mapping_mode": self.input_mapping_mode,
                    "quiet_mode_until": self._quiet_mode_until,
                    "quiet_reason": self._quiet_reason,
                    "quiet_reinit_pending": self._quiet_reinit_pending,
                },
                "state": {
                    "last_event": self.state.last_event,
                    "last_event_code": self.state.last_event_code,
                    "last_event_object": self.state.last_event_object,
                    "last_event_raw": self.state.last_event_raw,
                    "inputs": dict(self.state.inputs),
                    "relays": dict(self.state.relays),
                    "doors": dict(self.state.doors),
                    "door_words": {str(k): f"0x{v:04X}" for k, v in self.state.door_words.items()},
                    "door_secure": dict(self.state.door_secure),
                    "door_lock": dict(self.state.door_lock),
                    "areas": dict(self.state.areas),
                    "area_words": {str(k): f"0x{v:04X}" for k, v in self.state.area_words.items()},
                    "ras_status": {str(k): f"0x{v:02X}" for k, v in self.state.ras_status.items()},
                },
                "recent_frames": list(self._debug_frames),
            }

            def _write() -> None:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)

            await self.hass.async_add_executor_job(_write)
            _LOGGER.warning("Tecom ChallengerPlus debug dump written: %s", path)
            return path
        except Exception:
            _LOGGER.exception("Failed to write debug dump")
            return ""

    async def async_request_full_sync(self) -> None:
        if self.mode != MODE_CTPLUS:
            raise TecomNotSupported("Full sync requires CTPlus mode")
        await self._async_initial_sync()

    async def async_retrieve_events(self) -> None:
        if self.mode != MODE_CTPLUS:
            raise TecomNotSupported("Retrieve events requires CTPlus mode")
        await self._send_command(proto.cmd_retrieve_events())

    def _clear_door_lock_runtime_state(self) -> None:
        """Drop cached door lock/secure state before a new CTPlus session init.

        Contact/reed state is kept separately in door_words/doors. This prevents stale
        secure/unlock events from a previous session being reused after reconnect or a
        manual reinitialisation.
        """
        self.state.door_secure.clear()
        self.state.door_lock.clear()

    async def async_reinitialize_session(self, log_errors: bool = True) -> None:
        if self.mode != MODE_CTPLUS:
            raise TecomNotSupported("Session reinitialisation requires CTPlus mode")
        self._clear_door_lock_runtime_state()
        self._notify()
        try:
            await self._send_command(proto.cmd_session_hello(), bypass_quiet=True)
            await asyncio.sleep(max(0.25, self._min_send_interval * 2.5))
            await self._send_command(proto.cmd_session_params(), bypass_quiet=True)
            await asyncio.sleep(max(0.25, self._min_send_interval * 2.5))
            if getattr(self, 'dgp_door_ids', None):
                await self._send_command(proto.cmd_door_status_init(), bypass_quiet=True)
                self._door_status_inited = True
        except Exception:
            if log_errors:
                _LOGGER.debug("CTPlus session init failed", exc_info=True)
            return

        now = asyncio.get_running_loop().time()
        self._startup_backlog_started_monotonic = now
        self._last_unsolicited_event_monotonic = now
        self._startup_backlog_drain = True
        self._quiet_mode_until = 0.0
        self._quiet_reason = None

    # -------------------------
    # Control helpers

    # -------------------------
    async def async_set_relay(self, relay: int, on: bool) -> None:
        if self.mode != MODE_CTPLUS:
            raise TecomNotSupported("Relay control requires CTPlus mode")
        await self._send_command(proto.cmd_set_relay(relay, on))

    async def async_unlock_door(self, door: int) -> None:
        if self.mode != MODE_CTPLUS:
            raise TecomNotSupported("Door control requires CTPlus mode")
        await self._send_command(proto.cmd_open_door(door))

    async def async_arm_area(self, area: int, mode: str = "away") -> None:
        if self.mode != MODE_CTPLUS:
            raise TecomNotSupported("Area control requires CTPlus mode")

        # Optimistically update UI and ignore status-poll words briefly (some panels report confusing words).
        self.state.areas[area] = "armed"
        self._area_override_until[area] = asyncio.get_running_loop().time() + 120.0
        self._notify()

        if mode == "home":
            await self._send_command(proto.cmd_area_arm_home(area))
        else:
            await self._send_command(proto.cmd_area_arm_away(area))
    async def async_disarm_area(self, area: int) -> None:
        if self.mode != MODE_CTPLUS:
            raise TecomNotSupported("Area control requires CTPlus mode")

        # Optimistically update UI and ignore status-poll words briefly (some panels report confusing words).
        self.state.areas[area] = "disarmed"
        self._area_override_until[area] = asyncio.get_running_loop().time() + 120.0
        self._notify()

        await self._send_command(proto.cmd_area_disarm(area))

