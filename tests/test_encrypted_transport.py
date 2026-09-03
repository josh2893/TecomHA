"""Run the real hub/transport boundary with small HA service doubles.

No live panel or Home Assistant installation is needed. Cipher fixtures are
actual UDP payloads; network sends are collected without opening a socket.
"""
from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from types import ModuleType, SimpleNamespace

import pytest

from conftest import INTEGRATION_DIR
from tecom_cp import ctplus_crypto as crypto, ctplus_protocol as proto, const
from test_crypto import CAPTURED, HELLO_PLAINTEXT


@pytest.fixture
def make_hub(monkeypatch, tmp_path):
    modules = {
        'homeassistant': ModuleType('homeassistant'),
        'homeassistant.config_entries': SimpleNamespace(ConfigEntry=object),
        'homeassistant.core': SimpleNamespace(HomeAssistant=object, callback=lambda fn: fn),
        'homeassistant.exceptions': SimpleNamespace(ServiceValidationError=ValueError),
        'homeassistant.helpers': ModuleType('homeassistant.helpers'),
        'homeassistant.helpers.storage': SimpleNamespace(Store=lambda *args: None),
    }
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)
    spec = importlib.util.spec_from_file_location('tecom_cp.hub', INTEGRATION_DIR / 'hub.py')
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, 'tecom_cp.hub', module)
    spec.loader.exec_module(module)

    async def executor(fn):
        return fn()

    def make(enc_type=crypto.ENC_AES_CBC_128, auth_method=const.AUTH_METHOD_SECURITY_PASSWORD):
        hass = SimpleNamespace(
            bus=SimpleNamespace(async_fire=lambda *args: None),
            config=SimpleNamespace(path=lambda filename: str(tmp_path / filename)),
            async_add_executor_job=executor,
        )
        entry = SimpleNamespace(entry_id='test', options={}, data={
            'host': '192.168.1.50', 'send_port': 3001, 'listen_port': 3001,
            'encryption_type': enc_type, 'encryption_key': '1234567890',
            'auth_method': auth_method, 'computer_password': '1234567890',
            'auth_username': 'PATHUSER', 'auth_password': 'PathPass99',
        })
        hub = module.TecomHub(hass, entry)
        hub._udp_last_peer = ('192.168.1.50', 3001)
        hub._type_offset = 0x40
        return hub
    return make


class Sends:
    def __init__(self, route='sendto_nowait'):
        self.sent = []
        if route in ('sendto_nowait', 'send_nowait'):
            setattr(self, route, self.record)
        if route == 'failing_nowait':
            self.sendto_nowait = self.fail

    def record(self, data, peer=None):
        self.sent.append((data, peer))

    def fail(self, *args):
        raise OSError('Simulated send failure')

    async def async_send(self, data):
        self.record(data)

    async def async_sendto(self, data, peer):
        self.record(data, peer)


# Host ACKs from packet 6 of the original first capture for each cipher.
CAPTURED_ACKS = {
    crypto.ENC_AES_CBC_128: (39, '761f22b2c1593d0bb87e0b606f990ba400075ce854e4f1ceef3e3090036b2678924b'),
    crypto.ENC_AES_CBC_256: (42, '761f22b2c1593d0bb87e0b606f990ba40007ba9ac16e13c177c5fa4c1a7e9d3e8dbf'),
    crypto.ENC_TWOFISH_128: (45, '761f22b2c1593d0bb87e0b606f990ba40007e5077cc98b1336b839cc550d826d611d'),
}


