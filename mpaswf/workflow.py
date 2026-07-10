"""High-level implementation of the four public `mpaswf` phases."""

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
    """Resolved fixed-shape f024/f048 MPAS campaign."""

    pairs: tuple[ProductPair, ...]


def load_campaign(config: WorkflowConfig) -> Campaign:
    """Build the campaign from the small `campaign` configuration section."""
    start = parse_time(str(value(config, "campaign.start_valid_time")))
    end = parse_time(str(value(config, "campaign.end_valid_time")))
    interval = int(value(config, "campaign.interval_hours"))
    leads = value(config, "campaign.leads_hours")
    if not isinstance(leads, list):
        raise ValueError("campaign.leads_hours must be a list.")
    return Campaign(tuple(build_pairs(start, end, interval, leads)))


def _record_phase(layout: Layout, phase: str, payload: dict[str, object]) -> Path:
    """Persist a simple phase-level status file."""
    return write_json(layout.metadata_dir / f"{phase}.json", {"phase": phase, **payload})


def run_prepare(config: WorkflowConfig, *, force: bool = False) -> Path:
    """Ensure GFS inputs and WPS `FILE:` products for all initialization times."""
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
    """Generate/reuse the static product, then prepare or run dynamic initializations.

    The static interpolation is a strict dependency. For a PBS backend with no
    ``--wait``, the first call renders or submits only the static job when the
    product is absent. Re-run the same command after validation to advance to
    the date-dependent initialization layer.
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
    """Prepare, run, or submit every required f024/f048 MPAS forecast."""
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
    """Validate all f024/f048 products and write a neutral MPAS TSV manifest."""
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
