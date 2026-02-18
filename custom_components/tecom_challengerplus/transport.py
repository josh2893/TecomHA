"""Async transports (TCP/UDP) for Tecom ChallengerPlus."""

from __future__ import annotations

import asyncio
import logging
import contextlib
from typing import Callable, Optional

from .exceptions import TecomConnectionError

_LOGGER = logging.getLogger(__name__)

class TecomTransportBase:
    async def async_start(self) -> None:  # pragma: no cover
        raise NotImplementedError

    async def async_stop(self) -> None:  # pragma: no cover
        raise NotImplementedError

    async def async_send(self, data: bytes) -> None:  # pragma: no cover
        raise NotImplementedError


# -------------------------
# UDP raw
# -------------------------

class _UDPProtocol(asyncio.DatagramProtocol):
    def __init__(self, on_datagram: Callable[[bytes], None]) -> None:
        self.on_datagram = on_datagram

    def datagram_received(self, data: bytes, addr):  # noqa: ANN001
        self.on_datagram(data)


class TecomUDPRaw(TecomTransportBase):
    def __init__(
        self,
        hass,
        bind_host: str,
        bind_port: int,
        remote_host: str,
        remote_port: int,
        on_datagram: Callable[[bytes], None],
    ) -> None:
        self._hass = hass
        self._bind_host = bind_host
        self._bind_port = bind_port
        self._remote = (remote_host, remote_port)
        self._on = on_datagram
        self._transport: asyncio.DatagramTransport | None = None

    async def async_start(self) -> None:
        loop = asyncio.get_running_loop()
        self._transport, _ = await loop.create_datagram_endpoint(
            lambda: _UDPProtocol(self._on),
            local_addr=(self._bind_host, self._bind_port),
        )

    async def async_stop(self) -> None:
        if self._transport:
            self._transport.close()
            self._transport = None

    async def async_send(self, data: bytes) -> None:
        if not self._transport:
            raise TecomConnectionError("UDP transport not started")
        self._transport.sendto(data, self._remote)


# -------------------------
# TCP raw (bytes)
# -------------------------

class TecomTCPRaw(TecomTransportBase):
    def __init__(
        self,
        hass,
        host: str,
        port: int,
        role: str,
        bind_host: str,
        bind_port: int,
        on_bytes: Callable[[bytes], None],
    ) -> None:
        self._hass = hass
        self._host = host
        self._port = port
        self._role = role
        self._bind_host = bind_host
        self._bind_port = bind_port
        self._on = on_bytes

        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._server: asyncio.base_events.Server | None = None
        self._task: asyncio.Task | None = None

    async def async_start(self) -> None:
        if self._role == "server":
            self._server = await asyncio.start_server(self._handle_client, self._bind_host, self._bind_port)
            _LOGGER.info("TCP raw server listening on %s:%s", self._bind_host, self._bind_port)
        else:
            await self._connect_client()
        self._task = asyncio.create_task(self._read_loop())

    async def _connect_client(self) -> None:
        self._reader, self._writer = await asyncio.open_connection(self._host, self._port)
        _LOGGER.info("TCP raw connected to %s:%s", self._host, self._port)

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        # Accept first connection and use it
        if self._writer:
            writer.close()
            await writer.wait_closed()
            return
        self._reader, self._writer = reader, writer
        _LOGGER.info("TCP raw client connected from %s", writer.get_extra_info("peername"))

    async def _read_loop(self) -> None:
        while True:
            await asyncio.sleep(0)
            if not self._reader:
                await asyncio.sleep(0.25)
                continue
            try:
                data = await self._reader.read(4096)
            except Exception as e:
                _LOGGER.warning("TCP raw read error: %s", e)
                data = b""

            if not data:
                await asyncio.sleep(0.5)
                continue
            self._on(data)

    async def async_stop(self) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(Exception):
                await self._task
            self._task = None
        if self._writer:
            self._writer.close()
            with contextlib.suppress(Exception):
                await self._writer.wait_closed()
            self._writer = None
            self._reader = None
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    async def async_send(self, data: bytes) -> None:
        if not self._writer:
            raise TecomConnectionError("TCP not connected")
        self._writer.write(data)
        await self._writer.drain()


# -------------------------
# TCP Printer (line-based)
# -------------------------

class TecomTCPPrinterServer(TecomTransportBase):
    def __init__(self, hass, bind_host: str, bind_port: int, on_line: Callable[[str], None]) -> None:
        self._hass = hass
        self._bind_host = bind_host
        self._bind_port = bind_port
        self._on = on_line
        self._server: asyncio.base_events.Server | None = None

    async def async_start(self) -> None:
        self._server = await asyncio.start_server(self._handle, self._bind_host, self._bind_port)
        _LOGGER.info("Printer server listening on %s:%s", self._bind_host, self._bind_port)

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        peer = writer.get_extra_info("peername")
        _LOGGER.info("Printer connection from %s", peer)
        try:
            while True:
                line = await reader.readline()
                if not line:
                    break
                text = line.decode("utf-8", errors="ignore").strip()
                if text:
                    self._on(text)
        finally:
            writer.close()
            await writer.wait_closed()
            _LOGGER.info("Printer connection closed %s", peer)

    async def async_stop(self) -> None:
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    async def async_send(self, data: bytes) -> None:
        # Printer stream is typically one-way (panel -> server), so we don't send.
        return


class TecomTCPPrinterClient(TecomTransportBase):
    def __init__(self, hass, host: str, port: int, on_line: Callable[[str], None]) -> None:
        self._hass = hass
        self._host = host
        self._port = port
        self._on = on_line
        self._task: asyncio.Task | None = None
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None

    async def async_start(self) -> None:
        self._reader, self._writer = await asyncio.open_connection(self._host, self._port)
        self._task = asyncio.create_task(self._read_loop())
        _LOGGER.info("Printer client connected to %s:%s", self._host, self._port)

    async def _read_loop(self) -> None:
        assert self._reader is not None
        while True:
            line = await self._reader.readline()
            if not line:
                await asyncio.sleep(1)
                continue
            text = line.decode("utf-8", errors="ignore").strip()
            if text:
                self._on(text)

    async def async_stop(self) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(Exception):
                await self._task
            self._task = None
        if self._writer:
            self._writer.close()
            with contextlib.suppress(Exception):
                await self._writer.wait_closed()
            self._writer = None
            self._reader = None

    async def async_send(self, data: bytes) -> None:
        # Printer mode is typically read-only.
        return
