from pathlib import Path
import csv
import hashlib
import json

from mpaswf.config import WorkflowConfig, load_config
from mpaswf.forecast import load_forecast_run
from mpaswf.layout import Layout
from mpaswf.workflow import load_campaign, run_manifest


def test_example_configuration_loads() -> None:
    root = Path(__file__).resolve().parents[1]
    config = load_config(root / "examples" / "config.yaml")
    campaign = load_campaign(config)
    assert len(campaign.pairs) == 16


def test_manifest_contract_identity_is_documented_in_workflow_source() -> None:
    # Lightweight regression: the public producer contract must remain explicit
    # even when forecast execution itself is exercised in integration tests.
    root = Path(__file__).resolve().parents[1]
    source = (root / "mpaswf" / "workflow.py").read_text(encoding="utf-8")
    assert '"contract": "monan-nmc-forecast-pairs-v1"' in source
    assert '"producer": "mpaswf"' in source
    assert '"consumer": "MPAS-BMatrix"' in source
    assert '"manifest_sha256": digest' in source


def test_generated_manifest_sidecar_is_valid_json_bound_to_actual_products(tmp_path):
    config = WorkflowConfig(tmp_path / "config.yaml", {
        "paths": {"work_dir": str(tmp_path / "work"), "static_dir": str(tmp_path / "static"),
                  "gfs_dir": str(tmp_path / "gfs"), "cdct_templates_dir": str(tmp_path / "templates")},
        "campaign": {"start_valid_time": "2026-06-22T00:00:00Z",
                     "end_valid_time": "2026-06-25T00:00:00Z", "interval_hours": 24,
                     "leads_hours": [24, 48]},
        "products": {"restart_template": "restart.{valid_date_yyyy_mm_dd_hh_mm_ss}.nc",
                     "da_state_template": "mpasout.{valid_date_yyyy_mm_dd_hh_mm_ss}.nc"},
        "validation": {"minimum_size_bytes": 1, "require_netcdf": False},
    })
    layout = Layout.from_config(config)
    for pair in load_campaign(config).pairs:
        for request in (pair.f048, pair.f024):
            run = load_forecast_run(config, layout, request)
            run.run_dir.mkdir(parents=True, exist_ok=True)
            run.da_state_path.write_bytes(b"state")
            run.restart_path.write_bytes(b"restart")

    manifest = run_manifest(config)
    sidecar_text = manifest.with_suffix(".json").read_text(encoding="utf-8")
    payload = json.loads(sidecar_text)
    with manifest.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        rows = list(reader)
        assert payload["columns"] == reader.fieldnames
    assert payload["contract"] == "monan-nmc-forecast-pairs-v1"
    assert payload["pair_count"] == len(rows) == 4
    assert payload["manifest_sha256"] == hashlib.sha256(manifest.read_bytes()).hexdigest()
    assert sidecar_text.endswith("\n")
    assert rows[0]["f048_state"].endswith("2026062000/f048/mpasout.2026-06-22_00.00.00.nc")
