"""MPAS initialization staging, execution, PBS submission, and validation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .assets import stage_common_links
from .commands import run_command
from .config import WorkflowConfig, render, string, value
from .files import ensure_directory, ensure_link, is_valid_file, render_template, write_json
from .layout import Layout
from .pbs import render_pbs_job, submit_pbs, wait_pbs
from .software import installed_executable
from .validation import validate_file
from .static import load_static_run, validate_static
from .wps import wps_output_path
from .ui import status


@dataclass(frozen=True)
class InitRun:
    """Resolved MPAS initialization paths for one initialization time."""

    init_time: datetime
    run_dir: Path
    state_path: Path
    manifest_path: Path


def load_init_run(config: WorkflowConfig, layout: Layout, init_time: datetime) -> InitRun:
    """Resolve one initialization run without performing file-system changes."""
    run_dir = layout.init_dir(init_time)
    context = layout.context(init_time, init_time, 0, run_dir)
    state_name = render(string(config, "products.init_state_template") or "", context)
    return InitRun(init_time, run_dir, run_dir / state_name, run_dir / ".mpaswf" / "init.json")


def _validate_reference_setup(config: WorkflowConfig, run: InitRun, wps_file: Path) -> None:
    """Fail before PBS when the x1.10242 invariant-init contract is malformed."""
    enabled = bool(value(config, "validation.require_reference_preflight", required=False, default=False))
    if not enabled:
        return

    namelist_path = run.run_dir / "namelist.init_atmosphere"
    streams_path = run.run_dir / "streams.init_atmosphere"
    for path in (wps_file, namelist_path, streams_path, run.run_dir / "x1.10242.static.nc", run.run_dir / "x1.10242.graph.info.part.128"):
        if not path.exists():
            raise FileNotFoundError(f"MPAS init preflight input does not exist: {path}")

    namelist = namelist_path.read_text(encoding="utf-8")
    streams = streams_path.read_text(encoding="utf-8")
    expected_time = run.init_time.strftime("%Y-%m-%d_%H:00:00")
    required_namelist = (
        "config_init_case = 7",
        f"config_start_time = '{expected_time}'",
        f"config_stop_time = '{expected_time}'",
        "config_nvertlevels = 55",
        "config_met_prefix = 'GFS'",
        "config_sfc_prefix = 'GFS'",
        "config_static_interp = .false.",
        "config_native_gwd_static = .false.",
        "config_native_gwd_gsl_static = .false.",
        "config_vertical_grid = .true.",
        "config_met_interp = .true.",
        "config_block_decomp_file_prefix = 'x1.10242.graph.info.part.'",
    )
    for token in required_namelist:
        if token not in namelist:
            raise RuntimeError(f"MPAS init preflight: namelist is missing expected token: {token}")

    for token in ("x1.10242.static.nc", run.state_path.name, 'clobber_mode="overwrite"'):
        if token not in streams:
            raise RuntimeError(f"MPAS init preflight: streams file is missing expected token: {token}")

    status(f"MPAS init {run.init_time.strftime('%Y-%m-%d %HZ')}: reference preflight passed.")


def prepare_init(config: WorkflowConfig, layout: Layout, init_time: datetime, *, force: bool = False) -> InitRun:
    """Stage one MPAS initialization directory from validated invariant + GFS."""
    run = load_init_run(config, layout, init_time)
    minimum_size = int(value(config, "validation.minimum_size_bytes", required=False, default=1))
    if is_valid_file(run.state_path, minimum_size) and not force:
        status(f"MPAS init {init_time.strftime('%Y-%m-%d %HZ')}: reusing {run.state_path.name}.")
        return run

    status(f"MPAS init {init_time.strftime('%Y-%m-%d %HZ')}: staging run directory.")
    ensure_directory(run.run_dir)
    context = layout.context(init_time, init_time, 0, run.run_dir)
    wps_file = wps_output_path(config, layout, init_time)
    validate_file(wps_file, minimum_size)
    context.update({"wps_file": str(wps_file), "init_state": str(run.state_path)})

    ensure_link(wps_file, run.run_dir / wps_file.name)
    static_run = load_static_run(config, layout)
    validate_static(config, layout)
    ensure_link(static_run.state_path, run.run_dir / static_run.state_path.name)
    stage_common_links(config, run.run_dir, context)

    render_template(
        layout.templates_dir / (string(config, "templates.init_namelist") or ""),
        run.run_dir / "namelist.init_atmosphere",
        context,
    )
    render_template(
        layout.templates_dir / (string(config, "templates.init_streams") or ""),
        run.run_dir / "streams.init_atmosphere",
        context,
    )
    _validate_reference_setup(config, run, wps_file)
    write_json(
        run.manifest_path,
        {
            "init_time": context["init_time"],
            "run_dir": str(run.run_dir),
            "wps_file": str(wps_file),
            "state_path": str(run.state_path),
            "state": "prepared",
        },
    )
    return run


def execute_init(
    config: WorkflowConfig,
    layout: Layout,
    init_time: datetime,
    *,
    submit: bool,
    wait: bool,
    force: bool = False,
) -> InitRun:
    """Run, render, or submit one MPAS initialization stage."""
    run = prepare_init(config, layout, init_time, force=force)
    minimum_size = int(value(config, "validation.minimum_size_bytes", required=False, default=1))
    if is_valid_file(run.state_path, minimum_size) and not force:
        return run

    executable = installed_executable(config, "executables.mpas_init", "mpas_init_atmosphere")
    if not executable.is_file():
        raise FileNotFoundError(f"mpas_init_atmosphere executable does not exist: {executable}")
    backend = string(config, "execution.backend")
    context = layout.context(init_time, init_time, 0, run.run_dir)
    context.update({"init_state": str(run.state_path)})

    if backend == "local":
        run_command(
            [str(executable)],
            cwd=run.run_dir,
            logs_dir=run.run_dir / "logs",
            name="mpas_init",
            label=f"MPAS init {init_time.strftime('%Y-%m-%d %HZ')}",
        )
        validate_init(config, layout, init_time)
        return run

    walltime = string(config, "pbs.walltime_init") or ""
    job = render_pbs_job(
        config,
        run_dir=run.run_dir,
        job_name=f"mpasinit_{init_time.strftime('%Y%m%d%H')}",
        executable=executable,
        walltime=walltime,
        context=context,
        queue=string(config, "pbs.queue_init", required=False, default=string(config, "pbs.queue")),
        script_name=f"qsub_init_{init_time.strftime('%Y%m%d%H')}.pbs",
    )
    payload: dict[str, object] = {
        "init_time": context["init_time"],
        "run_dir": str(run.run_dir),
        "state_path": str(run.state_path),
        "pbs_script": str(job.script),
        "state": "rendered",
    }
    if submit:
        job_id = submit_pbs(config, job.script)
        payload.update({"job_id": job_id, "state": "submitted"})
        if wait:
            wait_pbs(config, job_id)
            validate_init(config, layout, init_time)
            payload["state"] = "completed"
    write_json(run.manifest_path, payload)
    return run


def validate_init(config: WorkflowConfig, layout: Layout, init_time: datetime) -> Path:
    """Validate one initialized MPAS state and, when requested, its model log."""
    run = load_init_run(config, layout, init_time)
    minimum_size = int(value(config, "validation.minimum_size_bytes", required=False, default=1))
    require_netcdf = bool(value(config, "validation.require_netcdf", required=False, default=False))
    validate_file(run.state_path, minimum_size, require_netcdf=require_netcdf)

    require_clean_log = bool(value(config, "validation.require_mpas_clean_log", required=False, default=False))
    log_path = run.run_dir / "log.init_atmosphere.0000.out"
    if require_clean_log:
        if not log_path.is_file():
            raise FileNotFoundError(f"MPAS init validation log does not exist: {log_path}")
        text = log_path.read_text(encoding="utf-8", errors="replace")
        for token in (
            "Critical error messages =            0",
            "Error messages =                     0",
        ):
            if token not in text:
                raise RuntimeError(f"MPAS init did not finish cleanly; missing {token!r} in {log_path}")

    report = run.manifest_path.with_name("init-validation.json")
    write_json(
        report,
        {
            "init_time": init_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "state_path": str(run.state_path),
            "log_path": str(log_path) if require_clean_log else None,
            "valid": True,
        },
    )
    return report
