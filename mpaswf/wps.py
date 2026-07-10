"""WPS staging and execution for one MPAS initialization time."""

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
    """Render a configured argv list without shell evaluation."""
    if not isinstance(raw, list) or not raw or not all(isinstance(item, str) and item for item in raw):
        raise ValueError(f"{label} must be a non-empty list of strings.")
    return [render(item, context) for item in raw]


def wps_output_path(config: WorkflowConfig, layout: Layout, init_time: datetime) -> Path:
    """Return the declared WPS intermediate product path."""
    run_dir = layout.wps_dir(init_time)
    context = layout.context(init_time, init_time, 0, run_dir)
    output_name = render(string(config, "wps.output_template") or "", context)
    return run_dir / output_name


def prepare_wps(config: WorkflowConfig, layout: Layout, init_time: datetime, *, force: bool = False) -> Path:
    """Download/stage GFS plus WPS inputs and run `link_grib` and `ungrib`.

    Parameters
    ----------
    config : WorkflowConfig
        Loaded configuration.
    layout : Layout
        Resolved directory layout.
    init_time : datetime
        WPS product time.
    force : bool, default=False
        Re-run WPS even when the expected `FILE:` product is valid.

    Returns
    -------
    pathlib.Path
        Validated WPS `FILE:` product.
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
