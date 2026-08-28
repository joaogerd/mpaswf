from __future__ import annotations

from pathlib import Path

from mpaswf.config import WorkflowConfig, load_config, value
from mpaswf.software import installed_executable, monan_jedi_root, wps_executable, wps_vtable


def _config(data: dict[str, object]) -> WorkflowConfig:
    return WorkflowConfig(path=Path("/tmp/configs/platform.yaml"), data=data)


def test_jaci_configuration_uses_one_monan_jedi_root(monkeypatch) -> None:
    monkeypatch.setenv("USER", "runtime-user")
    root = Path(__file__).resolve().parents[1]
    config = load_config(root / "configs" / "jaci-x1.10242.yaml")

    expected = "/p/projetos/monan_das/runtime-user/build/monan-jedi"
    assert value(config, "software.monan_jedi_root") == expected
    assert monan_jedi_root(config) == Path(expected)
    assert installed_executable(config, "executables.mpas_init", "mpas_init_atmosphere") == Path(expected) / "bin/mpas_init_atmosphere"
    assert installed_executable(config, "executables.mpas_atmosphere", "mpas_atmosphere") == Path(expected) / "bin/mpas_atmosphere"
    assert wps_executable(config, "ungrib.exe") == Path(expected) / "bin/ungrib.exe"
    assert wps_executable(config, "link_grib.csh") == Path(expected) / "bin/link_grib.csh"
    assert wps_vtable(config, {}) == Path(expected) / "share/wps/Variable_Tables/Vtable.GFS"


def test_legacy_executable_layout_remains_supported() -> None:
    config = _config(
        {
            "executables": {
                "wps_dir": "/legacy/WPS",
                "mpas_init": "/legacy/bin/mpas_init_atmosphere",
                "mpas_atmosphere": "/legacy/bin/mpas_atmosphere",
            },
            "wps": {"vtable": "{wps_dir}/ungrib/Variable_Tables/Vtable.GFS"},
        }
    )

    assert monan_jedi_root(config) is None
    assert installed_executable(config, "executables.mpas_init", "mpas_init_atmosphere") == Path("/legacy/bin/mpas_init_atmosphere")
    assert wps_executable(config, "ungrib.exe") == Path("/legacy/WPS/ungrib.exe")
    assert wps_vtable(config, {"wps_dir": "/legacy/WPS"}) == Path("/legacy/WPS/ungrib/Variable_Tables/Vtable.GFS")
