"""One-time MPAS static/invariant preparation for the campaign.

MPASWF supports two explicit modes:

* generate the static product with ``mpas_init_atmosphere`` from mesh/geography;
* reuse a validated precomputed invariant/static NetCDF supplied by
  ``static.source``.

The x1.10242 JACI/NMC case uses the second mode because that invariant was
already consolidated and validated for the MPAS-JEDI tutorial workflow.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .assets import stage_common_links
from .commands import run_command
from .config import WorkflowConfig, render, resolve_path, string, value
from .files import ensure_directory, ensure_link, is_valid_file, render_template, write_json
from .layout import Layout
from .model import parse_time
from .pbs import render_pbs_job, submit_pbs, wait_pbs
from .software import installed_executable
from .validation import validate_file
from .ui import status


@dataclass(frozen=True)
class StaticRun:
    """Resolved paths for the one-time static/invariant stage."""

    reference_time: datetime
    run_dir: Path
    state_path: Path
    manifest_path: Path


def load_static_run(config: WorkflowConfig, layout: Layout) -> StaticRun:
    """Resolve static-stage paths without modifying the file system."""
    reference_time = parse_time(string(config, "static.reference_time") or "")
    run_dir = layout.static_dir
    context = layout.context(reference_time, reference_time, 0, run_dir)
    product_name = render(string(config, "static.product_template") or "", context)
    return StaticRun(
        reference_time=reference_time,
        run_dir=run_dir,
        state_path=run_dir / product_name,
        manifest_path=run_dir / ".mpaswf" / "static.json",
    )


def _configured_static_source(config: WorkflowConfig, run: StaticRun) -> Path | None:
    """Resolve an optional precomputed invariant/static source."""
    raw = string(config, "static.source", required=False, default=None)
    if raw is None:
        return None
    context = {
        "static_state": str(run.state_path),
        "static_dir": str(run.run_dir),
    }
    return resolve_path(config, raw, context)


def prepare_static(
    config: WorkflowConfig,
    layout: Layout,
    *,
    force: bool = False,
) -> StaticRun:
    """Stage a precomputed invariant or a generated static interpolation run."""
    run = load_static_run(config, layout)
    minimum_size = int(value(config, "validation.minimum_size_bytes", required=False, default=1))
    source = _configured_static_source(config, run)

    if source is not None:
        validate_file(source, minimum_size)
        ensure_directory(run.run_dir)
        ensure_link(source, run.state_path)
        write_json(
            run.manifest_path,
            {
                "reference_time": run.reference_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "run_dir": str(run.run_dir),
                "source_path": str(source),
                "state_path": str(run.state_path),
                "state": "external-invariant",
            },
        )
        status(f"Static MPAS product: using validated invariant {source}.")
        return run

    if is_valid_file(run.state_path, minimum_size) and not force:
        status(f"Static MPAS product: reusing {run.state_path}.")
        return run

    status(f"Static MPAS product: staging interpolation in {run.run_dir}.")
    ensure_directory(run.run_dir)
    context = layout.context(run.reference_time, run.reference_time, 0, run.run_dir)
    context.update({"static_state": str(run.state_path)})

    stage_common_links(config, run.run_dir, context)
    render_template(
        layout.templates_dir / (string(config, "templates.static_namelist") or ""),
        run.run_dir / "namelist.init_atmosphere",
        context,
    )
    render_template(
        layout.templates_dir / (string(config, "templates.static_streams") or ""),
        run.run_dir / "streams.init_atmosphere",
        context,
    )
    write_json(
        run.manifest_path,
        {
            "reference_time": run.reference_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "run_dir": str(run.run_dir),
            "state_path": str(run.state_path),
            "state": "prepared",
        },
    )
    return run


def execute_static(
    config: WorkflowConfig,
    layout: Layout,
    *,
    submit: bool,
    wait: bool,
    force: bool = False,
) -> StaticRun:
    """Run/render static interpolation, or immediately validate an invariant."""
    run = prepare_static(config, layout, force=force)
    minimum_size = int(value(config, "validation.minimum_size_bytes", required=False, default=1))

    if _configured_static_source(config, run) is not None:
        validate_static(config, layout)
        return run

    if is_valid_file(run.state_path, minimum_size) and not force:
        return run

    executable = installed_executable(config, "executables.mpas_init", "mpas_init_atmosphere")
    if not executable.is_file():
        raise FileNotFoundError(f"mpas_init_atmosphere executable does not exist: {executable}")
    backend = string(config, "execution.backend")
    context = layout.context(run.reference_time, run.reference_time, 0, run.run_dir)
    context.update({"static_state": str(run.state_path)})

    if backend == "local":
        run_command(
            [str(executable)],
            cwd=run.run_dir,
            logs_dir=run.run_dir / "logs",
            name="mpas_static",
            label="MPAS static interpolation",
        )
        validate_static(config, layout)
        return run

    walltime = string(config, "pbs.walltime_static") or ""
    job = render_pbs_job(
        config,
        run_dir=run.run_dir,
        job_name="mpasstatic",
        executable=executable,
        walltime=walltime,
        context=context,
        queue=string(config, "pbs.queue_static", required=False, default=string(config, "pbs.queue")),
        script_name="qsub_static.pbs",
    )
    payload: dict[str, object] = {
        "reference_time": context["init_time"],
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
            validate_static(config, layout)
            payload["state"] = "completed"
    write_json(run.manifest_path, payload)
    return run


def validate_static(config: WorkflowConfig, layout: Layout) -> Path:
    """Validate the prepared mesh-level invariant/static product."""
    run = load_static_run(config, layout)
    minimum_size = int(value(config, "validation.minimum_size_bytes", required=False, default=1))
    require_netcdf = bool(value(config, "validation.require_netcdf", required=False, default=False))
    validate_file(run.state_path, minimum_size, require_netcdf=require_netcdf)
    report = run.manifest_path.with_name("static-validation.json")
    write_json(
        report,
        {
            "reference_time": run.reference_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "state_path": str(run.state_path),
            "valid": True,
        },
    )
    return report
