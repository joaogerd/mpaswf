"""High-level implementation of the four public `mpaswf` phases."""

from __future__ import annotations

import csv
import hashlib
import json
import tempfile
from datetime import datetime, timezone
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
    """Two-lead same-valid-time MPAS campaign."""

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
    """Prepare, run, or submit both configured NMC forecast leads."""
    if wait and not submit:
        raise ValueError("--wait requires --submit.")
    layout = Layout.from_config(config)
    campaign = load_campaign(config)
    requests = unique_forecasts(campaign.pairs)
    status(f"Forecast phase: {len(requests)} forecasts with configured NMC lead times.")
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
    """Validate same-valid-time forecast pairs and write a versioned MPAS manifest.

    The existing f024/f048 TSV and sidecar remain v1 for the original case.
    Other forecast lead pairs are represented by an explicit v2 contract with
    generic older/newer names and lead durations in every row.
    """
    layout = Layout.from_config(config)
    campaign = load_campaign(config)
    if not campaign.pairs:
        raise ValueError("O período do experimento não gerou pares NMC.")
    ensure_directory(layout.products_dir)
    output = layout.products_dir / "mpas-forecast-manifest.tsv"
    older_lead, newer_lead = campaign.pairs[0].leads_hours
    legacy = (older_lead, newer_lead) == (48, 24)
    fields = (
        ["valid_time", "f048_state", "f024_state", "f048_restart", "f024_restart"]
        if legacy else [
            "valid_time", "older_lead_hours", "newer_lead_hours",
            "older_state", "newer_state", "older_restart", "newer_restart",
        ]
    )
    status(
        f"Manifest phase: validating {len(campaign.pairs)} NMC pairs "
        f"({older_lead}h minus {newer_lead}h)."
    )
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", newline="", encoding="utf-8", dir=layout.products_dir,
            prefix=".mpas-forecast-manifest-", suffix=".tsv", delete=False
        ) as handle:
            temporary = Path(handle.name)
            writer = csv.writer(handle, delimiter="\t")
            writer.writerow(fields)
            for pair in campaign.pairs:
                validate_forecast(config, layout, pair.older)
                validate_forecast(config, layout, pair.newer)
                older = load_forecast_run(config, layout, pair.older)
                newer = load_forecast_run(config, layout, pair.newer)
                timestamp = pair.valid_time.strftime("%Y-%m-%dT%H:%M:%SZ")
                if legacy:
                    writer.writerow([
                        timestamp, str(older.da_state_path), str(newer.da_state_path),
                        str(older.restart_path), str(newer.restart_path),
                    ])
                else:
                    writer.writerow([
                        timestamp, older_lead, newer_lead,
                        str(older.da_state_path), str(newer.da_state_path),
                        str(older.restart_path), str(newer.restart_path),
                    ])
        temporary.replace(output)
    except Exception:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    sidecar = output.with_suffix(".json")
    pair_semantics = (
        {
            "valid_time": "shared forecast valid time T",
            "f048_state": "MPAS da_state initialized at T-48h and valid at T",
            "f024_state": "MPAS da_state initialized at T-24h and valid at T",
            "f048_restart": "validated restart product from the f048 forecast",
            "f024_restart": "validated restart product from the f024 forecast",
        }
        if legacy else {
            "valid_time": "shared forecast valid time T",
            "older_lead_hours": "longer forecast duration in hours",
            "newer_lead_hours": "shorter forecast duration in hours",
            "older_state": "MPAS da_state at T from older initialization",
            "newer_state": "MPAS da_state at T from newer initialization",
            "older_restart": "restart output of older forecast",
            "newer_restart": "restart output of newer forecast",
        }
    )
    payload = {
        "schema_version": 1 if legacy else 2,
        "contract": "monan-nmc-forecast-pairs-v1" if legacy else "monan-nmc-forecast-pairs-v2",
        "producer": "mpaswf",
        "consumer": "MPAS-BMatrix",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "manifest": output.name,
        "manifest_format": "tsv",
        "manifest_sha256": digest,
        "columns": fields,
        "pair_count": len(campaign.pairs),
        "pair_semantics": pair_semantics,
    }
    if not legacy:
        payload["leads_hours"] = {"older": older_lead, "newer": newer_lead}
    sidecar.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _record_phase(layout, "manifest", {
        "manifest": str(output), "contract": str(sidecar),
        "pairs": len(campaign.pairs), "state": "completed",
    })
    status(f"Manifest phase: wrote {output} and contract {sidecar}.")
    return output
