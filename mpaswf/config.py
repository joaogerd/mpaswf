"""Configuration loading, validation, and template rendering helpers.

MPASWF accepts two equivalent configuration layouts:

* one self-contained YAML document (the historical format); or
* a small platform YAML that points to a workflow contract through
  ``workflow.configuration``.

The split form mirrors the organization used by MPAS-BMatrix: machine-specific
paths, executables and PBS settings stay separate from campaign/scientific
settings.  The public CLI is unchanged; callers still pass exactly one
``--config`` path.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any, Mapping

import yaml


class ConfigurationError(ValueError):
    """Raised when a required configuration field is absent or malformed."""


@dataclass(frozen=True)
class WorkflowConfig:
    """Loaded workflow configuration.

    Parameters
    ----------
    path : pathlib.Path
        Absolute path of the platform or self-contained YAML passed to
        ``--config``.
    data : dict[str, Any]
        Fully merged, environment-expanded configuration.
    """

    path: Path
    data: dict[str, Any]

    @property
    def root(self) -> Path:
        """Return the directory containing the user-supplied configuration."""
        return self.path.parent


def _load_yaml(path: Path) -> dict[str, Any]:
    """Load one YAML mapping with an explicit, path-oriented error."""
    if not path.is_file():
        raise FileNotFoundError(f"Configuration file not found: {path}")
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as error:
        raise ConfigurationError(f"Invalid YAML in {path}: {error}") from error
    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise ConfigurationError(f"The root YAML document must be a mapping: {path}")
    return payload


def _deep_merge(base: Mapping[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    """Recursively merge mappings while treating lists as atomic values.

    The workflow contract is the base and the platform file is the override.
    This allows, for example, ``static.reference_time`` to live in the contract
    while ``static.links`` remains machine-specific in the platform document.
    Lists are replaced intentionally instead of concatenated implicitly.
    """
    result = deepcopy(dict(base))
    for key, item in override.items():
        previous = result.get(key)
        if isinstance(previous, Mapping) and isinstance(item, Mapping):
            result[key] = _deep_merge(previous, item)
        else:
            result[key] = deepcopy(item)
    return result


def _expand_env(item: Any) -> Any:
    """Expand shell environment variables recursively in decoded YAML values."""
    if isinstance(item, Mapping):
        return {str(key): _expand_env(value) for key, value in item.items()}
    if isinstance(item, list):
        return [_expand_env(value) for value in item]
    if isinstance(item, str):
        return os.path.expandvars(item)
    return item


def _workflow_contract_path(platform_path: Path, platform: Mapping[str, Any]) -> Path | None:
    """Resolve optional ``workflow.configuration`` relative to the platform file."""
    workflow = platform.get("workflow")
    if workflow is None:
        return None
    if not isinstance(workflow, Mapping):
        raise ConfigurationError("workflow must be a YAML mapping.")
    specification = workflow.get("configuration")
    if specification is None:
        return None
    if not isinstance(specification, str) or not specification.strip():
        raise ConfigurationError("workflow.configuration must be a non-empty YAML path.")
    candidate = Path(os.path.expandvars(specification)).expanduser()
    return candidate if candidate.is_absolute() else (platform_path.parent / candidate).resolve()


def load_config(path: Path) -> WorkflowConfig:
    """Load one self-contained config or a platform + workflow config pair.

    The command-line contract remains unchanged: callers provide one path with
    ``--config``.  When that document contains ``workflow.configuration``, the
    referenced workflow contract is loaded first and the platform document is
    deep-merged over it.  Existing all-in-one files continue to work exactly as
    before.
    """
    platform_path = Path(path).expanduser().resolve()
    platform = _expand_env(_load_yaml(platform_path))
    contract_path = _workflow_contract_path(platform_path, platform)

    if contract_path is None:
        merged = dict(platform)
    else:
        contract = _expand_env(_load_yaml(contract_path))
        merged = _deep_merge(contract, platform)
        # Provenance metadata is intentionally non-operational.  It helps
        # diagnostics without changing any existing configuration key.
        merged["workflow_contract_path"] = str(contract_path)

    config = WorkflowConfig(path=platform_path, data=merged)
    validate_config(config)
    return config


def mapping(config: WorkflowConfig | Mapping[str, Any], key: str) -> dict[str, Any]:
    """Read a required mapping using dotted-path notation."""
    data: Any = config.data if isinstance(config, WorkflowConfig) else config
    for part in key.split("."):
        if not isinstance(data, Mapping) or part not in data:
            raise ConfigurationError(f"Required mapping is missing: {key}")
        data = data[part]
    if not isinstance(data, dict):
        raise ConfigurationError(f"Expected mapping at {key}, received {type(data).__name__}.")
    return data


def value(config: WorkflowConfig | Mapping[str, Any], key: str, *, required: bool = True, default: Any = None) -> Any:
    """Read a scalar, list, or mapping using dotted-path notation."""
    data: Any = config.data if isinstance(config, WorkflowConfig) else config
    for part in key.split("."):
        if not isinstance(data, Mapping) or part not in data:
            if required:
                raise ConfigurationError(f"Required configuration value is missing: {key}")
            return default
        data = data[part]
    return data


def string(config: WorkflowConfig | Mapping[str, Any], key: str, *, required: bool = True, default: str | None = None) -> str | None:
    """Read a string configuration value."""
    result = value(config, key, required=required, default=default)
    if result is None and not required:
        return None
    if not isinstance(result, str) or not result:
        raise ConfigurationError(f"Configuration value must be a non-empty string: {key}")
    return result


def resolve_path(config: WorkflowConfig, raw: str, context: Mapping[str, str] | None = None) -> Path:
    """Render and resolve a configured file-system path.

    Relative paths are resolved against the platform/self-contained
    configuration directory, not the current working directory. Environment
    variables have already been expanded by ``load_config``.
    """
    rendered = render(raw, context or {})
    path = Path(rendered).expanduser()
    return path if path.is_absolute() else (config.root / path).resolve()


def render(template: str, context: Mapping[str, str]) -> str:
    """Render one explicit ``str.format`` template."""
    try:
        return template.format(**context)
    except KeyError as error:
        raise ConfigurationError(f"Unknown template placeholder {error.args[0]!r} in {template!r}") from error


def validate_config(config: WorkflowConfig) -> None:
    """Perform the intentionally small MPASWF schema validation."""
    for section in ("paths", "executables", "campaign", "gfs", "wps", "products", "templates", "static", "execution", "validation"):
        mapping(config, section)

    for key in (
        "paths.work_dir",
        "paths.static_dir",
        "paths.gfs_dir",
        "paths.cdct_templates_dir",
        "executables.wps_dir",
        "executables.mpas_init",
        "executables.mpas_atmosphere",
        "campaign.start_valid_time",
        "campaign.end_valid_time",
        "gfs.file_template",
        "wps.output_template",
        "products.init_state_template",
        "products.restart_template",
        "products.da_state_template",
        "templates.wps",
        "templates.static_namelist",
        "templates.static_streams",
        "templates.init_namelist",
        "templates.init_streams",
        "templates.forecast_namelist",
        "templates.forecast_streams",
        "static.reference_time",
        "static.product_template",
        "execution.backend",
    ):
        string(config, key)

    leads = value(config, "campaign.leads_hours")
    if not isinstance(leads, list) or not all(isinstance(item, int) for item in leads):
        raise ConfigurationError("campaign.leads_hours must be a list of integers.")

    backend = string(config, "execution.backend")
    if backend not in {"local", "pbs"}:
        raise ConfigurationError("execution.backend must be either 'local' or 'pbs'.")

    if backend == "pbs":
        mapping(config, "pbs")
        for key in ("pbs.queue", "pbs.walltime_static", "pbs.walltime_init", "pbs.walltime_forecast"):
            string(config, key)
