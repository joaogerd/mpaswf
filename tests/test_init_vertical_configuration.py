"""Synthetic initializations ensure vertical subgrid choices are not tutorial defaults."""
from datetime import datetime, timezone
from pathlib import Path

import pytest

from mpaswf.config import ConfigurationError, WorkflowConfig
from mpaswf.files import render_template
from mpaswf.layout import Layout
from mpaswf.mesh import initialization_context
from mpaswf.preflight import _renderable_template


TEMPLATE = Path(__file__).resolve().parents[1] / "templates/invariant/namelist.init_atmosphere.in"


def _case(tmp_path, model_levels, soil_levels, forcing_levels, aerosol_levels):
    return WorkflowConfig(tmp_path / "config.yaml", {
        "mesh": {"name": "custom.mesh", "nvertlevels": model_levels},
        "initialization": {"levels": {
            "nsoillevels": soil_levels,
            "nfglevels": forcing_levels,
            "nfgsoillevels": soil_levels,
            "gocartlevels": aerosol_levels,
        }},
        "static": {"reference_time": "2027-01-01T00:00:00Z",
                   "product_template": "custom.static.nc"},
    })


@pytest.mark.parametrize("model,soil,forcing,aerosol", [
    (12, 2, 18, 0), (72, 4, 52, 20), (137, 6, 91, 30),
])
def test_generic_init_template_uses_selected_case_dimensions(
    tmp_path, model, soil, forcing, aerosol
):
    config = _case(tmp_path, model, soil, forcing, aerosol)
    layout = Layout(tmp_path, tmp_path / "static", tmp_path / "gfs", TEMPLATE.parent)
    time = datetime(2027, 1, 1, tzinfo=timezone.utc)
    context = layout.context(time, time, 0, tmp_path)
    context.update(initialization_context(config))
    output = tmp_path / "rendered.nml"
    render_template(TEMPLATE, output, context)
    rendered = output.read_text()
    assert f"config_nvertlevels = {model}" in rendered
    assert f"config_nsoillevels = {soil}" in rendered
    assert f"config_nfglevels = {forcing}" in rendered
    assert f"config_nfgsoillevels = {soil}" in rendered
    assert f"config_gocartlevels = {aerosol}" in rendered


def test_preflight_reports_exact_missing_scientific_level_choices(tmp_path):
    config = _case(tmp_path, 60, 4, 50, 15)
    config.data["initialization"]["levels"].pop("nfglevels")
    layout = Layout(tmp_path, tmp_path / "static", tmp_path / "gfs", TEMPLATE.parent)
    check = _renderable_template(config, layout, "templates.init_namelist", TEMPLATE)
    assert check.status == "INVALID"
    assert "initialization.levels.nfglevels" in check.detail


def test_initialization_does_not_assume_vertical_levels_from_horizontal_mesh(tmp_path):
    config = _case(tmp_path, 50, 4, 20, 0)
    config.data["initialization"]["levels"]["nfglevels"] = -1
    with pytest.raises(ConfigurationError, match="initialization.levels.nfglevels"):
        initialization_context(config)
