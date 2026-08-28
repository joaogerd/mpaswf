"""Tests for deterministic GFS product and archive URL resolution."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from mpaswf.config import WorkflowConfig
from mpaswf.gfs import resolve_gfs_product
from mpaswf.layout import Layout


def test_resolve_gfs_product_builds_noaa_aws_archive_url(tmp_path: Path) -> None:
    """The configured archive URL matches the expected GFS date/cycle layout."""
    config = WorkflowConfig(
        path=tmp_path / "config.yaml",
        data={
            "gfs": {
                "file_template": "gfs.t{init_hour}z.pgrb2.0p25.f000",
                "url_template": (
                    "https://noaa-gfs-bdp-pds.s3.amazonaws.com/"
                    "gfs.{init_yyyymmdd}/{init_hour}/atmos/{gfs_file}"
                ),
            }
        },
    )
    layout = Layout(
        work_dir=tmp_path / "work",
        static_dir=tmp_path / "static",
        gfs_dir=tmp_path / "gfs",
        templates_dir=tmp_path / "templates",
    )
    init_time = datetime(2026, 6, 20, 0, tzinfo=timezone.utc)

    product = resolve_gfs_product(config, layout, init_time)

    assert product.path == tmp_path / "gfs/2026062000/gfs.t00z.pgrb2.0p25.f000"
    assert product.url == (
        "https://noaa-gfs-bdp-pds.s3.amazonaws.com/"
        "gfs.20260620/00/atmos/gfs.t00z.pgrb2.0p25.f000"
    )
