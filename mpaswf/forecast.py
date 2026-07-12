"""Stage, execute, submit, and validate MPAS forecast runs.

Each forecast request uses an already validated MPAS initial state and produces
both restart and ``da_state`` products. Local execution and PBS submission share
the same deterministic run-directory contract and persistent JSON metadata.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .commands import run_command
from .config import WorkflowConfig, render, string, value
from .files import ensure_link, is_valid_file, render_template, write_json
from .assets import stage_common_links
from .init import load_init_run, validate_init
from .layout import Layout
from .model import ForecastRequest
from .pbs import render_pbs_job, submit_pbs, wait_pbs
from .validation import validate_file
from .ui import status


@dataclass(frozen=True)
class ForecastRun:
    """Store resolved paths for one MPAS forecast request.

    Parameters
    ----------
    request : ForecastRequest
        Initialization time, valid time, and lead time of the forecast.
    run_dir : pathlib.Path
        Stage-specific forecast working directory.
    restart_path : pathlib.Path
        Expected MPAS restart product.
    da_state_path : pathlib.Path
        Expected MPAS analysis-state product.
    manifest_path : pathlib.Path
        Persistent JSON state file for the forecast stage.
    """

    request: ForecastRequest
    run_dir: Path
    restart_path: Path
    da_state_path: Path
    manifest_path: Path


def load_forecast_run(config: WorkflowConfig, layout: Layout, request: ForecastRequest) -> ForecastRun:
    """Resolve a forecast run without modifying the file system.

    Parameters
    ----------
    config : WorkflowConfig
        Loaded workflow configuration containing product filename templates.
    layout : Layout
        Resolved campaign directory layout.
    request : ForecastRequest
        Forecast request used to determine the run directory and render product
        names.

    Returns
    -------
    ForecastRun
        Resolved forecast directory, products, and metadata path.

    Raises
    ------
    ConfigurationError
        Propagated when a required product template is missing or references an
        unknown placeholder.
    """
    run_dir = layout.forecast_dir(request.init_time, request.lead_hours)
    context = layout.context(request.init_time, request.valid_time, request.lead_hours, run_dir)
    restart = run_dir / render(string(config, "products.restart_template") or "", context)
    da_state = run_dir / render(string(config, "products.da_state_template") or "", context)
    return ForecastRun(request, run_dir, restart, da_state, run_dir / ".mpaswf" / "forecast.json")


def prepare_forecast(config: WorkflowConfig, layout: Layout, request: ForecastRequest, *, force: bool = False) -> ForecastRun:
    """Stage one MPAS forecast directory from a validated initial state.

    Parameters
    ----------
    config : WorkflowConfig
        Loaded workflow configuration.
    layout : Layout
        Resolved campaign directory layout.
    request : ForecastRequest
        Forecast initialization, valid time, and lead time.
    force : bool, default=False
        Restage the directory even when both expected forecast products already
        satisfy the configured minimum size.

    Returns
    -------
    ForecastRun
        Forecast run contract after reuse or staging.

    Raises
    ------
    FileNotFoundError
        Propagated when the required initial state, shared asset, or template is
        missing.
    RuntimeError
        Propagated when validation of the initial state fails.
    ConfigurationError
        Propagated when configuration values or template placeholders are
        malformed.
    OSError
        Propagated when directories, links, rendered templates, or metadata
        cannot be created.

    Notes
    -----
    Reuse is based on basic file-size checks for both forecast products. During
    staging, the initial state is validated, linked into the run directory, and
    accompanied by shared assets and rendered atmosphere templates.
    """
    run = load_forecast_run(config, layout, request)
    minimum_size = int(value(config, "validation.minimum_size_bytes", required=False, default=1))
    if is_valid_file(run.restart_path, minimum_size) and is_valid_file(run.da_state_path, minimum_size) and not force:
        status(
            f"MPAS forecast {request.init_time.strftime('%Y-%m-%d %HZ')} f{request.lead_hours:03d}: "
            "reusing validated products."
        )
        return run

    status(
        f"MPAS forecast {request.init_time.strftime('%Y-%m-%d %HZ')} f{request.lead_hours:03d}: "
        "staging run directory."
    )
    run.run_dir.mkdir(parents=True, exist_ok=True)
    init_run = load_init_run(config, layout, request.init_time)
    validate_init(config, layout, request.init_time)
    context = layout.context(request.init_time, request.valid_time, request.lead_hours, run.run_dir)
    context.update(
        {
            "init_state": str(init_run.state_path),
            "restart_path": str(run.restart_path),
            "da_state_path": str(run.da_state_path),
        }
    )

    # CD-CT streams commonly expect an initial state under a local fixed name.
    ensure_link(init_run.state_path, run.run_dir / init_run.state_path.name)
    stage_common_links(config, run.run_dir, context)
    render_template(layout.templates_dir / (string(config, "templates.forecast_namelist") or ""), run.run_dir / "namelist.atmosphere", context)
    render_template(layout.templates_dir / (string(config, "templates.forecast_streams") or ""), run.run_dir / "streams.atmosphere", context)
    write_json(
        run.manifest_path,
        {
            "init_time": context["init_time"],
            "valid_time": context["valid_time"],
            "lead_hours": request.lead_hours,
            "run_dir": str(run.run_dir),
            "restart_path": str(run.restart_path),
            "da_state_path": str(run.da_state_path),
            "state": "prepared",
        },
    )
    return run


def execute_forecast(
    config: WorkflowConfig,
    layout: Layout,
    request: ForecastRequest,
    *,
    submit: bool,
    wait: bool,
    force: bool = False,
) -> ForecastRun:
    """Execute locally or render and optionally submit one forecast stage.

    Parameters
    ----------
    config : WorkflowConfig
        Loaded workflow configuration.
    layout : Layout
        Resolved campaign directory layout.
    request : ForecastRequest
        Forecast request to process.
    submit : bool
        Submit the rendered PBS job when the configured backend is ``pbs``.
    wait : bool
        Wait for a submitted PBS job and validate its products before returning.
    force : bool, default=False
        Ignore reusable forecast products and rerun or rerender the stage.

    Returns
    -------
    ForecastRun
        Forecast run contract after reuse, local execution, PBS rendering,
        submission, or completion.

    Raises
    ------
    FileNotFoundError
        Raised when the configured ``mpas_atmosphere`` executable or a required
        staged input is missing.
    RuntimeError
        Propagated when command execution, PBS submission, or product validation
        fails.
    ValueError
        Propagated when PBS command configuration is malformed.

    Notes
    -----
    With a local backend, the executable runs immediately and products are
    validated. With a PBS backend, a script is always rendered; submission and
    waiting are controlled independently by ``submit`` and ``wait``.
    """
    run = prepare_forecast(config, layout, request, force=force)
    minimum_size = int(value(config, "validation.minimum_size_bytes", required=False, default=1))
    complete = is_valid_file(run.restart_path, minimum_size) and is_valid_file(run.da_state_path, minimum_size)
    if complete and not force:
        return run

    executable = Path(string(config, "executables.mpas_atmosphere") or "").expanduser()
    if not executable.is_file():
        raise FileNotFoundError(f"mpas_atmosphere executable does not exist: {executable}")
    backend = string(config, "execution.backend")
    context = layout.context(request.init_time, request.valid_time, request.lead_hours, run.run_dir)
    context.update({"restart_path": str(run.restart_path), "da_state_path": str(run.da_state_path)})

    if backend == "local":
        run_command(
            [str(executable)],
            cwd=run.run_dir,
            logs_dir=run.run_dir / "logs",
            name="mpas_atmosphere",
            label=f"MPAS forecast {request.init_time.strftime('%Y-%m-%d %HZ')} f{request.lead_hours:03d}",
        )
        validate_forecast(config, layout, request)
        return run

    walltime = string(config, "pbs.walltime_forecast") or ""
    job = render_pbs_job(
        config,
        run_dir=run.run_dir,
        job_name=f"mpasf{request.lead_hours:03d}_{request.init_time.strftime('%Y%m%d%H')}",
        executable=executable,
        walltime=walltime,
        context=context,
        queue=string(config, "pbs.queue_forecast", required=False, default=string(config, "pbs.queue")),
    )
    payload: dict[str, object] = {
        "init_time": context["init_time"],
        "valid_time": context["valid_time"],
        "lead_hours": request.lead_hours,
        "run_dir": str(run.run_dir),
        "restart_path": str(run.restart_path),
        "da_state_path": str(run.da_state_path),
        "pbs_script": str(job.script),
        "state": "rendered",
    }
    if submit:
        job_id = submit_pbs(config, job.script)
        payload.update({"job_id": job_id, "state": "submitted"})
        if wait:
            wait_pbs(config, job_id)
            validate_forecast(config, layout, request)
            payload["state"] = "completed"
    write_json(run.manifest_path, payload)
    return run


def validate_forecast(config: WorkflowConfig, layout: Layout, request: ForecastRequest) -> Path:
    """Validate restart and ``da_state`` products and write a report.

    Parameters
    ----------
    config : WorkflowConfig
        Loaded workflow configuration containing validation settings.
    layout : Layout
        Resolved campaign directory layout.
    request : ForecastRequest
        Forecast request whose products are validated.

    Returns
    -------
    pathlib.Path
        Path to ``forecast-validation.json`` beside the stage manifest.

    Raises
    ------
    FileNotFoundError
        Raised when either expected product is absent or too small.
    RuntimeError
        Raised when optional NetCDF validation is requested but unavailable or
        a product cannot be opened as NetCDF.
    OSError
        Propagated when the validation report cannot be written.
    """
    run = load_forecast_run(config, layout, request)
    minimum_size = int(value(config, "validation.minimum_size_bytes", required=False, default=1))
    require_netcdf = bool(value(config, "validation.require_netcdf", required=False, default=False))
    validate_file(run.restart_path, minimum_size, require_netcdf=require_netcdf)
    validate_file(run.da_state_path, minimum_size, require_netcdf=require_netcdf)
    report = run.manifest_path.with_name("forecast-validation.json")
    write_json(
        report,
        {
            "init_time": request.init_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "valid_time": request.valid_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "lead_hours": request.lead_hours,
            "restart_path": str(run.restart_path),
            "da_state_path": str(run.da_state_path),
            "valid": True,
        },
    )
    return report
