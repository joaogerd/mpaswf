"""Versioned NMC producer contract works across forecast lead pairs."""
import csv
import hashlib
import json
from pathlib import Path

import pytest

from mpaswf.config import WorkflowConfig
from mpaswf.forecast import _validated_output_interval, load_forecast_run
from mpaswf.layout import Layout
from mpaswf.model import build_pairs, parse_time, unique_forecasts, unique_initialization_times
from mpaswf.workflow import load_campaign, run_manifest


@pytest.mark.parametrize("leads", [
    [12, 36], [6, 18], [48, 72], [1, 3],
])
def test_arbitrary_two_leads_have_correct_same_valid_time(leads):
    valid = parse_time("2027-01-01T18:00:00Z")
    pairs = build_pairs(valid, valid, 6, leads)
    pair = pairs[0]
    assert pair.older.lead_hours == max(leads)
    assert pair.newer.lead_hours == min(leads)
    assert pair.older.valid_time == pair.newer.valid_time == valid
    assert pair.older.init_time < pair.newer.init_time
    assert len(unique_initialization_times(pairs)) == 2
    assert len(unique_forecasts(pairs)) == 2
    if sorted(leads) != [24, 48]:
        with pytest.raises(AttributeError, match="no f024"):
            _ = pair.f024


@pytest.mark.parametrize("leads", [[12, 12], [0, 36], [24], [24, 36, 48], [-6, 12], [True, 12]])
def test_invalid_lead_pairs_are_rejected(leads):
    t = parse_time("2027-01-01T00:00:00Z")
    with pytest.raises(ValueError, match="exactly two distinct"):
        build_pairs(t, t, 12, leads)


def test_forecast_output_interval_must_reach_selected_lead():
    config = WorkflowConfig(Path("/case/one.yaml"), {
        "runtime": {"output_interval": "12:00:00"},
    })
    assert _validated_output_interval(config, 36) == "12:00:00"
    config.data["runtime"]["output_interval"] = "24:00:00"
    with pytest.raises(ValueError, match="horário final"):
        _validated_output_interval(config, 36)


def test_variable_lead_manifest_v2_maintains_producer_integrity(tmp_path):
    config = WorkflowConfig(tmp_path / "case.yaml", {
        "paths": {
            "work_dir": str(tmp_path / "work"),
            "static_dir": str(tmp_path / "static"),
            "gfs_dir": str(tmp_path / "gfs"),
            "cdct_templates_dir": str(tmp_path / "templates"),
        },
        "campaign": {
            "start_valid_time": "2027-01-01T00:00:00Z",
            "end_valid_time": "2027-01-02T00:00:00Z",
            "interval_hours": 12,
            "leads_hours": [12, 36],
        },
        "products": {
            "restart_template": "restart.{valid_date_yyyy_mm_dd_hh_mm_ss}.nc",
            "da_state_template": "mpasout.{valid_date_yyyy_mm_dd_hh_mm_ss}.nc",
        },
        "validation": {"minimum_size_bytes": 1, "require_netcdf": False},
    })
    layout = Layout.from_config(config)
    for pair in load_campaign(config).pairs:
        for request in (pair.older, pair.newer):
            run = load_forecast_run(config, layout, request)
            run.run_dir.mkdir(parents=True, exist_ok=True)
            run.da_state_path.write_bytes(b"state")
            run.restart_path.write_bytes(b"restart")
    manifest = run_manifest(config)
    data = json.loads(manifest.with_suffix(".json").read_text())
    with manifest.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        rows = list(reader)
    assert data["schema_version"] == 2
    assert data["contract"] == "monan-nmc-forecast-pairs-v2"
    assert data["leads_hours"] == {"older": 36, "newer": 12}
    assert data["manifest_sha256"] == hashlib.sha256(manifest.read_bytes()).hexdigest()
    assert all(row["older_lead_hours"] == "36" and row["newer_lead_hours"] == "12" for row in rows)
    assert rows[0]["older_state"].endswith("/2026123012/f036/mpasout.2027-01-01_00.00.00.nc")
    assert rows[0]["newer_state"].endswith("/2026123112/f012/mpasout.2027-01-01_00.00.00.nc")
    assert len(rows) == 3
    original = manifest.read_bytes()
    missing = load_forecast_run(
        config, layout, load_campaign(config).pairs[-1].newer
    ).da_state_path
    missing.unlink()
    with pytest.raises((FileNotFoundError, RuntimeError)):
        run_manifest(config)
    assert manifest.read_bytes() == original  # failure never truncates old output
