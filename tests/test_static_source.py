"""Tests for precomputed static/invariant staging."""

from __future__ import annotations

from pathlib import Path

from mpaswf.config import WorkflowConfig
from mpaswf.layout import Layout
from mpaswf.static import prepare_static


def test_prepare_static_links_configured_invariant(tmp_path: Path) -> None:
    source = tmp_path / "x1.10242.invariant.nc"
    source.write_bytes(b"invariant")
    run_dir = tmp_path / "static"
    config = WorkflowConfig(
        path=tmp_path / "config.yaml",
        data={
            "static": {
                "reference_time": "2010-10-23T00:00:00Z",
                "product_template": "x1.10242.static.nc",
                "source": str(source),
            },
            "validation": {"minimum_size_bytes": 1},
        },
    )
    layout = Layout(
        work_dir=tmp_path / "work",
        static_dir=run_dir,
        gfs_dir=tmp_path / "gfs",
        templates_dir=tmp_path / "templates",
    )

    run = prepare_static(config, layout)

    assert run.state_path.is_symlink()
    assert run.state_path.resolve() == source.resolve()
    assert (run_dir / ".mpaswf/static.json").is_file()
