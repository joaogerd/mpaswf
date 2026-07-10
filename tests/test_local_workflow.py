from __future__ import annotations

import os
from pathlib import Path

import yaml

from mpaswf.config import load_config
from mpaswf.workflow import run_forecast, run_init, run_manifest, run_prepare


def _script(path: Path, body: str) -> None:
    path.write_text("#!/usr/bin/env bash\nset -euo pipefail\n" + body + "\n", encoding="utf-8")
    path.chmod(path.stat().st_mode | 0o111)


def test_local_pipeline_creates_manifest(tmp_path: Path) -> None:
    """Exercise all four phases with small fake WPS and MPAS executables."""
    apps = tmp_path / "apps"
    wps = apps / "wps"
    (wps / "ungrib" / "Variable_Tables").mkdir(parents=True)
    (wps / "ungrib" / "Variable_Tables" / "Vtable.GFS").write_text("vtable\n", encoding="utf-8")
    _script(wps / "link_grib.csh", "exit 0")
    _script(
        wps / "ungrib.exe",
        "d=${PWD##*/}\ntouch \"FILE:${d:0:4}-${d:4:2}-${d:6:2}_${d:8:2}\"",
    )
    _script(
        apps / "mpas_init_atmosphere",
        "d=${PWD##*/}\nif [[ \"${d}\" == \"static\" ]]; then touch x1.static.nc; else touch \"init.${d}.nc\"; fi",
    )
    _script(apps / "mpas_atmosphere", "touch restart.nc mpasout.nc")

    templates = tmp_path / "templates"
    templates.mkdir()
    for name in (
        "namelist.wps.in",
        "namelist.init_atmosphere.static.in",
        "streams.init_atmosphere.static.in",
        "namelist.init_atmosphere.in",
        "streams.init_atmosphere.in",
        "namelist.atmosphere.in",
        "streams.atmosphere.in",
    ):
        (templates / name).write_text("# {init_time}\n", encoding="utf-8")

    gfs_root = tmp_path / "gfs"
    for cycle in ("2026062000", "2026062100"):
        directory = gfs_root / cycle
        directory.mkdir(parents=True)
        (directory / "gfs.t00z.pgrb2.0p25.f000").write_bytes(b"gfs")

    payload = {
        "paths": {
            "work_dir": str(tmp_path / "work"),
            "static_dir": str(tmp_path / "static"),
            "gfs_dir": str(gfs_root),
            "cdct_templates_dir": str(templates),
        },
        "executables": {
            "wps_dir": str(wps),
            "mpas_init": str(apps / "mpas_init_atmosphere"),
            "mpas_atmosphere": str(apps / "mpas_atmosphere"),
        },
        "campaign": {
            "start_valid_time": "2026-06-22T00:00:00Z",
            "end_valid_time": "2026-06-22T00:00:00Z",
            "interval_hours": 6,
            "leads_hours": [24, 48],
        },
        "gfs": {"file_template": "gfs.t{init_hour}z.pgrb2.0p25.f000", "url_template": None, "minimum_size_bytes": 1},
        "wps": {
            "output_template": "FILE:{init_date_yyyy_mm_dd_hh}",
            "vtable": "{wps_dir}/ungrib/Variable_Tables/Vtable.GFS",
            "namelist_target": "namelist.wps",
            "link_grib_command": ["./link_grib.csh", "{gfs_file}"],
            "ungrib_command": ["./ungrib.exe"],
        },
        "products": {
            "init_state_template": "init.{init_yyyymmddhh}.nc",
            "restart_template": "restart.nc",
            "da_state_template": "mpasout.nc",
        },
        "templates": {
            "wps": "namelist.wps.in",
            "static_namelist": "namelist.init_atmosphere.static.in",
            "static_streams": "streams.init_atmosphere.static.in",
            "init_namelist": "namelist.init_atmosphere.in",
            "init_streams": "streams.init_atmosphere.in",
            "forecast_namelist": "namelist.atmosphere.in",
            "forecast_streams": "streams.atmosphere.in",
        },
        "static": {
            "reference_time": "2010-10-23T00:00:00Z",
            "product_template": "x1.static.nc",
            "links": [],
        },
        "execution": {"backend": "local"},
        "validation": {"require_netcdf": False, "minimum_size_bytes": 0},
    }
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    config = load_config(config_path)

    run_prepare(config)
    run_init(config, submit=False, wait=False)
    run_forecast(config, submit=False, wait=False)
    manifest = run_manifest(config)

    assert manifest.is_file()
    assert len(manifest.read_text(encoding="utf-8").splitlines()) == 2
