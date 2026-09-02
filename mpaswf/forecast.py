"""MPAS forecast staging, execution, PBS submission, and validation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import re
from xml.etree import ElementTree as ET

from .assets import stage_common_links
from .commands import run_command
from .config import WorkflowConfig, render, resolve_path, string, value
from .files import ensure_link, is_valid_file, render_template, write_json
from .init import load_init_run, validate_init
from .layout import Layout
from .model import ForecastRequest
from .pbs import render_pbs_job, submit_pbs, wait_pbs
from .software import atmosphere_share, installed_executable
from .static import load_static_run, validate_static
from .validation import validate_file
from .ui import status


REFERENCE_PHYSICS_FILES = (
    "CAM_ABS_DATA.DBL",
    "CAM_AEROPT_DATA.DBL",
    "GENPARM.TBL",
    "LANDUSE.TBL",
    "OZONE_DAT.TBL",
    "RRTMG_LW_DATA",
    "RRTMG_LW_DATA.DBL",
    "RRTMG_SW_DATA",
    "RRTMG_SW_DATA.DBL",
    "SOILPARM.TBL",
    "VEGPARM.TBL",
)

REFERENCE_STREAM_LISTS = (
    "stream_list.atmosphere.analysis",
    "stream_list.atmosphere.background",
    "stream_list.atmosphere.control",
    "stream_list.atmosphere.ensemble",
)


@dataclass(frozen=True)
class ForecastRun:
    """Resolved output paths for one MPAS forecast request."""

    request: ForecastRequest
    run_dir: Path
    restart_path: Path
    da_state_path: Path
    manifest_path: Path


def load_forecast_run(config: WorkflowConfig, layout: Layout, request: ForecastRequest) -> ForecastRun:
    """Resolve one forecast run without mutating the file system."""
    run_dir = layout.forecast_dir(request.init_time, request.lead_hours)
    context = layout.context(request.init_time, request.valid_time, request.lead_hours, run_dir)
    restart = run_dir / render(string(config, "products.restart_template") or "", context)
    da_state = run_dir / render(string(config, "products.da_state_template") or "", context)
    return ForecastRun(request, run_dir, restart, da_state, run_dir / ".mpaswf" / "forecast.json")


def _reference_enabled(config: WorkflowConfig) -> bool:
    return bool(value(config, "validation.require_reference_preflight", required=False, default=False))


def _tutorial_dir(config: WorkflowConfig) -> Path:
    raw = string(config, "static.tutorial_physics_files", required=False, default=None)
    if raw is None:
        raise FileNotFoundError(
            "The x1.10242 reference forecast requires static.tutorial_physics_files."
        )
    return resolve_path(config, raw)


def _patch_namelist(text: str, replacements: dict[str, str]) -> str:
    """Patch required MPAS namelist keys and fail if the reference changed."""
    missing: list[str] = []
    for key, replacement in replacements.items():
        pattern = rf"(^\s*{re.escape(key)}\s*=\s*)[^,\n]*(.*)$"
        updated, count = re.subn(
            pattern,
            rf"\g<1>{replacement}\g<2>",
            text,
            flags=re.MULTILINE,
        )
        if count == 0:
            missing.append(key)
        text = updated
    if missing:
        raise RuntimeError(
            "MPAS forecast reference namelist is missing expected options: "
            + ", ".join(missing)
        )
    return text


def _find_stream(root: ET.Element, name: str) -> ET.Element | None:
    for child in root:
        if child.get("name") == name:
            return child
    return None


def _ensure_restart_stream(root: ET.Element, output_interval: str) -> None:
    restart = _find_stream(root, "restart")
    if restart is None:
        restart = ET.Element("stream")
        insert_at = 0
        for index, child in enumerate(list(root)):
            if child.tag == "immutable_stream":
                insert_at = index + 1
        root.insert(insert_at, restart)
    restart.set("name", "restart")
    restart.set("type", "output")
    restart.set("filename_template", "restart.$Y-$M-$D_$h.$m.$s.nc")
    restart.set("filename_interval", "output_interval")
    restart.set("output_interval", output_interval)
    restart.set("clobber_mode", "overwrite")


def _stage_reference_runtime(config: WorkflowConfig, run: ForecastRun) -> tuple[Path, Path]:
    """Stage installed MPAS physics files and validated tutorial stream lists."""
    share = atmosphere_share(config)
    if not share.is_dir():
        raise FileNotFoundError(f"Installed MPAS atmosphere share does not exist: {share}")

    for source in share.iterdir():
        if source.is_file() and source.name not in {"namelist.atmosphere", "streams.atmosphere"}:
            ensure_link(source, run.run_dir / source.name)

    tutorial = _tutorial_dir(config)
    if not tutorial.is_dir():
        raise FileNotFoundError(f"MPAS-JEDI tutorial runtime directory does not exist: {tutorial}")
    for name in REFERENCE_STREAM_LISTS:
        ensure_link(tutorial / name, run.run_dir / name)

    namelist_source = tutorial / "namelist.atmosphere_240km"
    streams_source = tutorial / "streams.atmosphere_240km"
    if not namelist_source.is_file():
        raise FileNotFoundError(f"Reference 240-km namelist does not exist: {namelist_source}")
    if not streams_source.is_file():
        raise FileNotFoundError(f"Reference 240-km streams file does not exist: {streams_source}")
    return namelist_source, streams_source


def _render_reference_forecast(
    config: WorkflowConfig,
    run: ForecastRun,
    namelist_source: Path,
    streams_source: Path,
) -> None:
    """Render the proven NMC x1.10242 forecast settings for one request."""
    request = run.request
    config_dt = int(value(config, "runtime.config_dt"))
    output_interval = string(config, "runtime.output_interval") or "24:00:00"
    start_time = request.init_time.strftime("%Y-%m-%d_%H:%M:%S")
    run_duration = f"{request.lead_hours // 24}_{request.lead_hours % 24:02d}:00:00"

    namelist = namelist_source.read_text(encoding="utf-8", errors="replace")
    namelist = _patch_namelist(
        namelist,
        {
            "config_dt": f"{float(config_dt):.1f}",
            "config_start_time": f"'{start_time}'",
            "config_run_duration": f"'{run_duration}'",
            "config_do_restart": ".false.",
            "config_block_decomp_file_prefix": "'x1.10242.graph.info.part.'",
            "config_sst_update": ".false.",
            "config_sstdiurn_update": ".false.",
            "config_deepsoiltemp_update": ".false.",
            "config_do_DAcycling": ".true.",
            "config_jedi_da": ".true.",
        },
    )
    (run.run_dir / "namelist.atmosphere").write_text(namelist, encoding="utf-8")

    tree = ET.parse(streams_source)
    root = tree.getroot()

    invariant = _find_stream(root, "invariant")
    if invariant is None:
        invariant = ET.SubElement(root, "immutable_stream")
        invariant.set("name", "invariant")
    invariant.set("type", "input")
    invariant.set("filename_template", "x1.10242.invariant.nc")
    invariant.set("input_interval", "initial_only")

    input_stream = _find_stream(root, "input")
    if input_stream is None:
        input_stream = ET.SubElement(root, "immutable_stream")
        input_stream.set("name", "input")
    input_stream.set("type", "input")
    input_stream.set("filename_template", "init.nc")
    input_stream.set("input_interval", "initial_only")

    da_state = _find_stream(root, "da_state")
    if da_state is None:
        da_state = ET.SubElement(root, "immutable_stream")
        da_state.set("name", "da_state")
    da_state.set("type", "output")
    da_state.set("precision", da_state.get("precision", "single"))
    da_state.set("io_type", da_state.get("io_type", "pnetcdf,cdf5"))
    da_state.set("filename_template", "mpasout.$Y-$M-$D_$h.$m.$s.nc")
    da_state.set("packages", "jedi_da")
    da_state.set("output_interval", output_interval)
    da_state.set("filename_interval", "output_interval")
    da_state.set("clobber_mode", "overwrite")

    _ensure_restart_stream(root, output_interval)

    for stream_name in ("output", "diagnostics"):
        stream = _find_stream(root, stream_name)
        if stream is not None:
            stream.set("type", "none")
            stream.set("output_interval", "none")

    tree.write(run.run_dir / "streams.atmosphere", encoding="unicode")


def _validate_reference_setup(config: WorkflowConfig, run: ForecastRun) -> None:
    """Fail before PBS if the NMC x1.10242 forecast contract is incomplete."""
    if not _reference_enabled(config):
        return

    required_paths = [
        run.run_dir / "init.nc",
        run.run_dir / "x1.10242.invariant.nc",
        run.run_dir / "x1.10242.grid.nc",
        run.run_dir / "x1.10242.graph.info",
        run.run_dir / "x1.10242.graph.info.part.128",
        run.run_dir / "namelist.atmosphere",
        run.run_dir / "streams.atmosphere",
    ]
    required_paths.extend(run.run_dir / name for name in REFERENCE_STREAM_LISTS)
    required_paths.extend(run.run_dir / name for name in REFERENCE_PHYSICS_FILES)
    for path in required_paths:
        if not path.exists():
            raise FileNotFoundError(f"MPAS forecast preflight input does not exist: {path}")

    config_dt = int(value(config, "runtime.config_dt"))
    output_interval = string(config, "runtime.output_interval") or "24:00:00"
    request = run.request
    start_time = request.init_time.strftime("%Y-%m-%d_%H:%M:%S")
    run_duration = f"{request.lead_hours // 24}_{request.lead_hours % 24:02d}:00:00"
    namelist = (run.run_dir / "namelist.atmosphere").read_text(encoding="utf-8", errors="replace")
    streams = (run.run_dir / "streams.atmosphere").read_text(encoding="utf-8", errors="replace")

    required_namelist = (
        f"config_dt = {float(config_dt):.1f}",
        f"config_start_time = '{start_time}'",
        f"config_run_duration = '{run_duration}'",
        "config_do_restart = .false.",
        "config_do_DAcycling = .true.",
        "config_jedi_da = .true.",
        "config_block_decomp_file_prefix = 'x1.10242.graph.info.part.'",
    )
    for token in required_namelist:
        if token not in namelist:
            raise RuntimeError(f"MPAS forecast preflight: namelist is missing expected token: {token}")

    required_streams = (
        'filename_template="x1.10242.invariant.nc"',
        'filename_template="init.nc"',
        'name="da_state"',
        'filename_template="mpasout.$Y-$M-$D_$h.$m.$s.nc"',
        'packages="jedi_da"',
        f'output_interval="{output_interval}"',
        'filename_interval="output_interval"',
        'clobber_mode="overwrite"',
        'name="restart"',
        'filename_template="restart.$Y-$M-$D_$h.$m.$s.nc"',
    )
    for token in required_streams:
        if token not in streams:
            raise RuntimeError(f"MPAS forecast preflight: streams is missing expected token: {token}")

    status(
        f"MPAS forecast {request.init_time.strftime('%Y-%m-%d %HZ')} "
        f"f{request.lead_hours:03d}: reference preflight passed."
    )


def prepare_forecast(config: WorkflowConfig, layout: Layout, request: ForecastRequest, *, force: bool = False) -> ForecastRun:
    """Stage one MPAS forecast directory using a validated initial state."""
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

    if _reference_enabled(config):
        ensure_link(init_run.state_path, run.run_dir / "init.nc")
        static_run = load_static_run(config, layout)
        validate_static(config, layout)
        ensure_link(static_run.state_path, run.run_dir / "x1.10242.invariant.nc")
        stage_common_links(config, run.run_dir, context)
        namelist_source, streams_source = _stage_reference_runtime(config, run)
        _render_reference_forecast(config, run, namelist_source, streams_source)
        _validate_reference_setup(config, run)
    else:
        ensure_link(init_run.state_path, run.run_dir / init_run.state_path.name)
        stage_common_links(config, run.run_dir, context)
        render_template(
            layout.templates_dir / (string(config, "templates.forecast_namelist") or ""),
            run.run_dir / "namelist.atmosphere",
            context,
        )
        render_template(
            layout.templates_dir / (string(config, "templates.forecast_streams") or ""),
            run.run_dir / "streams.atmosphere",
            context,
        )

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


def _forecast_walltime(config: WorkflowConfig, lead_hours: int) -> str:
    key = f"pbs.walltime_forecast_f{lead_hours:03d}"
    default = string(config, "pbs.walltime_forecast") or ""
    return string(config, key, required=False, default=default) or default


def execute_forecast(
    config: WorkflowConfig,
    layout: Layout,
    request: ForecastRequest,
    *,
    submit: bool,
    wait: bool,
    force: bool = False,
) -> ForecastRun:
    """Run, render, or submit one MPAS forecast stage."""
    run = prepare_forecast(config, layout, request, force=force)
    minimum_size = int(value(config, "validation.minimum_size_bytes", required=False, default=1))
    complete = is_valid_file(run.restart_path, minimum_size) and is_valid_file(run.da_state_path, minimum_size)
    if complete and not force:
        return run

    executable = installed_executable(config, "executables.mpas_atmosphere", "mpas_atmosphere")
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

    job = render_pbs_job(
        config,
        run_dir=run.run_dir,
        job_name=f"mpasf{request.lead_hours:03d}_{request.init_time.strftime('%Y%m%d%H')}",
        executable=executable,
        walltime=_forecast_walltime(config, request.lead_hours),
        context=context,
        queue=string(config, "pbs.queue_forecast", required=False, default=string(config, "pbs.queue")),
        script_name=f"qsub_forecast_{request.init_time.strftime('%Y%m%d%H')}_f{request.lead_hours:03d}.pbs",
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
    """Validate restart, da_state, and the MPAS log for one forecast."""
    run = load_forecast_run(config, layout, request)
    minimum_size = int(value(config, "validation.minimum_size_bytes", required=False, default=1))
    require_netcdf = bool(value(config, "validation.require_netcdf", required=False, default=False))
    validate_file(run.restart_path, minimum_size, require_netcdf=require_netcdf)
    validate_file(run.da_state_path, minimum_size, require_netcdf=require_netcdf)

    require_clean_log = bool(value(config, "validation.require_mpas_clean_log", required=False, default=False))
    log_path = run.run_dir / "log.atmosphere.0000.out"
    if require_clean_log:
        if not log_path.is_file():
            raise FileNotFoundError(f"MPAS forecast validation log does not exist: {log_path}")
        text = log_path.read_text(encoding="utf-8", errors="replace")
        for token in (
            "Critical error messages =            0",
            "Error messages =                     0",
        ):
            if token not in text:
                raise RuntimeError(
                    f"MPAS forecast did not finish cleanly; missing {token!r} in {log_path}"
                )

    report = run.manifest_path.with_name("forecast-validation.json")
    write_json(
        report,
        {
            "init_time": request.init_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "valid_time": request.valid_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "lead_hours": request.lead_hours,
            "restart_path": str(run.restart_path),
            "da_state_path": str(run.da_state_path),
            "log_path": str(log_path) if require_clean_log else None,
            "valid": True,
        },
    )
    return report
