"""Implement the four public MPASWF workflow phases.

This module coordinates lower-level GFS, WPS, static interpolation,
initialization, forecast, validation, and manifest helpers. It records concise
phase-level JSON state without embedding scientific model configuration.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from .config import WorkflowConfig, value
from .files import ensure_directory, write_json
from .forecast import execute_forecast, load_forecast_run, validate_forecast
from .init import execute_init, validate_init
from .static import execute_static, load_static_run, validate_static
from .layout import Layout
from .model import ProductPair, build_pairs, parse_time, unique_forecasts, unique_initialization_times
from .wps import prepare_wps
from .ui import status


@dataclass(frozen=True)
class Campaign:
    """Store the resolved fixed-shape f024/f048 MPAS campaign.

    Parameters
    ----------
    pairs : tuple of ProductPair
        Ordered product pairs generated for every configured valid time.
    """

    pairs: tuple[ProductPair, ...]


def load_campaign(config: WorkflowConfig) -> Campaign:
    """Build a campaign from the ``campaign`` configuration section.

    Parameters
    ----------
    config : WorkflowConfig
        Loaded workflow configuration.

    Returns
    -------
    Campaign
        Immutable tuple of f024/f048 product pairs.

    Raises
    ------
    ValueError
        Raised when campaign timestamps, spacing, or lead times are invalid, or
        when ``campaign.leads_hours`` is not a list.
    ConfigurationError
        Propagated when a required campaign value is absent.
    """
    start = parse_time(str(value(config, "campaign.start_valid_time")))
    end = parse_time(str(value(config, "campaign.end_valid_time")))
    interval = int(value(config, "campaign.interval_hours"))
    leads = value(config, "campaign.leads_hours")
    if not isinstance(leads, list):
        raise ValueError("campaign.leads_hours must be a list.")
    return Campaign(tuple(build_pairs(start, end, interval, leads)))


def _record_phase(layout: Layout, phase: str, payload: dict[str, object]) -> Path:
    """Persist a phase-level JSON status record.

    Parameters
    ----------
    layout : Layout
        Resolved campaign directory layout.
    phase : str
        Phase name used as both the filename stem and the ``phase`` field.
    payload : dict[str, object]
        Additional JSON-serializable state fields.

    Returns
    -------
    pathlib.Path
        Path to ``<metadata_dir>/<phase>.json``.

    Raises
    ------
    TypeError
        Propagated when ``payload`` is not JSON serializable.
    OSError
        Propagated when the metadata file cannot be written.
    """
    return write_json(layout.metadata_dir / f"{phase}.json", {"phase": phase, **payload})


def run_prepare(config: WorkflowConfig, *, force: bool = False) -> Path:
    """Ensure GFS inputs and WPS products for all initialization times.

    Parameters
    ----------
    config : WorkflowConfig
        Loaded workflow configuration.
    force : bool, default=False
        Redownload GFS inputs and rerun WPS even when reusable products exist.

    Returns
    -------
    pathlib.Path
        Phase-level ``prepare.json`` record.

    Raises
    ------
    FileNotFoundError
        Propagated when a required local input, executable, Vtable, or template
        is absent and cannot be acquired.
    RuntimeError
        Propagated when a download, external command, or product validation
        fails.
    ValueError
        Propagated when campaign or command configuration is malformed.

    Notes
    -----
    Initialization times are deduplicated across all f024/f048 pairs before WPS
    processing, so each required time is prepared exactly once per invocation.
    """
    layout = Layout.from_config(config)
    campaign = load_campaign(config)
    initialization_times = unique_initialization_times(campaign.pairs)
    status(f"Prepare phase: {len(initialization_times)} initialization times; GFS and WPS products.")
    products = []
    for index, init_time in enumerate(initialization_times, start=1):
        status(
            f"Prepare [{index}/{len(initialization_times)}]: {init_time.strftime('%Y-%m-%d %HZ')}."
        )
        products.append(str(prepare_wps(config, layout, init_time, force=force)))
    record = _record_phase(layout, "prepare", {"wps_products": products, "count": len(products), "state": "completed"})
    status(f"Prepare phase: completed {len(products)} WPS products.")
    return record


def run_init(config: WorkflowConfig, *, submit: bool, wait: bool, force: bool = False) -> Path:
    """Generate or reuse static data, then process dynamic initializations.

    Parameters
    ----------
    config : WorkflowConfig
        Loaded workflow configuration.
    submit : bool
        Submit rendered PBS jobs when the configured backend is PBS.
    wait : bool
        Wait for submitted jobs and validate their products.
    force : bool, default=False
        Ignore reusable static and initialized-state products.

    Returns
    -------
    pathlib.Path
        Phase-level ``init.json`` record.

    Raises
    ------
    ValueError
        Raised when ``wait`` is true while ``submit`` is false, or propagated
        from malformed campaign or PBS configuration.
    FileNotFoundError
        Propagated when required executables, inputs, templates, or assets are
        missing.
    RuntimeError
        Propagated when execution, submission, or validation fails outside the
        expected static dependency boundary.

    Notes
    -----
    Static interpolation is a strict dependency. For a PBS backend without
    waiting, the first call renders or submits only the static job when its
    product is absent. Re-running the same command after static validation
    advances to the date-dependent initialization layer.
    """
    if wait and not submit:
        raise ValueError("--wait requires --submit.")
    layout = Layout.from_config(config)
    campaign = load_campaign(config)

    status("Init phase: checking the one-time MPAS static interpolation product.")
    static_run = execute_static(config, layout, submit=submit, wait=wait, force=force)
    try:
        validate_static(config, layout)
    except (FileNotFoundError, RuntimeError):
        state = "submitted-static" if submit else "rendered-static"
        return _record_phase(
            layout,
            "init",
            {
                "static_run_dir": str(static_run.run_dir),
                "static_path": str(static_run.state_path),
                "items": [],
                "count": 0,
                "state": state,
            },
        )

    initialization_times = unique_initialization_times(campaign.pairs)
    status(f"Init phase: static product is valid; processing {len(initialization_times)} dynamic initializations.")
    items: list[dict[str, object]] = []
    for index, init_time in enumerate(initialization_times, start=1):
        status(
            f"Init [{index}/{len(initialization_times)}]: {init_time.strftime('%Y-%m-%d %HZ')}."
        )
        run = execute_init(config, layout, init_time, submit=submit, wait=wait, force=force)
        items.append(
            {
                "init_time": init_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "run_dir": str(run.run_dir),
                "state_path": str(run.state_path),
            }
        )
    state = "submitted-or-completed" if submit else "rendered-or-completed"
    record = _record_phase(
        layout,
        "init",
        {
            "static_run_dir": str(static_run.run_dir),
            "static_path": str(static_run.state_path),
            "items": items,
            "count": len(items),
            "state": state,
        },
    )
    status(f"Init phase: recorded {len(items)} dynamic initialization jobs.")
    return record


def run_forecast(config: WorkflowConfig, *, submit: bool, wait: bool, force: bool = False) -> Path:
    """Prepare, execute, or submit every required f024/f048 forecast.

    Parameters
    ----------
    config : WorkflowConfig
        Loaded workflow configuration.
    submit : bool
        Submit rendered PBS jobs when the configured backend is PBS.
    wait : bool
        Wait for submitted jobs and validate forecast products.
    force : bool, default=False
        Ignore reusable forecast products.

    Returns
    -------
    pathlib.Path
        Phase-level ``forecast.json`` record.

    Raises
    ------
    ValueError
        Raised when ``wait`` is true while ``submit`` is false, or propagated
        from malformed campaign or PBS configuration.
    FileNotFoundError
        Propagated when required initial states, executables, templates, or
        assets are missing.
    RuntimeError
        Propagated when execution, submission, or validation fails.

    Notes
    -----
    Forecast requests are deduplicated by initialization time and lead time
    before processing.
    """
    if wait and not submit:
        raise ValueError("--wait requires --submit.")
    layout = Layout.from_config(config)
    campaign = load_campaign(config)
    requests = unique_forecasts(campaign.pairs)
    status(f"Forecast phase: {len(requests)} f024/f048 MPAS forecasts.")
    items: list[dict[str, object]] = []
    for index, request in enumerate(requests, start=1):
        status(
            f"Forecast [{index}/{len(requests)}]: init {request.init_time.strftime('%Y-%m-%d %HZ')}, "
            f"f{request.lead_hours:03d}."
        )
        run = execute_forecast(config, layout, request, submit=submit, wait=wait, force=force)
        items.append(
            {
                "init_time": request.init_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "valid_time": request.valid_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "lead_hours": request.lead_hours,
                "run_dir": str(run.run_dir),
                "restart_path": str(run.restart_path),
                "da_state_path": str(run.da_state_path),
            }
        )
    state = "submitted-or-completed" if submit else "rendered-or-completed"
    record = _record_phase(layout, "forecast", {"items": items, "count": len(items), "state": state})
    status(f"Forecast phase: recorded {len(items)} forecasts.")
    return record


def run_manifest(config: WorkflowConfig) -> Path:
    """Validate all forecast pairs and write a neutral TSV manifest.

    Parameters
    ----------
    config : WorkflowConfig
        Loaded workflow configuration.

    Returns
    -------
    pathlib.Path
        Path to ``mpas-forecast-manifest.tsv`` in the products directory.

    Raises
    ------
    FileNotFoundError
        Raised when any required restart or ``da_state`` product is absent or
        too small.
    RuntimeError
        Raised when requested NetCDF validation cannot be performed or fails.
    ValueError
        Propagated when campaign configuration is invalid.
    OSError
        Propagated when the products directory, TSV file, validation reports, or
        phase record cannot be written.

    Notes
    -----
    Each row contains one valid time and the f048/f024 ``da_state`` and restart
    paths. Forecast products are validated before their paths are written.
    """
    layout = Layout.from_config(config)
    campaign = load_campaign(config)
    ensure_directory(layout.products_dir)
    output = layout.products_dir / "mpas-forecast-manifest.tsv"
    status(f"Manifest phase: validating {len(campaign.pairs)} f024/f048 pairs.")
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, delimiter="\t")
        writer.writerow(["valid_time", "f048_state", "f024_state", "f048_restart", "f024_restart"])
        for pair in campaign.pairs:
            validate_forecast(config, layout, pair.f024)
            validate_forecast(config, layout, pair.f048)
            f024 = load_forecast_run(config, layout, pair.f024)
            f048 = load_forecast_run(config, layout, pair.f048)
            writer.writerow(
                [
                    pair.valid_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    str(f048.da_state_path),
                    str(f024.da_state_path),
                    str(f048.restart_path),
                    str(f024.restart_path),
                ]
            )
    _record_phase(layout, "manifest", {"manifest": str(output), "pairs": len(campaign.pairs), "state": "completed"})
    status(f"Manifest phase: wrote {output}.")
    return output
