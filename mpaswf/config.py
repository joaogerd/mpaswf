"""Load, validate, and render MPASWF configuration data.

Configuration values are read from a YAML mapping and accessed through dotted
paths. Relative file-system paths are resolved against the directory containing
the configuration file so that interactive and batch executions use the same
location semantics.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import yaml


class ConfigurationError(ValueError):
    """Indicate that a required configuration field is absent or malformed."""


@dataclass(frozen=True)
class WorkflowConfig:
    """Store a parsed workflow configuration and its source path.

    Parameters
    ----------
    path : pathlib.Path
        Absolute path of the YAML configuration file.
    data : dict[str, Any]
        Parsed root mapping from the YAML document.

    Notes
    -----
    The dataclass is frozen, but nested objects contained in ``data`` remain
    mutable because the mapping is not recursively copied or frozen.
    """

    path: Path
    data: dict[str, Any]

    @property
    def root(self) -> Path:
        """Return the directory containing the configuration file.

        Returns
        -------
        pathlib.Path
            Parent directory of :attr:`path`.
        """
        return self.path.parent


def load_config(path: Path) -> WorkflowConfig:
    """Load and minimally validate one MPASWF YAML configuration.

    Parameters
    ----------
    path : pathlib.Path
        YAML configuration path. User-home expansion is supported, and the
        resulting path is resolved to an absolute path.

    Returns
    -------
    WorkflowConfig
        Parsed and minimally validated configuration.

    Raises
    ------
    FileNotFoundError
        Raised when ``path`` does not identify a regular file.
    yaml.YAMLError
        Propagated when the YAML document cannot be parsed.
    ConfigurationError
        Raised when the root document is not a mapping or a required field is
        absent or malformed.
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
    """Read a required mapping using dotted-path notation.

    Parameters
    ----------
    config : WorkflowConfig or mapping of str to Any
        Configuration object or mapping to traverse.
    key : str
        Dot-separated path such as ``"paths.work_dir"``.

    Returns
    -------
    dict[str, Any]
        Mapping stored at the requested path.

    Raises
    ------
    ConfigurationError
        Raised when any path component is absent or the resolved value is not
        a dictionary.
    """
    data: Any = config.data if isinstance(config, WorkflowConfig) else config
    for part in key.split("."):
        if not isinstance(data, Mapping) or part not in data:
            raise ConfigurationError(f"Required mapping is missing: {key}")
        data = data[part]
    if not isinstance(data, dict):
        raise ConfigurationError(f"Expected mapping at {key}, received {type(data).__name__}.")
    return data


def value(config: WorkflowConfig | Mapping[str, Any], key: str, *, required: bool = True, default: Any = None) -> Any:
    """Read a configuration value using dotted-path notation.

    Parameters
    ----------
    config : WorkflowConfig or mapping of str to Any
        Configuration object or mapping to traverse.
    key : str
        Dot-separated path to the requested value.
    required : bool, default=True
        Require every component of ``key`` to exist. When ``False``, a missing
        component causes ``default`` to be returned.
    default : Any, optional
        Value returned for a missing optional path.

    Returns
    -------
    Any
        Stored value, or ``default`` for a missing optional path.

    Raises
    ------
    ConfigurationError
        Raised when a required path is missing.
    """
    data: Any = config.data if isinstance(config, WorkflowConfig) else config
    for part in key.split("."):
        if not isinstance(data, Mapping) or part not in data:
            if required:
                raise ConfigurationError(f"Required configuration value is missing: {key}")
            return default
        data = data[part]
    return data


def string(config: WorkflowConfig | Mapping[str, Any], key: str, *, required: bool = True, default: str | None = None) -> str | None:
    """Read and validate a non-empty string configuration value.

    Parameters
    ----------
    config : WorkflowConfig or mapping of str to Any
        Configuration object or mapping to traverse.
    key : str
        Dot-separated path to the string value.
    required : bool, default=True
        Require the value to exist. Missing optional values return ``default``.
    default : str or None, optional
        Fallback used when ``required`` is ``False``.

    Returns
    -------
    str or None
        Non-empty configured string, or ``None`` for an absent optional value
        whose default is ``None``.

    Raises
    ------
    ConfigurationError
        Raised when the resolved value is not a non-empty string.
    """
    result = value(config, key, required=required, default=default)
    if result is None and not required:
        return None
    if not isinstance(result, str) or not result:
        raise ConfigurationError(f"Configuration value must be a non-empty string: {key}")
    return result


def resolve_path(config: WorkflowConfig, raw: str, context: Mapping[str, str] | None = None) -> Path:
    """Render and resolve a configured file-system path.

    Parameters
    ----------
    config : WorkflowConfig
        Loaded configuration whose parent directory defines the base for
        relative paths.
    raw : str
        Path text, optionally containing ``str.format`` placeholders.
    context : mapping of str to str, optional
        Placeholder values used to render ``raw``.

    Returns
    -------
    pathlib.Path
        Expanded absolute path. Absolute inputs are returned without resolving
        symbolic links; relative inputs are resolved against ``config.root``.

    Raises
    ------
    ConfigurationError
        Raised when ``raw`` references an unknown placeholder.

    Notes
    -----
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
        Supported placeholder values.

    Returns
    -------
    str
        Rendered text.

    Raises
    ------
    ConfigurationError
        Raised when ``template`` references a placeholder absent from
        ``context``.
    """
    try:
        return template.format(**context)
    except KeyError as error:
        raise ConfigurationError(f"Unknown template placeholder {error.args[0]!r} in {template!r}") from error


def validate_config(config: WorkflowConfig) -> None:
    """Validate the required first-version MPASWF configuration schema.

    Parameters
    ----------
    config : WorkflowConfig
        Parsed configuration to validate.

    Raises
    ------
    ConfigurationError
        Raised when a required section or string is absent, when
        ``campaign.leads_hours`` is not a list of integers, or when the
        execution backend is unsupported.

    Notes
    -----
    Validation is intentionally structural and limited to fields required by
    the current workflow. File existence and stage-specific constraints are
    checked later by the modules that consume each value.
    """
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
