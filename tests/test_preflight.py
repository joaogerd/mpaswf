from __future__ import annotations

from pathlib import Path

from mpaswf.config import WorkflowConfig
from mpaswf.forecast import REFERENCE_PHYSICS_FILES, REFERENCE_STREAM_LISTS
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
    atmosphere_share = install / "share" / "MPAS" / "core_atmosphere"
    atmosphere_share.mkdir(parents=True)
    for name in REFERENCE_PHYSICS_FILES:
        _touch(atmosphere_share / name)

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
    _touch(tutorial / "namelist.atmosphere_240km")
    _touch(tutorial / "streams.atmosphere_240km")
    for name in REFERENCE_STREAM_LISTS:
        _touch(tutorial / name)

    stack = tmp_path / "spack-stack"
    _touch(stack / "configs" / "sites" / "tier2" / "jaci" / "setup.sh")
    (stack / "envs" / "test" / "modules").mkdir(parents=True)

    return WorkflowConfig(
        path=tmp_path / "configs" / "jaci.yaml",
        data={
            "software": {"monan_jedi_install_root": str(install)},
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
            "pbs": {
                "bootstrap": [
                    f"pushd {stack} >/dev/null",
                    "source configs/sites/tier2/jaci/setup.sh",
                    "popd >/dev/null",
                    f"module use {stack / 'envs' / 'test' / 'modules'}",
                ]
            },
        },
    )


def test_preflight_accepts_existing_inputs_and_creatable_work_dirs(tmp_path: Path) -> None:
    report = config_preflight_report(_config(tmp_path))

    assert report["valid"] is True
    checks = {item["name"]: item for item in report["checks"]}

    assert checks["software.monan_jedi_install_root"]["status"] == "OK"
    assert checks["static.source"]["status"] == "OK"
    assert checks["static.links[2].source"]["status"] == "OK"
    assert checks["paths.work_dir"]["status"] == "CREATABLE"
    assert checks["paths.gfs_dir"]["status"] == "CREATABLE"
    assert checks["pbs.bootstrap[0].directory"]["status"] == "OK"
    assert checks["pbs.bootstrap[1].source"]["status"] == "OK"
    assert checks["pbs.bootstrap[3].module_use"]["status"] == "OK"


def test_preflight_reports_missing_required_static_asset(tmp_path: Path) -> None:
    config = _config(tmp_path)
    missing = Path(config.data["static"]["links"][1]["source"])
    missing.unlink()

    report = config_preflight_report(config)

    assert report["valid"] is False
    checks = {item["name"]: item for item in report["checks"]}
    assert checks["static.links[1].source"]["status"] == "MISSING"
    assert checks["static.links[1].source"]["path"] == str(missing)


def test_preflight_reports_missing_bootstrap_source(tmp_path: Path) -> None:
    config = _config(tmp_path)
    stack = Path(config.data["pbs"]["bootstrap"][0].split()[1])
    (stack / "configs" / "sites" / "tier2" / "jaci" / "setup.sh").unlink()

    report = config_preflight_report(config)

    assert report["valid"] is False
    checks = {item["name"]: item for item in report["checks"]}
    assert checks["pbs.bootstrap[1].source"]["status"] == "MISSING"



def test_reference_path_skips_unused_generic_templates(tmp_path: Path) -> None:
    config = _config(tmp_path)
    config.data["validation"] = {"require_reference_preflight": True}

    templates = Path(config.data["paths"]["cdct_templates_dir"])
    for key in (
        "static_namelist",
        "static_streams",
        "forecast_namelist",
        "forecast_streams",
    ):
        (templates / config.data["templates"][key]).unlink()

    report = config_preflight_report(config)

    assert report["valid"] is True
    checks = {item["name"]: item for item in report["checks"]}

    assert "templates.static_namelist" not in checks
    assert "templates.static_streams" not in checks
    assert "templates.forecast_namelist" not in checks
    assert "templates.forecast_streams" not in checks
    assert checks["reference.forecast_namelist"]["status"] == "OK"
    assert checks["reference.forecast_streams"]["status"] == "OK"


def test_reference_path_reports_missing_real_forecast_input(tmp_path: Path) -> None:
    config = _config(tmp_path)
    config.data["validation"] = {"require_reference_preflight": True}

    tutorial = Path(config.data["static"]["tutorial_physics_files"])
    (tutorial / "streams.atmosphere_240km").unlink()

    report = config_preflight_report(config)

    assert report["valid"] is False
    checks = {item["name"]: item for item in report["checks"]}
    assert checks["reference.forecast_streams"]["status"] == "MISSING"



def test_reference_path_requires_tutorial_directory_configuration(tmp_path: Path) -> None:
    config = _config(tmp_path)
    config.data["validation"] = {"require_reference_preflight": True}
    del config.data["static"]["tutorial_physics_files"]

    report = config_preflight_report(config)

    assert report["valid"] is False
    checks = {item["name"]: item for item in report["checks"]}
    assert checks["static.tutorial_physics_files"]["status"] == "NOT_CONFIGURED"
