"""Tests for deterministic GFS product and archive URL resolution."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from mpaswf.config import WorkflowConfig
from mpaswf.gfs import ensure_gfs, resolve_gfs_product
import pytest
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

def test_external_missing_gfs_explains_automatic_download(tmp_path: Path) -> None:
    config = WorkflowConfig(path=tmp_path / "config.yaml", data={"gfs": {
        "acquisition": "external",
        "file_template": "gfs.t{init_hour}z.pgrb2.0p25.f000",
        "url_template": "https://example.org/never-download",
    }})
    layout = Layout(tmp_path / "work", tmp_path / "static", tmp_path / "gfs", tmp_path / "templates")
    with pytest.raises(FileNotFoundError) as error:
        ensure_gfs(config, layout, datetime(2026, 6, 20, tzinfo=timezone.utc))
    assert "gfs.acquisition: automatic" in str(error.value)
    assert "write access" in str(error.value)
    assert not layout.gfs_dir.exists()


def test_external_mode_reuses_read_only_gfs(tmp_path: Path) -> None:
    config = WorkflowConfig(path=tmp_path / "config.yaml", data={"gfs": {
        "acquisition": "external", "file_template": "gfs.t{init_hour}z.pgrb2.0p25.f000"
    }})
    layout = Layout(tmp_path / "work", tmp_path / "static", tmp_path / "gfs", tmp_path / "templates")
    init_time = datetime(2026, 6, 20, tzinfo=timezone.utc)
    product = resolve_gfs_product(config, layout, init_time)
    product.path.parent.mkdir(parents=True)
    product.path.write_bytes(b"valid GFS fixture")
    product.path.parent.chmod(0o555)
    assert ensure_gfs(config, layout, init_time).path == product.path