@pytest.mark.parametrize('enc_type', CAPTURED_ACKS)
@pytest.mark.parametrize('route', ['sendto_nowait', 'send_nowait', 'async', 'failing_nowait'])
def test_ack_every_transport_route_matches_capture(make_hub, monkeypatch, enc_type, route):
    seq, hexs = CAPTURED_ACKS[enc_type]
    expected = bytes.fromhex(hexs)
    monkeypatch.setattr('os.urandom', lambda count: expected[:16])

    async def run():
        hub = make_hub(enc_type)
        transport = hub._transport_obj = Sends(route)
        frame = proto.Frame(proto.TYPE_EVENT_OR_DATA, seq, type_offset=0x40)
        hub._send_panel_ack(frame, delay=0)
        if route in ('sendto_nowait', 'send_nowait'):
            assert len(transport.sent) == 1  # Immediate path must stay immediate.
        await asyncio.sleep(0)  # Let the real async fallback run, if needed.
        assert [payload for payload, _ in transport.sent] == [expected]
        assert hub._debug_frames[-1]['hex'] == proto.build_ack(seq, type_offset=0x40).to_bytes().hex()
    asyncio.run(run())


@pytest.mark.parametrize('enc_type', [crypto.ENC_NONE, *CAPTURED])
@pytest.mark.parametrize('auth_method', [const.AUTH_METHOD_SECURITY_PASSWORD, const.AUTH_METHOD_CREDENTIALS])
def test_both_auth_methods_use_selected_transport_encryption(make_hub, enc_type, auth_method):
    async def run():
        hub = make_hub(enc_type, auth_method)
        hub._transport_obj = Sends()
        body = hub._build_auth_command()
        expected_body = (proto.cmd_session_auth_credentials('PATHUSER', 'PathPass99')
                         if auth_method == const.AUTH_METHOD_CREDENTIALS else
                         bytes.fromhex('01060b2143658709'))
        assert body == expected_body
        frame = proto.Frame(proto.TYPE_COMMAND, 1, body=body, type_offset=0x40)
        await hub._send_frame(frame)
        wire = hub._transport_obj.sent[0][0]
        if enc_type == crypto.ENC_NONE:
            assert wire == frame.to_bytes()
        else:
            assert crypto.looks_encrypted(wire)
            assert hub._decrypt_datagram(wire) == frame.to_bytes()
        # Auth must not leak via raw hex, structured bodies or pending ACK links.
        text = json.dumps([list(hub._debug_frames), hub._pending_host_frames])
        assert body.hex() not in text
        assert frame.to_bytes().hex() not in text
        hub._track_rx_frame(proto.Frame(proto.TYPE_PANEL_ACK, 1))
        assert frame.to_bytes().hex() not in json.dumps(list(hub._debug_frames))
    asyncio.run(run())


@pytest.mark.parametrize('route', ['sendto_nowait', 'send_nowait', 'async'])
def test_unencrypted_ack_bytes_are_unchanged(make_hub, route):
    async def run():
        hub = make_hub(crypto.ENC_NONE)
        hub._transport_obj = Sends(route)
        hub._send_panel_ack(proto.Frame(proto.TYPE_EVENT_OR_DATA, 0x5e, type_offset=0x40), delay=0)
        await asyncio.sleep(0)
        assert hub._transport_obj.sent[0][0] == proto.build_ack(0x5e, type_offset=0x40).to_bytes()
    asyncio.run(run())


def test_delayed_ack_stays_encrypted(make_hub):
    async def run():
        hub = make_hub()
        hub._transport_obj = Sends()
        hub._send_panel_ack(proto.Frame(proto.TYPE_EVENT_OR_DATA, 1, type_offset=0x40), delay=0.001)
        assert not hub._transport_obj.sent
        await asyncio.sleep(0.02)
        assert hub._cipher.unwrap(hub._transport_obj.sent[0][0]) == proto.build_ack(1, type_offset=0x40).to_bytes()
    asyncio.run(run())


@pytest.mark.parametrize('enc_type', CAPTURED)
def test_received_capture_reaches_real_frame_handler(make_hub, enc_type):
    hub = make_hub(enc_type)
    handled = []
    hub._handle_ctplus_frame = handled.append
    hub._on_ctplus_datagram(bytes.fromhex(CAPTURED[enc_type]), hub._udp_last_peer)
    assert handled == [proto.parse_frame(HELLO_PLAINTEXT)]
    assert hub._decrypt_failures == 0


