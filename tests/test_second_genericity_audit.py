"""Second genericity audit: mesh naming, local/PBS decomposition, and reuse."""

import json
from pathlib import Path

import pytest

from mpaswf.config import ConfigurationError, WorkflowConfig
from mpaswf.mesh import (
    ensure_campaign_identity, mesh_graph_filename, mesh_grid_filename,
    mesh_context, mpi_ranks, partition_prefix,
)


def _case(tmp_path: Path) -> WorkflowConfig:
    return WorkflowConfig(tmp_path / "case.yaml", {
        "mesh": {"name": "regional.v3", "nvertlevels": 72},
        "static": {"source": "/data/region.invariant.nc", "product_template": "region.static.nc"},
        "runtime": {"config_dt": 135, "forecast_namelist": "/cases/nml",
                    "forecast_streams": "/cases/streams"},
        "gfs": {"file_template": "gfs.t{init_hour}z.f000"},
        "wps": {"output_template": "GFS:{init_date_yyyy_mm_dd_hh}"},
        "templates": {"init_namelist": "namelist.in"},
        "products": {"init_state_template": "region.init.{init_date_yyyy_mm_dd_hh_mm_ss}.nc"},
        "execution": {"backend": "pbs"},
        "pbs": {"select": 2, "mpiprocs": 32},
        "campaign": {"start_valid_time": "2027-01-01T00:00:00Z",
                     "end_valid_time": "2027-01-02T00:00:00Z",
                     "leads_hours": [24, 48]},
        "validation": {"require_staging_preflight": True},
    })


def test_custom_mesh_filenames_match_selected_asset_targets(tmp_path: Path):
    case = _case(tmp_path)
    case.data["mesh"].update({
        "grid_filename": "regional-grid.nc",
        "graph_filename": "regional-connectivity.info",
    })
    assert mesh_grid_filename(case) == "regional-grid.nc"
    assert mesh_graph_filename(case) == "regional-connectivity.info"
    assert partition_prefix(case) == "regional-connectivity.info.part."
    context = mesh_context(case)
    assert context["grid_filename"] == "regional-grid.nc"
    assert context["partition_prefix"] == "regional-connectivity.info.part."
    assert mpi_ranks(case) == 64
    case.data["mesh"]["partition_prefix"] = "region.custom.part."
    assert partition_prefix(case) == "region.custom.part."


def test_mesh_asset_filenames_reject_relative_paths(tmp_path: Path):
    case = _case(tmp_path)
    case.data["mesh"]["graph_filename"] = "../another-case/graph.info"
    with pytest.raises(ConfigurationError, match="mesh.graph_filename"):
        mesh_graph_filename(case)


def test_local_mode_has_explicit_serial_rank_policy(tmp_path: Path):
    case = _case(tmp_path)
    case.data["execution"]["backend"] = "local"
    case.data.pop("pbs")
    assert mpi_ranks(case) == 1
    case.data["execution"]["mpi_ranks"] = 8
    with pytest.raises(ConfigurationError, match="local backend"):
        mpi_ranks(case)


def test_campaign_ignores_period_extension_but_rejects_science_changes(tmp_path: Path):
    case = _case(tmp_path)
    work = tmp_path / "work"
    ensure_campaign_identity(case, work)
    identity = json.loads((work / ".mpaswf/mesh.json").read_text())
    assert len(identity["scientific_sha256"]) == 64

    case.data["campaign"]["end_valid_time"] = "2027-01-05T00:00:00Z"
    ensure_campaign_identity(case, work)  # extending an identical run is safe

    case.data["runtime"]["config_dt"] = 120
    with pytest.raises(ConfigurationError, match="scientific configuration"):
        ensure_campaign_identity(case, work)


def test_old_mesh_only_marker_uses_safe_compatibility_warning(tmp_path: Path):
    case = _case(tmp_path)
    work = tmp_path / "work"
    marker = work / ".mpaswf/mesh.json"
    marker.parent.mkdir(parents=True)
    marker.write_text(json.dumps({"mesh": "regional.v3", "nvertlevels": 72}))
    (work / "forecast" / "run").mkdir(parents=True)
    (work / "forecast" / "run" / "old.nc").write_text("old")
    with pytest.warns(FutureWarning, match="older mesh-only"):
        ensure_campaign_identity(case, work)
