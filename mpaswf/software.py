"""Resolve software published by the MONAN-JEDI runtime installation.

The normal runtime contract has one public root::

    <monan_jedi_install_root>/
        bin/
        lib/
        include/
        share/

MPASWF must not depend on MONAN-JEDI build trees, ecbuild source checkouts, or
versioned WPS staging directories. Historical ``executables.*`` settings remain
accepted only as a compatibility fallback for existing self-contained configs.
"""

from __future__ import annotations

import json
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .config import ConfigurationError, WorkflowConfig, render, string


@dataclass(frozen=True)
class RuntimeContract:
    """Installed MONAN-JEDI ecosystem contract v2."""

    path: Path
    stack_env_name: str
    stack_env_module: str
    stack_site_setup: str
    module_root_template: str
    capabilities: dict[str, bool]

    def module_root(self, stack_root: Path) -> Path:
        return stack_root / self.module_root_template.format(env_name=self.stack_env_name)


def runtime_contract(config: WorkflowConfig) -> RuntimeContract:
    """Load the runtime contract from the configured public install prefix."""
    root = monan_jedi_root(config)
    if root is None:
        raise ConfigurationError(
            "The ecosystem runtime contract requires software.monan_jedi_install_root."
        )
    path = root / "share" / "monan-jedi" / "install-manifest.json"
    if not path.is_file():
        raise ConfigurationError(f"MONAN-JEDI runtime contract not found: {path}")
    try:
        payload: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ConfigurationError(f"Invalid MONAN-JEDI runtime contract: {path}: {error}") from error
    if not isinstance(payload, dict):
        raise ConfigurationError("MONAN-JEDI runtime contract root must be a JSON object.")
    if payload.get("ecosystem_contract_version") != 2:
        raise ConfigurationError(
            "MONAN-JEDI installation does not provide ecosystem contract v2; "
            "reinstall MONAN-JEDI with the current producer."
        )
    if payload.get("contract") != "monan-jedi-runtime-v2":
        raise ConfigurationError("Unsupported MONAN-JEDI runtime contract identifier.")
    if payload.get("public_anchors") != ["MONAN_JEDI_INSTALL_ROOT", "STACK_ROOT"]:
        raise ConfigurationError("Unexpected MONAN-JEDI public anchor set.")

    stack = payload.get("stack")
    if not isinstance(stack, dict):
        raise ConfigurationError("Runtime contract stack block is missing.")
    for key in ("env_name", "env_module", "site_setup", "module_root_template"):
        if not isinstance(stack.get(key), str) or not stack[key]:
            raise ConfigurationError(f"Runtime contract stack.{key} must be a non-empty string.")

    capabilities = payload.get("capabilities")
    if not isinstance(capabilities, dict) or not all(
        isinstance(key, str) and isinstance(value, bool)
        for key, value in capabilities.items()
    ):
        raise ConfigurationError("Runtime contract capabilities must map strings to booleans.")

    return RuntimeContract(
        path=path,
        stack_env_name=stack["env_name"],
        stack_env_module=stack["env_module"],
        stack_site_setup=stack["site_setup"],
        module_root_template=stack["module_root_template"],
        capabilities=dict(capabilities),
    )


def monan_jedi_root(config: WorkflowConfig) -> Path | None:
    """Return the configured MONAN-JEDI public installation prefix, if any.

    ``software.monan_jedi_install_root`` is the canonical key. The historical
    ``software.monan_jedi_root`` spelling remains accepted during migration.
    """
    raw = string(
        config,
        "software.monan_jedi_install_root",
        required=False,
        default=None,
    )
    if raw is None:
        raw = string(config, "software.monan_jedi_root", required=False, default=None)
        if raw is not None:
            warnings.warn(
                "software.monan_jedi_root is deprecated; use "
                "software.monan_jedi_install_root",
                DeprecationWarning,
                stacklevel=2,
            )
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
            f"Configure software.monan_jedi_install_root or the legacy {legacy_key} path."
        )
    path = Path(raw).expanduser()
    return path if path.is_absolute() else (config.root / path).resolve()


def atmosphere_share(config: WorkflowConfig) -> Path:
    """Resolve the public MPAS atmosphere runtime-data directory."""
    root = monan_jedi_root(config)
    if root is not None:
        return root / "share" / "MPAS" / "core_atmosphere"

    raw = string(config, "executables.mpas_atmosphere_share", required=False, default=None)
    if raw is None:
        raise ConfigurationError(
            "Configure software.monan_jedi_install_root or the legacy "
            "executables.mpas_atmosphere_share path."
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
            "Configure software.monan_jedi_install_root or the legacy executables.wps_dir path."
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

    # Historical configs use {wps_dir} inside wps.vtable. Preserve that render
    # context even when an explicit legacy Vtable template is present.
    legacy_root = string(config, "executables.wps_dir", required=False, default=None)
    if legacy_root is None:
        raise ConfigurationError(
            "Configure software.monan_jedi_install_root or the legacy executables.wps_dir path."
        )
    legacy_context = {**context, "wps_dir": legacy_root}
    raw = string(
        config,
        "wps.vtable",
        required=False,
        default="{wps_dir}/ungrib/Variable_Tables/Vtable.GFS",
    ) or "{wps_dir}/ungrib/Variable_Tables/Vtable.GFS"

    rendered = render(raw, legacy_context)
    path = Path(rendered).expanduser()
    return path if path.is_absolute() else (config.root / path).resolve()
