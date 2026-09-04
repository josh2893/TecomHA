"""Regression checks for filtered Activity and capture-confirmed denial layouts.

Card bytes and user details are synthetic; no real credential data is retained.
The hub, protocol, event entity and logbook platform are the production modules.
"""
from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from types import SimpleNamespace

import pytest
from conftest import INTEGRATION_DIR
from tecom_cp import ctplus_protocol as proto, const
from tecom_cp.access import DOOR_EVENT_TYPES, EVENT_ACCESS_ACTIVITY, describe_access
from test_encrypted_transport import make_hub, Sends

CARD = bytes.fromhex('abcdef123456')


def body(code, door=17, user=1041, stamp=1):
    header = b'\x0f\x0c' + stamp.to_bytes(4, 'little') + bytes([code])
    if code == proto.EVENT_ACCESS_DENIED_CARD:
        return header + CARD + bytes([door])
    return header + door.to_bytes(2, 'little') + b'\0' + user.to_bytes(2, 'little') + b'\0\0'


@pytest.fixture
def activity_stack(make_hub, monkeypatch):
    class Bus:
        def __init__(self):
            self.events = []
            self.listeners = {}
        def async_listen(self, name, fn):
            self.listeners.setdefault(name, []).append(fn)
            return lambda: self.listeners[name].remove(fn)
        def async_fire(self, name, data, context=None):
            event = SimpleNamespace(event_type=name, data=dict(data), context=context)
            self.events.append(event)
            for fn in tuple(self.listeners.get(name, ())):
                fn(event)

    class Entity:
        @property
        def name(self):
            return self._attr_name
        def _trigger_event(self, kind, attrs):
            self.triggered.append((kind, attrs))
        def async_write_ha_state(self):
            pass

    registry = SimpleNamespace(async_get=lambda entity_id: SimpleNamespace(device_id=f'device_{entity_id}'))
    monkeypatch.setitem(sys.modules, 'homeassistant.components.event', SimpleNamespace(EventEntity=Entity))
    monkeypatch.setitem(sys.modules, 'homeassistant.helpers.entity', SimpleNamespace(DeviceInfo=dict))
    monkeypatch.setitem(sys.modules, 'homeassistant.helpers.entity_platform', SimpleNamespace(AddEntitiesCallback=object))
    monkeypatch.setitem(sys.modules, 'homeassistant.helpers.entity_registry', SimpleNamespace(async_get=lambda hass: registry))

    def load(name):
        spec = importlib.util.spec_from_file_location(f'tecom_cp.{name}', INTEGRATION_DIR / f'{name}.py')
        mod = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, f'tecom_cp.{name}', mod)
        spec.loader.exec_module(mod)
        return mod

    def make():
        hub = make_hub('none')
        hub.hass.bus = Bus()
        hub.hass.states = SimpleNamespace(get=lambda eid: SimpleNamespace(name='Front Entry Access'))
        hub._transport_obj = Sends()
        hub._panel_ack_delay_seconds = 0
        hub.entry.title = 'Test panel'
        hub.entry.unique_id = 'test-panel'
        hub.state.user_names = {1041: 'J. Smith', 2050: 'A. Jones'}
        entity_module = load('event')
        logbook = load('logbook')
        registered = []
        logbook.async_describe_events(hub.hass, lambda *args: registered.append(args))
        assert registered[0][:2] == (const.DOMAIN, EVENT_ACCESS_ACTIVITY)
        return hub, entity_module.TecomDoorAccessEvent, registered[0][2]
    return make


async def add_entity(hub, entity_class, door=17):
    entity = entity_class(hub, door)
    entity.entity_id = f'event.{hub.entry.entry_id}_door_{door}_access'
    entity.hass = hub.hass
    entity.triggered = []
    await entity.async_added_to_hass()
    return entity


def deliver(hub, code, door=17, user=1041, stamp=1, seq=1):
    frame = proto.Frame(proto.TYPE_EVENT_OR_DATA, seq, body=body(code, door, user, stamp))
    hub._on_ctplus_datagram(frame.to_bytes(), hub._udp_last_peer)
    return frame


def activities(hub):
    return [e for e in hub.hass.bus.events if e.event_type == EVENT_ACCESS_ACTIVITY]


@pytest.mark.parametrize('door', [17, 19])
def test_card_layout_uses_trailing_door_not_card_bytes(door):
    result = proto.parse_event_full(body(0x4B, door))
    assert result == dict(code=0x4B, object=door, area=0, user=0, anchored=True)


def test_void_layout_retains_full_user_number():
    result = proto.parse_event_full(body(0x8B, 17, 2050))
    assert result['object'] == 17 and result['user'] == 2050 and result['area'] == 0


@pytest.mark.parametrize('length', [7, 9, 12, 13, 15])
@pytest.mark.parametrize('code', [0x4B, 0x8B])
def test_unconfirmed_denial_lengths_are_rejected(code, length):
    assert proto.parse_event_full((body(code, stamp=0x8A) + b'\0')[:length]) is None


@pytest.mark.parametrize('code', [0x4B, 0x8B])
def test_unconfirmed_legacy_denial_is_rejected(code):
    assert proto.parse_event_full(bytes([0x8A, code, 17, 0])) is None


