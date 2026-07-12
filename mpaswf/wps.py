"""Stage and execute WPS for one MPAS initialization time.

The WPS stage acquires or reuses the configured GFS input, links the reference
WPS executables and Vtable, renders ``namelist.wps``, executes ``link_grib`` and
``ungrib``, and validates the expected ``FILE:`` intermediate product.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .commands import run_command
from .config import WorkflowConfig, render, string, value
from .files import ensure_directory, ensure_link, is_valid_file, render_template, write_json
from .gfs import ensure_gfs
from .layout import Layout
from .ui import status
from .model import render_time_context
from .validation import validate_file


def _argv(raw: object, context: dict[str, str], label: str) -> list[str]:
    """Validate and render a configured command argument list.

    Parameters
    ----------
    raw : object
        Candidate command representation expected to be a non-empty list of
        non-empty strings.
    context : dict[str, str]
        Placeholder values used to render each command token.
    label : str
        Configuration field name included in validation errors.

    Returns
    -------
    list[str]
        Rendered command tokens suitable for execution without a shell.

    Raises
    ------
    ValueError
        Raised when ``raw`` is not a non-empty list of non-empty strings.
    ConfigurationError
        Propagated when a token references an unknown placeholder.
    """
    if not isinstance(raw, list) or not raw or not all(isinstance(item, str) and item for item in raw):
        raise ValueError(f"{label} must be a non-empty list of strings.")
    return [render(item, context) for item in raw]


def wps_output_path(config: WorkflowConfig, layout: Layout, init_time: datetime) -> Path:
    """Resolve the declared WPS intermediate product path.

    Parameters
    ----------
    config : WorkflowConfig
        Loaded workflow configuration containing ``wps.output_template``.
    layout : Layout
        Resolved campaign directory layout.
    init_time : datetime
        Initialization timestamp used to select the WPS directory and render the
        output filename.

    Returns
    -------
    pathlib.Path
        Expected WPS product below the timestamp-specific WPS run directory.

    Raises
    ------
    ConfigurationError
        Propagated when the output template is missing, malformed, or references
        an unknown placeholder.
    """
    run_dir = layout.wps_dir(init_time)
    context = layout.context(init_time, init_time, 0, run_dir)
    output_name = render(string(config, "wps.output_template") or "", context)
    return run_dir / output_name


def prepare_wps(config: WorkflowConfig, layout: Layout, init_time: datetime, *, force: bool = False) -> Path:
    """Acquire GFS input, stage WPS files, and run ``ungrib``.

    Parameters
    ----------
    config : WorkflowConfig
        Loaded workflow configuration.
    layout : Layout
        Resolved campaign directory layout.
    init_time : datetime
        Initialization time of the required WPS product.
    force : bool, default=False
        Redownload or restage GFS and rerun WPS even when the expected ``FILE:``
        product already satisfies the configured minimum size.

    Returns
    -------
    pathlib.Path
        Validated WPS ``FILE:`` product.

    Raises
    ------
    FileNotFoundError
        Raised when the WPS installation, GFS input, Vtable, executable, or
        namelist template is missing.
    ValueError
        Raised when configured command argument lists are malformed.
    RuntimeError
        Propagated when GFS acquisition, an external WPS command, or final
        product validation fails.
    ConfigurationError
        Propagated when configured templates or required values are malformed.
    OSError
        Propagated when directories, links, logs, rendered files, or metadata
        cannot be created.

    Notes
    -----
    Existing WPS installations are not modified. ``link_grib.csh``,
    ``ungrib.exe``, and the Vtable are linked into the timestamp-specific run
    directory. Command output is retained in persistent log files.
    """
    run_dir = layout.wps_dir(init_time)
    output = wps_output_path(config, layout, init_time)
    minimum_size = int(value(config, "validation.minimum_size_bytes", required=False, default=1))
    label = init_time.strftime("%Y-%m-%d %HZ")
    if is_valid_file(output, minimum_size) and not force:
        status(f"WPS {label}: reusing {output.name}.")
        return output

    status(f"WPS {label}: staging GFS, Vtable, and namelist.")
    gfs = ensure_gfs(config, layout, init_time, force=force)
    ensure_directory(run_dir)
    context = layout.context(init_time, init_time, 0, run_dir)
    context.update({"gfs_file": str(gfs.path), "wps_file": str(output)})

    wps_root = Path(string(config, "executables.wps_dir") or "").expanduser()
    if not wps_root.is_dir():
        raise FileNotFoundError(f"WPS directory does not exist: {wps_root}")
    vtable_raw = string(config, "wps.vtable") or ""
    context["wps_dir"] = str(wps_root)
    vtable = Path(render(vtable_raw, context)).expanduser()
    if not vtable.is_absolute():
        vtable = (config.root / vtable).resolve()

    # Stage WPS executables as links to preserve the reference installation.
    ensure_link(wps_root / "link_grib.csh", run_dir / "link_grib.csh")
    ensure_link(wps_root / "ungrib.exe", run_dir / "ungrib.exe")
    ensure_link(vtable, run_dir / "Vtable")

    template_name = string(config, "templates.wps") or ""
    template = layout.templates_dir / template_name
    target_name = string(config, "wps.namelist_target", required=False, default="namelist.wps") or "namelist.wps"
    render_template(template, run_dir / target_name, context)

    metadata = run_dir / ".mpaswf" / "wps.json"
    write_json(
        metadata,
        {
            "init_time": context["init_time"],
            "gfs_file": str(gfs.path),
            "output": str(output),
            "state": "prepared",
        },
    )

    logs_dir = run_dir / "logs"
    link_argv = _argv(value(config, "wps.link_grib_command"), context, "wps.link_grib_command")
    ungrib_argv = _argv(value(config, "wps.ungrib_command"), context, "wps.ungrib_command")
    run_command(
        link_argv,
        cwd=run_dir,
        logs_dir=logs_dir,
        name="link_grib",
        label=f"WPS {label}: link_grib",
    )
    run_command(
        ungrib_argv,
        cwd=run_dir,
        logs_dir=logs_dir,
        name="ungrib",
        label=f"WPS {label}: ungrib",
    )
    validate_file(output, minimum_size, require_netcdf=False)
    status(f"WPS {label}: produced {output.name}.")
    write_json(metadata, {"init_time": context["init_time"], "gfs_file": str(gfs.path), "output": str(output), "state": "completed"})
    return output
