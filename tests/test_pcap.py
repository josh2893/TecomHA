"""Synthetic Ethernet captures keep file metadata outside protocol fixtures."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import struct

import pytest

from test_crypto import CAPTURED
from tecom_cp import ctplus_crypto as crypto

spec = importlib.util.spec_from_file_location('pcap_reader', Path(__file__).resolve().parents[1] / 'tools/_pcap.py')
pcap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pcap)

WIRE = bytes.fromhex(CAPTURED[crypto.ENC_AES_CBC_128])


def block(kind, body, endian):
    assert len(body) % 4 == 0
    size = len(body) + 12
    return struct.pack(endian + 'II', kind, size) + body + struct.pack(endian + 'I', size)


def capture(payload=WIRE, *, endian='<', padding=b'', options=b'', ip_options=b'', vlan=False, original_extra=0, interface=0, link_type=1):
    shb = block(0x0A0D0D0A, struct.pack(endian + 'IHHq', 0x1A2B3C4D, 1, 0, -1), endian)
    idb = block(1, struct.pack(endian + 'HHI', link_type, 0, 65535), endian)
    udp = struct.pack('!HHHH', 3001, 3001, 8 + len(payload), 0) + payload
    ip = struct.pack('!BBHHHBBH4s4s', 0x45 + len(ip_options) // 4, 0,
                     20 + len(ip_options) + len(udp), 0, 0, 64, 17, 0,
                     bytes([192, 168, 1, 10]), bytes([192, 168, 1, 50])) + ip_options
    ethernet = bytes(12) + (b'\x81\x00\x00\x01\x08\x00' if vlan else b'\x08\x00')
    packet = ethernet + ip + udp + padding
    epb = struct.pack(endian + 'IIIII', interface, 0, 0, len(packet), len(packet) + original_extra)
    epb += packet + bytes(-len(packet) % 4) + options
    return shb + idb + block(6, epb, endian)


def read(tmp_path, data):
    path = tmp_path / 'synthetic.pcapng'
    path.write_bytes(data)
    return list(pcap.udp_payloads(str(path)))


@pytest.mark.parametrize('endian', ['<', '>'])
def test_actual_udp_boundary_excludes_capture_footer(tmp_path, endian):
    data = capture(endian=endian)
    assert data[-4:] == struct.pack(endian + 'I', 108)
    assert read(tmp_path, data) == [{
        'src': '192.168.1.10', 'dst': '192.168.1.50', 'payload': WIRE,
    }]


@pytest.mark.parametrize('payload_length', [1, 2, 3, 34])
def test_capture_padding_options_and_original_length_are_not_payload(tmp_path, payload_length):
    payload = bytes(range(payload_length))
    options = struct.pack('<HH', 1, 4) + b'test' + bytes(4)
    data = capture(payload, options=options, original_extra=48)
    assert read(tmp_path, data)[0]['payload'] == payload


def test_udp_length_excludes_ethernet_padding(tmp_path):
    assert read(tmp_path, capture(padding=bytes(16)))[0]['payload'] == WIRE


def test_vlan_and_ipv4_options_respect_header_lengths(tmp_path):
    assert read(tmp_path, capture(vlan=True, ip_options=bytes(4)))[0]['payload'] == WIRE


def test_new_section_resets_byte_order_and_interfaces(tmp_path):
    data = capture(endian='<') + capture(b'next', endian='>')
    assert [row['payload'] for row in read(tmp_path, data)] == [WIRE, b'next']


@pytest.mark.parametrize('damage', ['truncate', 'footer', 'captured_length', 'interface', 'link_type'])
def test_malformed_or_unsupported_capture_is_not_silently_misdecoded(tmp_path, damage):
    if damage == 'interface':
        data = capture(interface=1)
    elif damage == 'link_type':
        data = capture(link_type=101)
    else:
        data = bytearray(capture())
        if damage == 'truncate':
            data = data[:-4]
        elif damage == 'footer':
            data[-1] ^= 1
        else:
            struct.pack_into('<I', data, 28 + 20 + 20, 9999)
    with pytest.raises(ValueError):
        read(tmp_path, data)
