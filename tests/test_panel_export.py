"""Regression tests for CTPlus export.panel name imports."""

from __future__ import annotations

import json

from conftest import load


panel_export = load("panel_export")


def test_ctplus_raw_control_characters_do_not_break_import(tmp_path):
    """CTPlus sometimes emits literal newlines inside quoted descriptions."""
    metadata = json.dumps({"version": 1})
    export = {
        "panel": [
            {
                "areas": [[
                    {"tc_area": {"areano": 1}},
                    {"tc_basedevice": {"devicedesc": "Ground\nFloor"}},
                ]],
            },
            {
                "macros": [[
                    {"tc_macro": {"macrodesc": "Door release\n"}},
                ]],
            },
        ],
    }
    # json.dumps escapes newlines. Replace the escapes to reproduce the exact
    # invalid-but-generated form observed in a real CTPlus export.
    text = metadata + "\n" + json.dumps(export).replace("\\n", "\n")
    path = tmp_path / "export.panel"
    path.write_text(text, encoding="utf-8")

    names = panel_export.load_panel_export_names(str(path))

    assert names.loaded
    assert names.areas == {1: "Ground Floor"}


def test_malformed_optional_export_does_not_abort_setup(tmp_path, caplog):
    path = tmp_path / "export.panel"
    path.write_text('{"panel": [}', encoding="utf-8")

    names = panel_export.load_panel_export_names(str(path))

    assert not names.loaded
    assert "continuing without imported names" in caplog.text
