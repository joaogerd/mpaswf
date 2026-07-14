"""WPS staging and execution for one MPAS initialization time."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .commands import run_command
from .config import WorkflowConfig, render, string, value
from .files import ensure_directory, ensure_link, is_valid_file, render_template, write_json
from .gfs import ensure_gfs
from .layout import Layout
from .ui import status
from .validation import validate_file


@dataclass(frozen=True)
class WPSRuntime:
    """Resolved WPS runtime published for use by MPASWF.

    Parameters
    ----------
    root : pathlib.Path
        Runtime installation root. For the MONAN-JEDI publication this is the
        directory containing ``bin`` and ``share/wps``.
    bin_dir : pathlib.Path
        Directory containing ``ungrib.exe`` and ``link_grib.csh``.
    ungrib : pathlib.Path
        Resolved ``ungrib.exe`` executable.
    link_grib : pathlib.Path
        Resolved ``link_grib.csh`` helper.
    """

    root: Path
    bin_dir: Path
    ungrib: Path
    link_grib: Path


def _argv(raw: object, context: dict[str, str], label: str) -> list[str]:
    """Render a configured argv list without shell evaluation."""
    if not isinstance(raw, list) or not raw or not all(isinstance(item, str) and item for item in raw):
        raise ValueError(f"{label} must be a non-empty list of strings.")
    return [render(item, context) for item in raw]


def resolve_wps_runtime(config: WorkflowConfig) -> WPSRuntime:
    """Resolve either a MONAN-JEDI install root or a direct WPS binary directory.

    ``executables.wps_dir`` may point to the MONAN-JEDI installation root, whose
    executables live below ``bin``, or directly to a directory containing the
    two WPS runtime programs. Supporting both forms preserves compatibility with
    legacy WPS installations while making the MONAN-JEDI publication layout the
    preferred contract.

    Parameters
    ----------
    config : WorkflowConfig
        Loaded MPASWF configuration.

    Returns
    -------
    WPSRuntime
        Resolved runtime root, binary directory, and executable paths.

    Raises
    ------
    FileNotFoundError
        Raised when neither supported layout contains both required programs.
    """
    configured = Path(string(config, "executables.wps_dir") or "").expanduser()
    candidates = (configured, configured / "bin")

    for bin_dir in candidates:
        ungrib = bin_dir / "ungrib.exe"
        link_grib = bin_dir / "link_grib.csh"
        if not ungrib.is_file() or not link_grib.is_file():
            continue

        if bin_dir == configured / "bin":
            root = configured
        elif configured.name == "bin" and (configured.parent / "share" / "wps").is_dir():
            root = configured.parent
        else:
            root = configured

        return WPSRuntime(
            root=root.resolve(),
            bin_dir=bin_dir.resolve(),
            ungrib=ungrib.resolve(),
            link_grib=link_grib.resolve(),
        )

    attempted = ", ".join(str(path) for path in candidates)
    raise FileNotFoundError(
        "WPS runtime is incomplete. Expected ungrib.exe and link_grib.csh in one of: "
        f"{attempted}"
    )


def wps_output_path(config: WorkflowConfig, layout: Layout, init_time: datetime) -> Path:
    """Return the declared WPS intermediate product path."""
    run_dir = layout.wps_dir(init_time)
    context = layout.context(init_time, init_time, 0, run_dir)
    output_name = render(string(config, "wps.output_template") or "", context)
    return run_dir / output_name


def _clean_generated_files(run_dir: Path) -> None:
    """Remove only WPS-generated links and intermediate products before a rerun."""
    for pattern in ("GRIBFILE.*", "FILE:*", "PFILE:*"):
        for path in run_dir.glob(pattern):
            if path.is_file() or path.is_symlink():
                path.unlink()


def prepare_wps(config: WorkflowConfig, layout: Layout, init_time: datetime, *, force: bool = False) -> Path:
    """Stage GFS plus WPS inputs and run ``link_grib`` and ``ungrib``.

    Parameters
    ----------
    config : WorkflowConfig
        Loaded configuration.
    layout : Layout
        Resolved directory layout.
    init_time : datetime
        WPS product time.
    force : bool, default=False
        Re-run WPS even when the expected ``FILE:`` product is valid. A valid
        local GFS input is still reused; forcing the prepare phase does not
        redownload external input data.

    Returns
    -------
    pathlib.Path
        Validated WPS ``FILE:`` product.
    """
    run_dir = layout.wps_dir(init_time)
    output = wps_output_path(config, layout, init_time)
    minimum_size = int(value(config, "validation.minimum_size_bytes", required=False, default=1))
    label = init_time.strftime("%Y-%m-%d %HZ")
    if is_valid_file(output, minimum_size) and not force:
        status(f"WPS {label}: reusing {output.name}.")
        return output

    runtime = resolve_wps_runtime(config)
    ensure_directory(run_dir)
    _clean_generated_files(run_dir)

    context = layout.context(init_time, init_time, 0, run_dir)
    context.update(
        {
            # Keep ``wps_dir`` as the direct binary directory for compatibility
            # with existing configurations, while exposing explicit new names.
            "wps_dir": str(runtime.bin_dir),
            "wps_bin_dir": str(runtime.bin_dir),
            "wps_root": str(runtime.root),
            "wps_file": str(output),
        }
    )

    vtable_raw = string(config, "wps.vtable") or ""
    vtable = Path(render(vtable_raw, context)).expanduser()
    if not vtable.is_absolute():
        vtable = (config.root / vtable).resolve()
    if not vtable.is_file():
        raise FileNotFoundError(f"WPS Vtable does not exist: {vtable}")

    status(f"WPS {label}: staging GFS, Vtable, and namelist.")
    # ``force`` controls regeneration of the WPS product, not acquisition of an
    # external GFS input. Existing valid GRIB files remain reusable and offline
    # campaigns with ``url_template: null`` continue to work.
    gfs = ensure_gfs(config, layout, init_time, force=False)
    context["gfs_file"] = str(gfs.path)

    # Stage WPS executables as links to preserve the reference installation.
    ensure_link(runtime.link_grib, run_dir / "link_grib.csh")
    ensure_link(runtime.ungrib, run_dir / "ungrib.exe")
    ensure_link(vtable, run_dir / "Vtable")

    template_name = string(config, "templates.wps") or ""
    template = layout.templates_dir / template_name
    target_name = string(config, "wps.namelist_target", required=False, default="namelist.wps") or "namelist.wps"
    render_template(template, run_dir / target_name, context)

    metadata = run_dir / ".mpaswf" / "wps.json"
    metadata_payload = {
        "init_time": context["init_time"],
        "gfs_file": str(gfs.path),
        "output": str(output),
        "wps_root": str(runtime.root),
        "wps_bin_dir": str(runtime.bin_dir),
        "ungrib": str(runtime.ungrib),
        "link_grib": str(runtime.link_grib),
        "vtable": str(vtable),
    }
    write_json(metadata, {**metadata_payload, "state": "prepared"})

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
    write_json(metadata, {**metadata_payload, "state": "completed"})
    return output
