"""Opportunity Workbench application package.

The repository historically exposed its FastAPI instance from the top-level
``app.py`` module.  The lazy compatibility attribute keeps ``from app import
app`` and ``uvicorn app:app`` working while domain modules live in this package.
"""

from __future__ import annotations

from importlib import util
from pathlib import Path
from types import ModuleType
from typing import Any
import sys

_LEGACY_MODULE_NAME = "_opportunity_workbench_legacy_app"
_legacy_module: ModuleType | None = None


def _load_legacy_module() -> ModuleType:
    global _legacy_module
    if _legacy_module is not None:
        return _legacy_module

    source = Path(__file__).resolve().parents[1] / "app.py"
    spec = util.spec_from_file_location(_LEGACY_MODULE_NAME, source)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load the application module at {source}")

    module = util.module_from_spec(spec)
    sys.modules[_LEGACY_MODULE_NAME] = module
    spec.loader.exec_module(module)
    _legacy_module = module
    return module


def __getattr__(name: str) -> Any:
    if name in {"app", "AnalysisPayload"}:
        return getattr(_load_legacy_module(), name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["app", "AnalysisPayload"]
