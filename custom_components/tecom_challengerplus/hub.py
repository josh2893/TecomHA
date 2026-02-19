"""Central hub: manages transport, parsing, shared state, and services."""

from __future__ import annotations

import asyncio
import logging
import re
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
)
from .exceptions import TecomNotSupported, TecomConnectionError
from .transport import TecomTCPPrinterClient, TecomTCPPrinterServer, TecomUDPRaw, TecomTCPRaw
from . import ctplus_protocol as proto

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
    inputs: dict[int, bool] = None
    relays: dict[int, bool] = None
    doors: dict[int, str] = None
    areas: dict[int, str] = None

    def __post_init__(self):
        self.inputs = self.inputs or {}
        self.relays = self.relays or {}
        self.doors = self.doors or {}
        self.areas = self.areas or {}


class TecomHub:
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
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

        self.inputs_count = int(cfg.get(CONF_INPUTS_COUNT, 0))
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

        self._listeners: set[UpdateCallback] = set()

        self._transport_obj = None  # runtime transport
        self._seq_out = 1
        self._poll_task: asyncio.Task | None = None
        self._heartbeat_task: asyncio.Task | None = None
        self._tcp_buf: bytes = b""  # only used for TCP

    def _next_seq(self) -> int:
        self._seq_out = (self._seq_out + 1) & 0xFF
        if self._seq_out == 0:
            self._seq_out = 1
        return self._seq_out

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

    async def async_start(self) -> None:
        """Start transport and register services."""
        if self.mode == MODE_CTPLUS and self.encryption_type != ENC_NONE:
            raise TecomNotSupported(
                "Encryption is configured but not implemented yet; set encryption to None"
            )

        await self._start_transport()
        self._register_services()

        if self.mode == MODE_CTPLUS:
            self._poll_task = asyncio.create_task(self._poll_loop())
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def async_stop(self) -> None:
        if self._poll_task:
            self._poll_task.cancel()
            self._poll_task = None
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            self._heartbeat_task = None

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

    async def async_send_bytes(self, payload: bytes) -> None:
        if not self._transport_obj:
            raise TecomConnectionError("Transport not started")
        await self._transport_obj.async_send(payload)

    async def _send_frame(self, frame: proto.Frame) -> None:
        await self.async_send_bytes(frame.to_bytes())

    async def _send_command(self, body: bytes) -> None:
        seq = self._next_seq()
        await self._send_frame(proto.Frame(proto.TYPE_COMMAND, seq, body=body))

    # -------------------------
    # Heartbeat / Polling
    # -------------------------

    async def _heartbeat_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(max(5, min(30, self.poll_interval)))
                await self._send_frame(proto.build_heartbeat(self._next_seq()))
            except asyncio.CancelledError:
                return
            except Exception:
                _LOGGER.exception("Heartbeat loop error")

    async def _poll_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(self.poll_interval)
                if self.inputs_count > 0:
                    await self.async_request_inputs(1, self.inputs_count)
                if getattr(self, 'relay_poll_ranges', None):
                    for s, e in self.relay_poll_ranges:
                        await self.async_request_relays(s, e)
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

    def _on_printer_datagram(self, data: bytes) -> None:
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

    def _on_ctplus_bytes(self, data: bytes) -> None:
        # Experimental TCP support via sync+CRC scan
        if not data:
            return
        self._tcp_buf += data
        buf = self._tcp_buf
        frames: list[proto.Frame] = []
        i = 0
        while True:
            j = buf.find(bytes([proto.SYNC]), i)
            if j < 0:
                break
            found = False
            for end in range(j + 7, min(len(buf), j + 2048) + 1):
                fr = proto.parse_frame(buf[j:end])
                if fr:
                    frames.append(fr)
                    i = end
                    found = True
                    break
            if not found:
                break
        self._tcp_buf = buf[i:]
        for fr in frames:
            self._handle_ctplus_frame(fr)

    def _on_ctplus_datagram(self, data: bytes) -> None:
        fr = proto.parse_frame(data)
        if not fr:
            self.state.last_event = f"RAW {data.hex()}"
            self.hass.bus.async_fire(f"{DOMAIN}_raw", {"hex": data.hex(), "len": len(data)})
            self._notify()
            return
        self._handle_ctplus_frame(fr)

    def _handle_ctplus_frame(self, fr: proto.Frame) -> None:
        if fr.msg_type == proto.TYPE_EVENT_OR_DATA:
            # ACK required
            asyncio.create_task(self._send_frame(proto.build_ack(fr.seq)))

            # input status response
            resp_in = proto.parse_input_status_response(fr.body)
            if resp_in:
                start, statuses = resp_in
                for i, s in enumerate(statuses):
                    inp = start + i
                    self.state.inputs[inp] = bool(s & 0x20)  # observed bit
                self.state.last_event = f"Inputs {start}-{start+len(statuses)-1}"
                self._notify()
                return

            # relay status response
            resp_rel = proto.parse_relay_status_response(fr.body)
            if resp_rel:
                start, statuses = resp_rel
                for i, s in enumerate(statuses):
                    relay = start + i
                    self.state.relays[relay] = bool(s & 0x01)  # observed bit
                self.state.last_event = f"Relays {start}-{start+len(statuses)-1}"
                self._notify()
                return

            # events
            ev = proto.parse_event(fr.body)
            if ev:
                code, obj = ev
                if code == 0x96:
                    self.state.inputs[obj] = False
                elif code == 0x97:
                    self.state.inputs[obj] = True
                elif code == 0x84:
                    self.state.relays[obj] = True
                elif code == 0x85:
                    self.state.relays[obj] = False
                elif code == 0x0B:
                    self.state.areas[obj] = "armed"
                elif code == 0x0C:
                    self.state.areas[obj] = "disarmed"

                self.state.last_event = f"Event 0x{code:02X} obj {obj}"
                self.hass.bus.async_fire(
                    f"{DOMAIN}_event",
                    {"code": code, "object": obj, "raw": fr.body.hex()},
                )
                self._notify()
                return

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
        if mode == "home":
            await self._send_command(proto.cmd_area_arm_home(area))
        else:
            await self._send_command(proto.cmd_area_arm_away(area))

    async def async_disarm_area(self, area: int) -> None:
        if self.mode != MODE_CTPLUS:
            raise TecomNotSupported("Area control requires CTPlus mode")
        await self._send_command(proto.cmd_area_disarm(area))