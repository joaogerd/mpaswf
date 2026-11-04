"""Regression tests: the historic case is explicit and its templates are reusable."""

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from mpaswf.config import WorkflowConfig, load_config
from mpaswf.forecast import forecast_sources, stream_list_directory
from mpaswf.layout import Layout
from mpaswf.mesh import mesh_name, staging_preflight_enabled
from mpaswf.workflow import load_campaign


ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / "testcase/tutorial-240km"


def _case(monkeypatch) -> WorkflowConfig:
    monkeypatch.setenv("USER", "ci-user")
    return load_config(CASE / "jaci.yaml")


def test_tutorial_is_explicit_and_runnable_as_a_configuration(monkeypatch):
    config = _case(monkeypatch)
    assert mesh_name(config) == "x1.10242"
    assert config.data["mesh"]["nvertlevels"] == 55
    assert staging_preflight_enabled(config) is True
    assert "tutorial_physics_files" not in config.data["static"]
    assert config.data["runtime"]["config_dt"] == 60
    assert config.data["runtime"]["forecast_namelist"].endswith(
        "namelist.atmosphere_240km"
    )
    assert config.data["runtime"]["forecast_streams"].endswith(
        "streams.atmosphere_240km"
    )
    assert forecast_sources(config)[0].name == "namelist.atmosphere_240km"
    assert stream_list_directory(config).name == "MPAS_namelist_stream_physics_files"
    assert Layout.from_config(config).templates_dir == CASE / "templates"
    assert all(
        (CASE / "templates" / config.data["templates"][key]).is_file()
        for key in ("wps", "init_namelist", "init_streams")
    )
    pairs = load_campaign(config).pairs
    assert len(pairs) == 4
    assert pairs[0].valid_time == datetime(2026, 6, 22, tzinfo=timezone.utc)
    assert pairs[-1].valid_time == datetime(2026, 6, 25, tzinfo=timezone.utc)


def test_tutorial_templates_render_identically_for_original_mesh():
    replacements = {
        "init_date_yyyy_mm_dd_hh": "2026-06-20_00",
        "init_date_yyyy_mm_dd_hh_mm_ss": "2026-06-20_00.00.00",
        "nvertlevels": "55",
        "partition_prefix": "x1.10242.graph.info.part.",
        "static_filename": "x1.10242.static.nc",
        "init_filename": "x1.10242.init.2026-06-20_00.00.00.nc",
    }
    for filename in (
        "namelist.wps.in",
        "namelist.init_atmosphere.in",
        "streams.init_atmosphere.in",
    ):
        original = (ROOT / "templates/x1.10242" / filename).read_text()
        testcase = (CASE / "templates" / filename).read_text()
        assert testcase.format(**replacements) == original.format(**replacements)


def test_copying_case_can_change_mesh_and_period_without_code_changes(monkeypatch):
    source = _case(monkeypatch)
    data = deepcopy(source.data)
    data["mesh"] = {"name": "x1.163842", "nvertlevels": 70}
    data["static"]["product_template"] = "x1.163842.static.nc"
    data["campaign"]["start_valid_time"] = "2027-01-01T00:00:00Z"
    data["campaign"]["end_valid_time"] = "2027-01-02T00:00:00Z"
    data["campaign"]["interval_hours"] = 12
    data["runtime"]["config_dt"] = 150
    data["products"]["init_state_template"] = "x1.163842.init.{init_date_yyyy_mm_dd_hh_mm_ss}.nc"
    other = WorkflowConfig(CASE / "custom.yaml", data)
    assert mesh_name(other) == "x1.163842"
    assert len(load_campaign(other).pairs) == 3
    assert staging_preflight_enabled(other) is True
