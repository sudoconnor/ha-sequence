"""Load Sequence modules without importing Home Assistant."""

from __future__ import annotations

import importlib.util
import pathlib
import sys
import types

ROOT = pathlib.Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "custom_components" / "sequence"


def ensure_sequence_package() -> None:
    """Register the integration package without executing its Home Assistant init."""

    if "custom_components" not in sys.modules:
        package = types.ModuleType("custom_components")
        package.__path__ = [str(ROOT / "custom_components")]
        sys.modules["custom_components"] = package
    else:
        sys.modules["custom_components"].__path__ = [str(ROOT / "custom_components")]
    if "custom_components.sequence" not in sys.modules:
        package = types.ModuleType("custom_components.sequence")
        package.__path__ = [str(COMPONENT)]
        sys.modules["custom_components.sequence"] = package


def load_sequence_module(name: str):
    """Load one integration module by file path."""

    ensure_sequence_package()
    qualified = f"custom_components.sequence.{name}"
    if qualified in sys.modules:
        return sys.modules[qualified]
    spec = importlib.util.spec_from_file_location(qualified, COMPONENT / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[qualified] = module
    spec.loader.exec_module(module)
    return module
