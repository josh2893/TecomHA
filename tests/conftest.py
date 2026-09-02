"""Test setup.

These tests exercise the protocol, crypto and migration logic, none of which
needs Home Assistant. Importing the integration as a real package would run
``__init__.py`` and pull Home Assistant in, so instead a stand-in package is
registered whose ``__path__`` points at the integration directory. Relative
imports inside the modules (``from .twofish import Twofish``) then resolve
normally, while ``__init__.py`` is never executed.

Tests import from ``tecom_cp`` rather than ``tecom_challengerplus`` to make it
obvious that this is the dependency-free view of the package.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

INTEGRATION_DIR = (
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "tecom_challengerplus"
)

PACKAGE = "tecom_cp"


def _register_package() -> types.ModuleType:
    if PACKAGE in sys.modules:
        return sys.modules[PACKAGE]
    pkg = types.ModuleType(PACKAGE)
    pkg.__path__ = [str(INTEGRATION_DIR)]
    sys.modules[PACKAGE] = pkg
    return pkg


def load(name: str) -> types.ModuleType:
    """Import one integration module in isolation."""
    _register_package()
    full = f"{PACKAGE}.{name}"
    if full in sys.modules:
        return sys.modules[full]
    spec = importlib.util.spec_from_file_location(full, INTEGRATION_DIR / f"{name}.py")
    if spec is None or spec.loader is None:  # pragma: no cover
        raise ImportError(f"Cannot load {name} from {INTEGRATION_DIR}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[full] = module
    spec.loader.exec_module(module)
    return module


# Loaded once at collection so the modules are importable as tecom_cp.<name>.
_register_package()
for _name in ("twofish", "ctplus_protocol", "ctplus_crypto", "const"):
    load(_name)