def test_wrong_key_crc_failures_are_counted_and_recovery_resets_warning(make_hub, caplog):
    hub = make_hub()
    wrong = crypto.CtplusCipher(crypto.ENC_AES_CBC_128, 'WrongKey123')
    # Exactly one full block: no padding check can detect the wrong key.
    aligned_frame = proto.Frame(proto.TYPE_COMMAND, 1, body=b'abcdefghi').to_bytes()
    assert len(aligned_frame) == 16
    wire = wrong.wrap(aligned_frame, iv=bytes(16))
    assert hub._cipher.unwrap(wire) is not None
    for _ in range(4):
        assert hub._decrypt_datagram(wire) is None
    assert hub._decrypt_failures == 4
    assert sum('Unable to decrypt' in msg for msg in caplog.messages) == 1
    assert hub._decrypt_datagram(bytes.fromhex(CAPTURED[crypto.ENC_AES_CBC_128])) == HELLO_PLAINTEXT
    assert hub._decrypt_failures == 0
    assert not hub._decrypt_warned


def test_encrypted_multiple_frames_are_preserved(make_hub):
    hub = make_hub()
    plain = HELLO_PLAINTEXT + proto.build_ack(1).to_bytes()
    assert hub._decrypt_datagram(hub._cipher.wrap(plain)) == plain
    assert hub._decrypt_datagram(hub._cipher.wrap(plain + b'garbage')) is None


def test_missing_encryption_configuration_is_diagnosed(make_hub, caplog):
    hub = make_hub(crypto.ENC_NONE)
    hub._decrypt_datagram(bytes.fromhex(CAPTURED[crypto.ENC_AES_CBC_128]))
    assert any('no encryption is configured' in msg for msg in caplog.messages)


def test_debug_dump_redacts_auth_in_combined_datagrams_and_reports_cipher(make_hub):
    async def run():
        hub = make_hub()
        auth = proto.Frame(proto.TYPE_COMMAND, 1, body=hub._build_auth_command()).to_bytes()
        hub._debug_append({'hex': (HELLO_PLAINTEXT + auth).hex()})
        hub._decrypt_failures = 2
        path = await hub.async_dump_debug()
        data = json.loads(open(path).read())
        assert data['config']['auth_method'] == const.AUTH_METHOD_SECURITY_PASSWORD
        assert data['config']['encryption_type'] == crypto.ENC_AES_CBC_128
        assert data['config']['decrypt_failures'] == 2
        assert data['recent_frames'][-1]['hex'] == ''
        assert 'redacted authentication' in data['recent_frames'][-1]['redacted']
        assert not {'encryption_key', 'computer_password', 'auth_password'} & data['config'].keys()
    asyncio.run(run())


def test_complete_valid_frame_is_checked_before_candidate_prefixes(make_hub):
    hub = make_hub()
    # Packet 37 in AES 128 / Security-Computer Password / Capture 1. A shorter
    # prefix also passes CRC; scanning first leaves an apparent extra byte.
    plain = bytes.fromhex('5ea08000117a006a00')
    assert proto.parse_frame(plain) is not None
    assert proto.parse_frame(plain[:-1]) is not None
    assert hub._decrypt_datagram(hub._cipher.wrap(plain)) == plain


@pytest.mark.parametrize('name', [b'J. Smith', b''])
def test_user_record_debug_copies_are_redacted_even_without_name(make_hub, name):
    hub = make_hub()
    record = bytearray(43)
    record[:2] = (150).to_bytes(2, 'little')
    record[6:12] = bytes.fromhex('424200000004')
    record[19:19 + len(name)] = name
    body = bytes([0x7D, 45, 0x1D, 43]) + bytes(record)
    frame = proto.Frame(proto.TYPE_EVENT_OR_DATA, 3, body=body)
    hub._debug_append({'hex': frame.to_bytes().hex(), 'body_hex': body.hex(),
                       'acks_hex': frame.to_bytes().hex(), 'ack_for_body_hex': body.hex()})
    entry = hub._debug_frames[-1]
    assert all(entry[key] == '' for key in ('hex', 'body_hex', 'acks_hex', 'ack_for_body_hex'))
    assert 'redacted user records' in entry['redacted']
