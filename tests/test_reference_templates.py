"""Regression tests for repository-versioned reference case templates."""

from __future__ import annotations

from pathlib import Path

from mpaswf.config import load_config
from mpaswf.files import render_template
from mpaswf.layout import Layout
from mpaswf.model import parse_time
from mpaswf.wps import wps_output_path


def _reference():
    repo = Path(__file__).resolve().parents[1]
    config = load_config(repo / "configs/jaci-x1.10242.yaml")
    return repo, config, Layout.from_config(config)


def test_jaci_x1_10242_uses_versioned_templates() -> None:
    """The reference config must not depend on an external template checkout."""
    repo, _, layout = _reference()

    assert layout.templates_dir == (repo / "templates/x1.10242").resolve()
    for name in (
        "namelist.wps.in",
        "namelist.init_atmosphere.in",
        "streams.init_atmosphere.in",
    ):
        assert (layout.templates_dir / name).is_file()


def test_x1_10242_wps_product_uses_cdct_gfs_prefix() -> None:
    """WPS product naming remains aligned with the CD-CT GFS prefix."""
    _, config, layout = _reference()
    init_time = parse_time("2026-06-20T00:00:00Z")

    output = wps_output_path(config, layout, init_time)

    assert output.name == "GFS:2026-06-20_00"


def test_x1_10242_init_templates_render_invariant_contract(tmp_path: Path) -> None:
    """Rendered init files preserve the validated invariant/GFS setup."""
    _, config, layout = _reference()
    init_time = parse_time("2026-06-20T00:00:00Z")
    context = layout.context(init_time, init_time, 0, tmp_path)

    namelist = tmp_path / "namelist.init_atmosphere"
    streams = tmp_path / "streams.init_atmosphere"
    render_template(layout.templates_dir / "namelist.init_atmosphere.in", namelist, context)
    render_template(layout.templates_dir / "streams.init_atmosphere.in", streams, context)

    nml = namelist.read_text(encoding="utf-8")
    xml = streams.read_text(encoding="utf-8")
    for token in (
        "config_start_time = '2026-06-20_00:00:00'",
        "config_nvertlevels = 55",
        "config_met_prefix = 'GFS'",
        "config_static_interp = .false.",
        "config_met_interp = .true.",
        "config_block_decomp_file_prefix = 'x1.10242.graph.info.part.'",
    ):
        assert token in nml

    assert "x1.10242.static.nc" in xml
    assert "x1.10242.init.2026-06-20_00.00.00.nc" in xml
    assert 'clobber_mode="overwrite"' in xml
