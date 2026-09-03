"""Read IPv4 UDP payloads from Ethernet PCAPNG Enhanced Packet Blocks.

Capture padding, options and the repeated Block Total Length are file metadata,
never part of a UDP payload. Keep both the captured length and UDP length bounds.
"""
from __future__ import annotations

from pathlib import Path
import struct
from typing import Iterator


def _ethernet_udp(packet: bytes) -> dict | None:
    if len(packet) < 14:
        return None
    ip = 14
    ethertype = int.from_bytes(packet[12:14], 'big')
    while ethertype in (0x8100, 0x88A8):  # 802.1Q / provider VLAN tags
        if len(packet) < ip + 4:
            return None
        ethertype = int.from_bytes(packet[ip + 2:ip + 4], 'big')
        ip += 4
    if ethertype != 0x0800:
        return None
    if len(packet) < ip + 20 or packet[ip] >> 4 != 4:
        raise ValueError('Truncated or invalid IPv4 header')
    ihl = (packet[ip] & 15) * 4
    total = int.from_bytes(packet[ip + 2:ip + 4], 'big')
    if ihl < 20 or total < ihl or ip + total > len(packet):
        raise ValueError('Truncated or invalid IPv4 packet')
    if packet[ip + 9] != 17:
        return None
    if int.from_bytes(packet[ip + 6:ip + 8], 'big') & 0x3FFF:
        return None  # Fragment reassembly is outside this reader's scope.
    udp = ip + ihl
    if udp + 8 > ip + total:
        raise ValueError('Truncated UDP header')
    length = int.from_bytes(packet[udp + 4:udp + 6], 'big')
    if length < 8 or udp + length > ip + total:
        raise ValueError('Truncated or invalid UDP payload')
    return {
        'src': '.'.join(str(b) for b in packet[ip + 12:ip + 16]),
        'dst': '.'.join(str(b) for b in packet[ip + 16:ip + 20]),
        'payload': packet[udp + 8:udp + length],
    }


def udp_payloads(path: str) -> Iterator[dict]:
    """Yield {src, dst, payload}; reject malformed or unsupported captures."""
    data = Path(path).read_bytes()
    pos = 0
    endian = None
    interfaces: list[int] = []
    while pos < len(data):
        if len(data) - pos < 12:
            raise ValueError('Truncated PCAPNG block')
        if data[pos:pos + 4] == b'\x0a\x0d\x0d\x0a':
            magic = data[pos + 8:pos + 12]
            if magic == b'\x4d\x3c\x2b\x1a':
                endian = '<'
            elif magic == b'\x1a\x2b\x3c\x4d':
                endian = '>'
            else:
                raise ValueError('Invalid PCAPNG byte-order magic')
            interfaces = []
        if endian is None:
            raise ValueError('PCAPNG must start with a Section Header Block')
        kind, size = struct.unpack_from(endian + 'II', data, pos)
        if size < 12 or size % 4 or pos + size > len(data):
            raise ValueError('Invalid PCAPNG block length')
        if struct.unpack_from(endian + 'I', data, pos + size - 4)[0] != size:
            raise ValueError('PCAPNG block length footer does not match')
        if kind == 0x0A0D0D0A and size < 28:
            raise ValueError('Truncated PCAPNG section header')
        if kind == 1:
            if size < 20:
                raise ValueError('Truncated PCAPNG interface description')
            interfaces.append(struct.unpack_from(endian + 'H', data, pos + 8)[0])
        elif kind == 6:
            if size < 32:
                raise ValueError('Truncated PCAPNG Enhanced Packet Block')
            interface, _, _, captured, original = struct.unpack_from(endian + 'IIIII', data, pos + 8)
            if interface >= len(interfaces):
                raise ValueError('Unknown PCAPNG interface')
            if interfaces[interface] != 1:
                raise ValueError('Only Ethernet PCAPNG interfaces are supported')
            if captured > original or 28 + ((captured + 3) & ~3) > size - 4:
                raise ValueError('Invalid PCAPNG captured packet length')
            result = _ethernet_udp(data[pos + 28:pos + 28 + captured])
            if result is not None:
                yield result
        pos += size
