"""Config entry migration tests.

Builds before path authentication became functional ignored the configured
computer password and always sent the panel's documented default. Every
installation that connects today is therefore using that default, whatever the
field contains. Honouring a stored value on upgrade would break any setup where
somebody had filled the field in optimistically, so the migration deliberately
overwrites it with the value that was actually in use.

These tests exist because getting this wrong breaks working installations
silently, and the failure looks like the panel being offline.
"""

from __future__ import annotations


import pytest

from tecom_cp import const  # noqa: E402  (see conftest.py)


def migrate(data: dict, options: dict) -> tuple[dict, dict]:
    """Mirror of the migration in __init__.py, callable without Home Assistant."""
    data, options = dict(data), dict(options)
    for store in (data, options):
        if const.CONF_ENCRYPTION_TYPE in store:
            current = str(store[const.CONF_ENCRYPTION_TYPE] or const.ENC_NONE)
            store[const.CONF_ENCRYPTION_TYPE] = const.LEGACY_ENCRYPTION_ALIASES.get(current, current)
    target = options if options else data
    target[const.CONF_AUTH_METHOD] = const.AUTH_METHOD_SECURITY_PASSWORD
    target[const.CONF_COMPUTER_PASSWORD] = const.DEFAULT_COMPUTER_PASSWORD
    return data, options


def merged(data: dict, options: dict) -> dict:
    """How the hub reads configuration."""
    return {**data, **options}


@pytest.mark.parametrize("stored_password", [
    "0000000000",   # left at the default
    "5551234567",   # filled in optimistically, previously ignored
    "",             # cleared
    "1111111111",
])
def test_existing_entries_keep_sending_the_default_password(stored_password):
    data = {"host": "192.168.1.50", const.CONF_COMPUTER_PASSWORD: stored_password}
    cfg = merged(*migrate(data, {"poll_interval": 3}))
    assert cfg[const.CONF_COMPUTER_PASSWORD] == const.DEFAULT_COMPUTER_PASSWORD
    assert cfg[const.CONF_AUTH_METHOD] == const.AUTH_METHOD_SECURITY_PASSWORD


def test_migration_writes_to_options_when_options_exist():
    data = {"host": "192.168.1.50"}
    options = {"poll_interval": 3}
    new_data, new_options = migrate(data, options)
    assert const.CONF_AUTH_METHOD in new_options
    assert const.CONF_AUTH_METHOD not in new_data


def test_migration_writes_to_data_when_there_are_no_options():
    data = {"host": "192.168.1.50"}
    new_data, new_options = migrate(data, {})
    assert const.CONF_AUTH_METHOD in new_data


@pytest.mark.parametrize("legacy,expected", [
    ("twofish", const.ENC_TWOFISH_128),
    ("aes128", const.ENC_AES_CBC_128),
    ("aes256", const.ENC_AES_CBC_256),
    ("none", const.ENC_NONE),
])
def test_legacy_encryption_values_are_mapped(legacy, expected):
    data = {"host": "x", const.CONF_ENCRYPTION_TYPE: legacy}
    cfg = merged(*migrate(data, {}))
    assert cfg[const.CONF_ENCRYPTION_TYPE] == expected


def test_current_encryption_values_are_left_alone():
    for value in const.ENCRYPTION_TYPES:
        cfg = merged(*migrate({"host": "x", const.CONF_ENCRYPTION_TYPE: value}, {}))
        assert cfg[const.CONF_ENCRYPTION_TYPE] == value


def test_unrelated_settings_survive_migration():
    data = {"host": "192.168.1.50", "send_port": 3001, "input_ranges": "1-16,31"}
    options = {"poll_interval": 3, "runtime_poll_inputs": True}
    cfg = merged(*migrate(data, options))
    assert cfg["host"] == "192.168.1.50"
    assert cfg["send_port"] == 3001
    assert cfg["input_ranges"] == "1-16,31"
    assert cfg["poll_interval"] == 3
    assert cfg["runtime_poll_inputs"] is True


def test_migrated_password_produces_the_previously_hardcoded_frame():
    """The whole point: the frame on the wire must not change."""
    from tecom_cp import ctplus_protocol as proto

    cfg = merged(*migrate({"host": "x", const.CONF_COMPUTER_PASSWORD: "9999999999"}, {}))
    frame = proto.cmd_session_auth_security_password(cfg[const.CONF_COMPUTER_PASSWORD])
    assert frame == bytes.fromhex("01060b0000000000")
