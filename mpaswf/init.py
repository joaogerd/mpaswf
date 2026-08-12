"""MPAS initialization staging, execution, PBS submission, and validation."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .assets import stage_common_links
from .commands import run_command
from .config import WorkflowConfig, render, string, value
from .files import ensure_directory, ensure_link, is_valid_file, render_template, write_json
from .layout import Layout
from .pbs import render_pbs_job, submit_pbs, wait_pbs
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


def prepare_init(config: WorkflowConfig, layout: Layout, init_time: datetime, *, force: bool = False) -> InitRun:
    """Stage one MPAS initialization directory from the CD-CT reference case."""
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

    # Keep the WPS intermediate under its conventional name in the init directory.
    ensure_link(wps_file, run.run_dir / wps_file.name)
    # Dynamic initialization consumes the static product generated once per mesh.
    static_run = load_static_run(config, layout)
    validate_static(config, layout)
    ensure_link(static_run.state_path, run.run_dir / static_run.state_path.name)
    stage_common_links(config, run.run_dir, context)

    render_template(layout.templates_dir / (string(config, "templates.init_namelist") or ""), run.run_dir / "namelist.init_atmosphere", context)
    render_template(layout.templates_dir / (string(config, "templates.init_streams") or ""), run.run_dir / "streams.init_atmosphere", context)
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
    """Run, render, or submit one MPAS initialization stage.

    With `execution.backend: local`, the executable runs immediately. With
    `execution.backend: pbs`, a PBS script is always rendered; it is submitted
    only when `submit=True`.
    """
    run = prepare_init(config, layout, init_time, force=force)
    minimum_size = int(value(config, "validation.minimum_size_bytes", required=False, default=1))
    if is_valid_file(run.state_path, minimum_size) and not force:
        return run

    executable = Path(string(config, "executables.mpas_init") or "").expanduser()
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
    """Validate one initialized MPAS state and persist a small report."""
    run = load_init_run(config, layout, init_time)
    minimum_size = int(value(config, "validation.minimum_size_bytes", required=False, default=1))
    require_netcdf = bool(value(config, "validation.require_netcdf", required=False, default=False))
    validate_file(run.state_path, minimum_size, require_netcdf=require_netcdf)
    report = run.manifest_path.with_name("init-validation.json")
    write_json(report, {"init_time": init_time.strftime("%Y-%m-%dT%H:%M:%SZ"), "state_path": str(run.state_path), "valid": True})
    return report
