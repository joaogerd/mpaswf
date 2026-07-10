"""Configuration loading, validation, and template rendering helpers."""

from __future__ import annotations

from dataclasses import dataclass
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
        Absolute path of the YAML file.
    data : dict[str, Any]
        Parsed configuration data.
    """

    path: Path
    data: dict[str, Any]

    @property
    def root(self) -> Path:
        """Return the directory containing the configuration file."""
        return self.path.parent


def load_config(path: Path) -> WorkflowConfig:
    """Load and validate one minimal `mpaswf` configuration file.

    Parameters
    ----------
    path : pathlib.Path
        YAML configuration path.

    Returns
    -------
    WorkflowConfig
        Parsed, minimally validated configuration.
    """
    path = path.expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Configuration file not found: {path}")
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ConfigurationError("The root YAML document must be a mapping.")
    config = WorkflowConfig(path=path, data=payload)
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

    Relative paths are resolved against the configuration directory, not the
    current working directory. This keeps PBS and interactive execution
    consistent.
    """
    rendered = render(raw, context or {})
    path = Path(rendered).expanduser()
    return path if path.is_absolute() else (config.root / path).resolve()


def render(template: str, context: Mapping[str, str]) -> str:
    """Render one explicit ``str.format`` template.

    Parameters
    ----------
    template : str
        Input template string.
    context : mapping of str to str
        Supported placeholders.

    Returns
    -------
    str
        Rendered text.

    Raises
    ------
    ConfigurationError
        Raised when a template references an unknown placeholder.
    """
    try:
        return template.format(**context)
    except KeyError as error:
        raise ConfigurationError(f"Unknown template placeholder {error.args[0]!r} in {template!r}") from error


def validate_config(config: WorkflowConfig) -> None:
    """Perform the intentionally small first-version schema validation."""
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