@pytest.mark.parametrize('data,expected', [
    ({'code': 0x92, 'user': 1041, 'user_name': 'J. Smith'}, 'Access granted - J. Smith'),
    ({'code': 0x92, 'user': 1041}, 'Access granted - User 1041'),
    ({'code': 0x92, 'last_user_name': 'J. Smith'}, 'Access granted - System'),
    ({'code': 0x9D, 'last_user_name': 'J. Smith'}, 'Access granted (exit button)'),
    ({'code': 0x8B, 'user': 1041, 'user_name': 'J. Smith'}, 'Access denied - J. Smith (void)'),
    ({'code': 0x8B, 'user': 1041}, 'Access denied - User 1041 (void)'),
    ({'code': 0x4B, 'last_user_name': 'J. Smith'}, 'Access denied - Card rejected'),
    ({'code': 0xA7}, 'Door forced'),
    ({'code': 0xA9}, 'Door open too long'),
])
def test_activity_wording(data, expected):
    assert describe_access(data)[0] == expected


def test_entity_device_filters_and_historical_name_snapshot(activity_stack):
    async def run():
        hub, cls, describe = activity_stack()
        entity = await add_entity(hub, cls)
        deliver(hub, 0x92)
        event, = activities(hub)
        assert event.data['entity_id'] == entity.entity_id
        assert event.data['device_id'] == f'device_{entity.entity_id}'
        assert event.data['name'] == 'Front Entry Access'
        assert event.data['message'] == 'Access granted - J. Smith'
        hub.state.user_names[1041] = 'Changed Name'
        await entity.async_will_remove_from_hass()
        assert describe(event)['message'] == 'Access granted - J. Smith'
        assert len(activities(hub)) == 1
    asyncio.run(run())


def test_denials_and_egress_preserve_last_successful_user(activity_stack):
    async def run():
        hub, cls, _ = activity_stack()
        entity = await add_entity(hub, cls)
        deliver(hub, 0x92)
        before = dict(hub.state.last_access[17])
        deliver(hub, 0x8B, user=2050, seq=2, stamp=2)
        deliver(hub, 0x4B, seq=3, stamp=3)
        deliver(hub, 0x9D, user=0, seq=4, stamp=4)
        assert hub.state.last_access[17] == before
        assert [a.data['message'] for a in activities(hub)] == [
            'Access granted - J. Smith', 'Access denied - A. Jones (void)',
            'Access denied - Card rejected', 'Access granted (exit button)']
        assert entity.triggered[1][1]['last_user'] == 1041
        assert entity.triggered[2][1]['user'] is None
        assert hub._access_log[2]['raw_user_bytes'] is None
    asyncio.run(run())


def test_panel_and_door_isolation_and_no_startup_activity(activity_stack):
    async def run():
        hub, cls, _ = activity_stack()
        entity = await add_entity(hub, cls)
        assert not activities(hub)
        for entry_id, door, code in [('another-panel', 17, 0x92), ('test', 19, 0x92), ('test', 17, 0x96), ('test',17,0x8C)]:
            hub.hass.bus.async_fire(f'{const.DOMAIN}_ctplus_event', dict(entry_id=entry_id, object=door, code=code))
        assert not entity.triggered and not activities(hub)
        await entity.async_will_remove_from_hass()
        deliver(hub, 0x92)
        assert not activities(hub)
    asyncio.run(run())


def test_retransmissions_do_not_create_swipes_or_advance_last_access(activity_stack):
    async def run():
        hub, cls, _ = activity_stack()
        await add_entity(hub, cls)
        deliver(hub, 0x92)
        before = dict(hub.state.last_access[17])
        deliver(hub, 0x92)
        assert hub.state.last_access[17] == before
        assert len(hub._access_log) == len(activities(hub)) == 1
        deliver(hub, 0x92, seq=2, stamp=2)
        assert len(hub._access_log) == len(activities(hub)) == 2
    asyncio.run(run())


def test_card_redaction_in_frames_ack_raw_bus_and_dump(activity_stack):
    async def run():
        hub, cls, _ = activity_stack()
        await add_entity(hub, cls)
        frame = deliver(hub, 0x4B)
        deliver(hub, 0x4B)
        await asyncio.sleep(0)
        path = await hub.async_dump_debug()
        text = open(path).read()
        events = json.dumps([e.data for e in hub.hass.bus.events])
        assert CARD.hex() not in text + events
        assert frame.to_bytes().hex() not in text + events
        assert hub.state.last_event_raw == ''
        assert not hub.state.last_access
        dump = json.loads(text)
        assert dump['state']['access']['summary']['denied'] == 1
        assert len(activities(hub)) == 1
        assert any(e.get('ack_for_event', {}).get('denial_reason') == 'card_rejected' for e in dump['recent_frames'])
    asyncio.run(run())


def test_malformed_card_frame_is_redacted_without_inventing_denial(activity_stack):
    async def run():
        hub, cls, _ = activity_stack()
        await add_entity(hub, cls)
        frame = proto.Frame(proto.TYPE_EVENT_OR_DATA, 1, body=body(0x4B)[:-1])
        hub._on_ctplus_datagram(frame.to_bytes(), hub._udp_last_peer)
        text = open(await hub.async_dump_debug()).read()
        assert CARD.hex() not in text
        assert not activities(hub)
    asyncio.run(run())
