from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

from mpaswf.config import load_config
from mpaswf.layout import Layout
from mpaswf.wps import prepare_wps


def _write_executable(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def _write_config(tmp_path: Path, wps_dir: Path) -> Path:
    templates = tmp_path / "templates"
    templates.mkdir()
    (templates / "namelist.wps.in").write_text(
        """&share
  start_date = '{init_date_yyyy_mm_dd_hh}:00:00',
  end_date = '{init_date_yyyy_mm_dd_hh}:00:00',
/
&ungrib
  out_format = 'WPS',
  prefix = 'FILE',
/
""",
        encoding="utf-8",
    )

    gfs_dir = tmp_path / "gfs"
    gfs_file = gfs_dir / "2026062200" / "gfs.t00z.pgrb2.0p25.f000"
    gfs_file.parent.mkdir(parents=True)
    gfs_file.write_bytes(b"GRIB-local-input")

    payload = {
        "paths": {
            "work_dir": str(tmp_path / "work"),
            "static_dir": str(tmp_path / "static"),
            "gfs_dir": str(gfs_dir),
            "cdct_templates_dir": str(templates),
        },
        "executables": {
            "wps_dir": str(wps_dir),
            "mpas_init": "/bin/true",
            "mpas_atmosphere": "/bin/true",
        },
        "campaign": {
            "start_valid_time": "2026-06-24T00:00:00Z",
            "end_valid_time": "2026-06-24T00:00:00Z",
            "interval_hours": 6,
            "leads_hours": [24, 48],
        },
        "gfs": {
            "file_template": "gfs.t{init_hour}z.pgrb2.0p25.f000",
            "url_template": None,
            "minimum_size_bytes": 1,
        },
        "wps": {
            "output_template": "FILE:{init_date_yyyy_mm_dd_hh}",
            "vtable": "{wps_root}/share/wps/Vtable",
            "namelist_target": "namelist.wps",
            "link_grib_command": ["./link_grib.csh", "{gfs_file}"],
            "ungrib_command": ["./ungrib.exe"],
        },
        "products": {
            "init_state_template": "x1.10242.init.{init_date_yyyy_mm_dd_hh_mm_ss}.nc",
            "restart_template": "restart.{valid_date_yyyy_mm_dd_hh_mm_ss}.nc",
            "da_state_template": "mpasout.{valid_date_yyyy_mm_dd_hh_mm_ss}.nc",
        },
        "templates": {
            "wps": "namelist.wps.in",
            "static_namelist": "static.nml",
            "static_streams": "static.streams",
            "init_namelist": "init.nml",
            "init_streams": "init.streams",
            "forecast_namelist": "forecast.nml",
            "forecast_streams": "forecast.streams",
        },
        "static": {
            "reference_time": "2010-10-23T00:00:00Z",
            "product_template": "x1.10242.static.nc",
            "links": [],
        },
        "execution": {"backend": "local"},
        "validation": {"require_netcdf": False, "minimum_size_bytes": 1},
    }

    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return config_path


@pytest.mark.parametrize("configure_bin_directly", [False, True])
def test_prepare_consumes_monan_jedi_wps_and_force_reuses_local_gfs(
    tmp_path: Path,
    configure_bin_directly: bool,
) -> None:
    runtime_root = tmp_path / "monan-jedi"
    runtime_bin = runtime_root / "bin"
    vtable = runtime_root / "share" / "wps" / "Vtable"
    vtable.parent.mkdir(parents=True)
    vtable.write_text("Vtable.GFS\n", encoding="utf-8")

    _write_executable(
        runtime_bin / "link_grib.csh",
        "#!/bin/sh\nset -eu\nln -sfn \"$1\" GRIBFILE.AAA\n",
    )
    _write_executable(
        runtime_bin / "ungrib.exe",
        """#!/bin/sh
set -eu
test -s GRIBFILE.AAA
test -s Vtable
test -s namelist.wps
printf 'run\n' >> .ungrib-runs
printf 'wps-data\n' > 'FILE:2026-06-22_00'
""",
    )

    configured_wps_dir = runtime_bin if configure_bin_directly else runtime_root
    config = load_config(_write_config(tmp_path, configured_wps_dir))
    layout = Layout.from_config(config)
    init_time = datetime(2026, 6, 22, tzinfo=timezone.utc)

    first = prepare_wps(config, layout, init_time)
    second = prepare_wps(config, layout, init_time, force=True)

    assert first == second
    assert second.read_bytes() == b"wps-data\n"
    assert (second.parent / ".ungrib-runs").read_text(encoding="utf-8").splitlines() == ["run", "run"]

    metadata = json.loads((second.parent / ".mpaswf" / "wps.json").read_text(encoding="utf-8"))
    assert metadata["state"] == "completed"
    assert metadata["wps_root"] == str(runtime_root.resolve())
    assert metadata["wps_bin_dir"] == str(runtime_bin.resolve())
    assert metadata["vtable"] == str(vtable.resolve())
    assert metadata["gfs_file"].endswith("gfs/2026062200/gfs.t00z.pgrb2.0p25.f000")
