"""Resolve software published by the MONAN-JEDI runtime installation.

The normal runtime contract has one public root::

    <monan_jedi_root>/
        bin/
        lib/
        include/
        share/

MPASWF must not depend on MONAN-JEDI build trees, ecbuild source checkouts, or
versioned WPS staging directories. Historical ``executables.*`` settings remain
accepted only as a compatibility fallback for existing self-contained configs.
"""

from __future__ import annotations

from pathlib import Path
from typing import Mapping

from .config import ConfigurationError, WorkflowConfig, render, string, value


def monan_jedi_root(config: WorkflowConfig) -> Path | None:
    """Return the configured MONAN-JEDI public installation prefix, if any."""
    raw = string(config, "software.monan_jedi_root", required=False, default=None)
    if raw is None:
        return None
    path = Path(raw).expanduser()
    return path if path.is_absolute() else (config.root / path).resolve()


def installed_executable(config: WorkflowConfig, legacy_key: str, filename: str) -> Path:
    """Resolve one executable from the canonical prefix or a legacy override."""
    root = monan_jedi_root(config)
    if root is not None:
        return root / "bin" / filename

    raw = string(config, legacy_key, required=False, default=None)
    if raw is None:
        raise ConfigurationError(
            f"Configure software.monan_jedi_root or the legacy {legacy_key} path."
        )
    path = Path(raw).expanduser()
    return path if path.is_absolute() else (config.root / path).resolve()


def wps_executable(config: WorkflowConfig, filename: str) -> Path:
    """Resolve one WPS executable/helper from the public installation contract."""
    root = monan_jedi_root(config)
    if root is not None:
        return root / "bin" / filename

    legacy_root = string(config, "executables.wps_dir", required=False, default=None)
    if legacy_root is None:
        raise ConfigurationError(
            "Configure software.monan_jedi_root or the legacy executables.wps_dir path."
        )
    path = Path(legacy_root).expanduser()
    if not path.is_absolute():
        path = (config.root / path).resolve()
    return path / filename


def wps_vtable(config: WorkflowConfig, context: Mapping[str, str]) -> Path:
    """Resolve the GFS Vtable from the canonical share tree or legacy config."""
    root = monan_jedi_root(config)
    if root is not None:
        name = string(config, "wps.vtable_name", required=False, default="Vtable.GFS") or "Vtable.GFS"
        if Path(name).name != name:
            raise ConfigurationError("wps.vtable_name must be a filename, not a path.")
        return root / "share" / "wps" / "Variable_Tables" / name

    raw = string(config, "wps.vtable", required=False, default=None)
    if raw is None:
        legacy_root = string(config, "executables.wps_dir", required=False, default=None)
        if legacy_root is None:
            raise ConfigurationError(
                "Configure software.monan_jedi_root or legacy wps.vtable/executables.wps_dir settings."
            )
        raw = "{wps_dir}/ungrib/Variable_Tables/Vtable.GFS"
        context = {**context, "wps_dir": legacy_root}

    rendered = render(raw, context)
    path = Path(rendered).expanduser()
    return path if path.is_absolute() else (config.root / path).resolve()


def validate_software_contract(config: WorkflowConfig) -> None:
    """Validate that either the canonical prefix or the legacy layout is declared."""
    root = monan_jedi_root(config)
    if root is not None:
        return

    for key in (
        "executables.wps_dir",
        "executables.mpas_init",
        "executables.mpas_atmosphere",
    ):
        if value(config, key, required=False, default=None) is None:
            raise ConfigurationError(
                "software.monan_jedi_root is not configured and the legacy "
                f"software contract is incomplete: missing {key}."
            )
