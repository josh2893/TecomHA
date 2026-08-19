"""Minimal pcapng reader.

Written by hand rather than pulling in scapy: this only needs to walk Enhanced
Packet Blocks and pull UDP payloads, and the dependency is not worth it for a
repository that otherwise has none.
"""
from __future__ import annotations

import struct
from typing import Iterator


def udp_payloads(path: str) -> Iterator[dict]:
    """Yield {src, dst, payload} for every UDP packet in a pcapng file."""
    data = open(path, "rb").read()
    pos = 0
    while pos < len(data) - 8:
        btype, blen = struct.unpack("<II", data[pos:pos + 8])
        if blen < 12 or pos + blen > len(data) + 4:
            break
        if btype == 0x00000006:  # Enhanced Packet Block
            cap_len = struct.unpack("<I", data[pos + 24:pos + 28])[0]
            pkt = data[pos + 32:pos + 32 + cap_len]
            # Locate the IPv4 header rather than assuming a fixed link-layer
            # offset; captures come from varied interfaces.
            for off in range(0, min(20, max(0, len(pkt) - 20))):
                if pkt[off] == 0x45 and pkt[off + 9] == 17:
                    src = ".".join(str(b) for b in pkt[off + 12:off + 16])
                    dst = ".".join(str(b) for b in pkt[off + 16:off + 20])
                    yield {"src": src, "dst": dst, "payload": pkt[off + 28:]}
                    break
        pos += (blen + 3) & ~3
