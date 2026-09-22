from __future__ import annotations

from pathlib import Path

from mpaswf.config import WorkflowConfig
from mpaswf.preflight import config_preflight_report


def _touch(path: Path, *, executable: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("test\n", encoding="utf-8")
    if executable:
        path.chmod(0o755)


def _config(tmp_path: Path) -> WorkflowConfig:
    install = tmp_path / "monan-jedi"
    for name in (
        "mpas_init_atmosphere",
        "mpas_atmosphere",
        "ungrib.exe",
        "link_grib.csh",
    ):
        _touch(install / "bin" / name, executable=True)
    _touch(install / "share" / "wps" / "Variable_Tables" / "Vtable.GFS")
    (install / "share" / "MPAS" / "core_atmosphere").mkdir(parents=True)

    templates = tmp_path / "templates"
    template_names = {
        "wps": "namelist.wps.in",
        "static_namelist": "namelist.init_atmosphere.static.in",
        "static_streams": "streams.init_atmosphere.static.in",
        "init_namelist": "namelist.init_atmosphere.in",
        "init_streams": "streams.init_atmosphere.in",
        "forecast_namelist": "namelist.atmosphere.in",
        "forecast_streams": "streams.atmosphere.in",
    }
    for name in template_names.values():
        _touch(templates / name)

    invariant = tmp_path / "inputs" / "x1.10242.invariant.nc"
    mesh = tmp_path / "inputs" / "x1.10242.grid.nc"
    graph = tmp_path / "inputs" / "x1.10242.graph.info"
    partition = tmp_path / "inputs" / "x1.10242.graph.info.part.128"
    tutorial = tmp_path / "inputs" / "tutorial"
    for path in (invariant, mesh, graph, partition):
        _touch(path)
    tutorial.mkdir(parents=True)

    return WorkflowConfig(
        path=tmp_path / "configs" / "jaci.yaml",
        data={
            "software": {"monan_jedi_root": str(install)},
            "paths": {
                "work_dir": str(tmp_path / "work" / "mpaswf"),
                "static_dir": str(tmp_path / "work" / "mpaswf" / "static"),
                "gfs_dir": str(tmp_path / "data" / "gfs"),
                "cdct_templates_dir": str(templates),
            },
            "wps": {"vtable_name": "Vtable.GFS"},
            "templates": template_names,
            "static": {
                "reference_time": "2026-01-01T00:00:00Z",
                "product_template": "x1.10242.static.nc",
                "source": str(invariant),
                "tutorial_physics_files": str(tutorial),
                "links": [
                    {"source": str(mesh), "target": "x1.10242.grid.nc"},
                    {"source": str(graph), "target": "x1.10242.graph.info"},
                    {"source": str(partition), "target": "x1.10242.graph.info.part.128"},
                ],
            },
        },
    )


def test_preflight_accepts_existing_inputs_and_creatable_work_dirs(tmp_path: Path) -> None:
    report = config_preflight_report(_config(tmp_path))

    assert report["valid"] is True
    checks = {item["name"]: item for item in report["checks"]}

    assert checks["software.monan_jedi_root"]["status"] == "OK"
    assert checks["static.source"]["status"] == "OK"
    assert checks["static.links[2].source"]["status"] == "OK"
    assert checks["paths.work_dir"]["status"] == "CREATABLE"
    assert checks["paths.gfs_dir"]["status"] == "CREATABLE"


def test_preflight_reports_missing_required_static_asset(tmp_path: Path) -> None:
    config = _config(tmp_path)
    missing = Path(config.data["static"]["links"][1]["source"])
    missing.unlink()

    report = config_preflight_report(config)

    assert report["valid"] is False
    checks = {item["name"]: item for item in report["checks"]}
    assert checks["static.links[1].source"]["status"] == "MISSING"
    assert checks["static.links[1].source"]["path"] == str(missing)
