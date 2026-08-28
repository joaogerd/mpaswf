"""Regression tests for repository-versioned reference case templates."""

from __future__ import annotations

from pathlib import Path

from mpaswf.config import load_config
from mpaswf.layout import Layout
from mpaswf.model import parse_time
from mpaswf.wps import wps_output_path


def test_jaci_x1_10242_uses_versioned_wps_template() -> None:
    """The reference config must not depend on an external template checkout."""
    repo = Path(__file__).resolve().parents[1]
    config = load_config(repo / "configs/jaci-x1.10242.yaml")
    layout = Layout.from_config(config)

    assert layout.templates_dir == (repo / "templates/x1.10242").resolve()
    assert (layout.templates_dir / "namelist.wps.in").is_file()


def test_x1_10242_wps_product_uses_cdct_gfs_prefix() -> None:
    """WPS product naming remains aligned with the CD-CT GFS prefix."""
    repo = Path(__file__).resolve().parents[1]
    config = load_config(repo / "configs/jaci-x1.10242.yaml")
    layout = Layout.from_config(config)
    init_time = parse_time("2026-06-20T00:00:00Z")

    output = wps_output_path(config, layout, init_time)

    assert output.name == "GFS:2026-06-20_00"
