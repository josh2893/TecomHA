"""Exercise the real setup/options flows without installing Home Assistant.

The HA doubles cover only form results, selectors and sections; Voluptuous
performs schema validation and the integration's flow methods run unchanged.
Frontend errors must target a top-level section: ha-form-expandable does not
pass field errors into its nested ha-form (Home Assistant frontend).
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from types import ModuleType, SimpleNamespace

import pytest
import voluptuous as vol

from conftest import INTEGRATION_DIR
from tecom_cp import const


@pytest.fixture
def flow_module(monkeypatch):
    class Flow:
        def __init_subclass__(cls, **kwargs):
            pass

        async def async_set_unique_id(self, unique_id):
            self.unique_id = unique_id

        def _abort_if_unique_id_configured(self):
            pass

        def async_show_form(self, **kwargs):
            return {"type": "form", **kwargs}

        def async_create_entry(self, **kwargs):
            return {"type": "create_entry", **kwargs}

    class Section:
        def __init__(self, schema, options):
            self.schema = schema
            self.options = options

        def __call__(self, data):
            return self.schema(data)

    class TextSelector:
        def __init__(self, config):
            self.config = config

        def __call__(self, data):
            return vol.Schema(str)(data)

    class SelectSelector(TextSelector):
        def __call__(self, data):
            return vol.In([option["value"] for option in self.config["options"]])(data)

    class NumberSelector(TextSelector):
        def __call__(self, data):
            return vol.All(vol.Coerce(float), vol.Range(
                min=self.config["min"], max=self.config["max"],
            ))(data)

    class BooleanSelector:
        def __call__(self, data):
            return vol.Schema(bool)(data)

    ha = ModuleType("homeassistant")
    ha.config_entries = SimpleNamespace(ConfigFlow=Flow, OptionsFlow=Flow)
    helpers = ModuleType("homeassistant.helpers")
    helpers.selector = SimpleNamespace(
        TextSelector=TextSelector, TextSelectorConfig=dict,
        TextSelectorType=SimpleNamespace(PASSWORD="password", TEXT="text"),
        SelectSelector=SelectSelector, SelectSelectorConfig=dict,
        SelectSelectorMode=SimpleNamespace(DROPDOWN="dropdown"),
        NumberSelector=NumberSelector, NumberSelectorConfig=dict,
        NumberSelectorMode=SimpleNamespace(BOX="box"),
        BooleanSelector=BooleanSelector,
    )
    data_entry_flow = ModuleType("homeassistant.data_entry_flow")
    data_entry_flow.section = Section
    for name, module in (
        ("homeassistant", ha), ("homeassistant.helpers", helpers),
        ("homeassistant.data_entry_flow", data_entry_flow),
    ):
        monkeypatch.setitem(sys.modules, name, module)
    spec = importlib.util.spec_from_file_location(
        "tecom_cp.config_flow", INTEGRATION_DIR / "config_flow.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def start(module, screen):
    if screen == "setup":
        flow = module.TecomChallengerPlusConfigFlow()
        step = flow.async_step_user
    else:
        entry = SimpleNamespace(
            data={"host": "192.168.1.50", "computer_password": "0000000000"},
            options={"input_ranges": "1-16,31", "poll_interval": 7,
                     "runtime_poll_inputs": True, "user_sync_enabled": False},
        )
        flow = module.TecomChallengerPlusOptionsFlow(entry)
        step = flow.async_step_init
    return step, asyncio.run(step())


def submit(module, step, form, changes):
    # Untouched controls use their schema defaults, as in a submitted HA form.
    data = {section: {} for section in module.SECTION_KEYS}
    data["connection"]["host"] = "192.168.1.50"
    for section, fields in changes.items():
        data[section].update(fields)
    validated = form["data_schema"](data)
    return asyncio.run(step(validated))


def assert_visible_error(form, section, code):
    assert form["type"] == "form"
    assert form["errors"][section] == code
    assert set(form["errors"]).issubset(form["data_schema"].schema)
    assert form["data_schema"].schema[section].options["collapsed"] is False


@pytest.mark.parametrize("screen", ["setup", "options"])
def test_ten_character_aes256_key_with_default_security_password(flow_module, screen):
    m = flow_module
    step, form = start(m, screen)
    result = submit(m, step, form, {"authentication": {
        "encryption_type": const.ENC_AES_CBC_256, "encryption_key": "Ab12Cd34Ef",
    }})
    assert result["type"] == "create_entry"
    assert result["data"]["computer_password"] == "0000000000"
    assert result["data"]["encryption_key"] == "Ab12Cd34Ef"
    assert result["data"]["encryption_type"] == const.ENC_AES_CBC_256
    assert not set(m.SECTION_KEYS) & result["data"].keys()
    if screen == "options":
        assert result["data"]["poll_interval"] == 7
        assert result["data"]["input_ranges"] == "1-16,31"
        assert result["data"]["runtime_poll_inputs"] is True
        assert result["data"]["user_sync_enabled"] is False


@pytest.mark.parametrize("screen", ["setup", "options"])
@pytest.mark.parametrize("fields,code", [
    ({"computer_password": ""}, "security_password_format"),
    ({"encryption_key": ""}, "encryption_key_required"),
    ({"encryption_key": "Ab12-Cd34!"}, "key_not_alphanumeric"),
    ({"encryption_key": "x" * 33}, "key_too_long"),
])
def test_invalid_authentication_is_visible_and_can_be_corrected(flow_module, screen, fields, code):
    m = flow_module
    step, form = start(m, screen)
    submitted = {"computer_password": "0000000000",
                 "encryption_type": const.ENC_AES_CBC_256,
                 "encryption_key": "Ab12Cd34Ef", **fields}
    result = submit(m, step, form, {
        "authentication": submitted, "objects": {"input_ranges": "1-16,31"},
    })
    assert_visible_error(result, "authentication", code)
    # Retry must retain the host, password, cipher, key and unrelated edits.
    retained = m.flatten_sections(result["data_schema"]({k: {} for k in m.SECTION_KEYS}))
    assert retained["host"] == "192.168.1.50"
    assert retained["input_ranges"] == "1-16,31"
    for key, value in submitted.items():
        assert retained[key] == value
    corrected = submit(m, step, result, {"authentication": {
        "computer_password": "0000000000", "encryption_key": "Ab12Cd34Ef",
    }})
    assert corrected["type"] == "create_entry"
    assert corrected["data"]["encryption_type"] == const.ENC_AES_CBC_256


def test_setup_host_error_is_visible_without_losing_authentication(flow_module):
    m = flow_module
    step, form = start(m, "setup")
    result = submit(m, step, form, {
        "connection": {"host": ""}, "authentication": {
            "encryption_type": const.ENC_AES_CBC_256, "encryption_key": "Ab12Cd34Ef",
        },
    })
    assert_visible_error(result, "connection", "host_required")
    corrected = submit(m, step, result, {"connection": {"host": "192.168.1.50"}})
    assert corrected["type"] == "create_entry"
    assert corrected["data"]["encryption_key"] == "Ab12Cd34Ef"


@pytest.mark.parametrize("field,value,code", [
    ("computer_password", "\u0661" * 10, "security_password_format"),
    ("encryption_key", "\u00e9" * 10, "key_not_alphanumeric"),
    ("auth_username", "", "auth_username_required"),
    ("auth_username", "\u00e9", "auth_username_ascii"),
    ("auth_username", "x" * 31, "auth_username_too_long"),
    ("auth_password", "\u00e9", "auth_password_ascii"),
    ("auth_password", "x" * 17, "auth_password_too_long"),
])
def test_credentials_rejected_before_ascii_wire_encoding(flow_module, field, value, code):
    m = flow_module
    step, form = start(m, "options")
    fields = {"encryption_type": const.ENC_AES_CBC_256, "encryption_key": "Ab12Cd34Ef"}
    if field.startswith("auth_"):
        fields.update(auth_method=const.AUTH_METHOD_CREDENTIALS, auth_username="operator")
    fields[field] = value
    result = submit(m, step, form, {"authentication": fields})
    assert_visible_error(result, "authentication", code)
    translations = json.loads((INTEGRATION_DIR / "translations/en.json").read_text())
    for screen in ("config", "options"):
        assert code in translations[screen]["error"]


@pytest.mark.parametrize("cipher,limit", [
    (const.ENC_AES_CBC_128, 16), (const.ENC_AES_CBC_256, 32), (const.ENC_TWOFISH_128, 16),
])
def test_existing_cipher_key_limits_remain_supported(flow_module, cipher, limit):
    step, form = start(flow_module, "options")
    result = submit(flow_module, step, form, {"authentication": {
        "encryption_type": cipher, "encryption_key": "A" * limit,
    }})
    assert result["type"] == "create_entry"


def test_no_encryption_and_path_credentials_still_save(flow_module):
    step, form = start(flow_module, "options")
    result = submit(flow_module, step, form, {"authentication": {
        "auth_method": const.AUTH_METHOD_CREDENTIALS, "auth_username": "operator",
        "auth_password": "Path-Password!", "encryption_type": const.ENC_NONE,
        "encryption_key": "", "computer_password": "",
    }})
    assert result["type"] == "create_entry"
