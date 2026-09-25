from __future__ import annotations

from pathlib import Path

import pytest

from mpaswf.config import ConfigurationError, WorkflowConfig, load_config, value
from mpaswf.software import monan_jedi_root


def test_split_configuration_loads_and_deep_merges(monkeypatch) -> None:
    """Platform and workflow YAMLs merge without changing the public config API."""
    monkeypatch.setenv("USER", "mpaswf-test-user")
    monkeypatch.setenv("MONAN_JEDI_INSTALL_ROOT", "/runtime/monan-jedi")
    monkeypatch.setenv("STACK_ROOT", "/runtime/spack-stack")
    root = Path(__file__).resolve().parents[1]

    config = load_config(root / "configs" / "jaci-x1.10242.yaml")

    # Campaign/scientific values come from the workflow contract.
    assert value(config, "campaign.leads_hours") == [24, 48]
    assert value(config, "campaign.interval_hours") == 24
    assert value(config, "static.product_template") == "x1.10242.static.nc"

    # Machine-specific values come from the platform document and share the
    # same nested `static` mapping after the deep merge.
    links = value(config, "static.links")
    assert isinstance(links, list)
    assert links[0]["target"] == "x1.10242.grid.nc"
    assert value(config, "execution.backend") == "pbs"
    assert value(config, "software.monan_jedi_install_root") == "/runtime/monan-jedi"
    assert value(config, "pbs.stack_root") == "/runtime/spack-stack"

    # Environment expansion happens before the workflow sees paths.
    assert "mpaswf-test-user" in value(config, "paths.work_dir")
    assert config.data["workflow_contract_path"].endswith("configs/mpas-x1.10242.yaml")


def test_legacy_all_in_one_configuration_remains_supported() -> None:
    """The historical examples/config.yaml contract remains loadable unchanged."""
    root = Path(__file__).resolve().parents[1]
    config = load_config(root / "examples" / "config.yaml")

    assert value(config, "campaign.leads_hours") == [24, 48]
    assert "workflow_contract_path" not in config.data


def test_unresolved_environment_reference_fails_during_load(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("MISSING_RUNTIME_ROOT", raising=False)
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
paths:
  work_dir: /tmp/work
  static_dir: /tmp/static
  gfs_dir: /tmp/gfs
  cdct_templates_dir: /tmp/templates
campaign:
  start_valid_time: "2026-01-01T00:00:00Z"
  end_valid_time: "2026-01-02T00:00:00Z"
  leads_hours: [24, 48]
gfs:
  file_template: file
wps:
  output_template: output
products:
  init_state_template: init
  restart_template: restart
  da_state_template: da
templates:
  wps: wps
  static_namelist: static_nml
  static_streams: static_streams
  init_namelist: init_nml
  init_streams: init_streams
  forecast_namelist: forecast_nml
  forecast_streams: forecast_streams
static:
  reference_time: "2026-01-01T00:00:00Z"
  product_template: static.nc
execution:
  backend: local
validation: {}
software:
  monan_jedi_install_root: ${MISSING_RUNTIME_ROOT}
""",
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationError, match="MISSING_RUNTIME_ROOT"):
        load_config(config_path)


def test_legacy_monan_jedi_root_key_remains_accepted() -> None:
    config = WorkflowConfig(
        path=Path("/tmp/config.yaml"),
        data={"software": {"monan_jedi_root": "/legacy/install"}},
    )

    with pytest.warns(DeprecationWarning, match="monan_jedi_root"):
        assert monan_jedi_root(config) == Path("/legacy/install")


def test_deferred_pbs_shell_variable_does_not_fail_config_loading(tmp_path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
paths:
  work_dir: /tmp/work
  static_dir: /tmp/static
  gfs_dir: /tmp/gfs
  cdct_templates_dir: /tmp/templates
campaign:
  start_valid_time: "2026-01-01T00:00:00Z"
  end_valid_time: "2026-01-02T00:00:00Z"
  leads_hours: [24, 48]
gfs:
  file_template: file
wps:
  output_template: output
products:
  init_state_template: init
  restart_template: restart
  da_state_template: da
templates:
  wps: wps
  static_namelist: static_nml
  static_streams: static_streams
  init_namelist: init_nml
  init_streams: init_streams
  forecast_namelist: forecast_nml
  forecast_streams: forecast_streams
static:
  reference_time: "2026-01-01T00:00:00Z"
  product_template: static.nc
execution:
  backend: pbs
validation: {}
software:
  monan_jedi_install_root: /runtime/monan-jedi
pbs:
  queue: test
  walltime_static: "00:10:00"
  walltime_init: "00:10:00"
  walltime_forecast: "00:10:00"
  stack_root: /runtime/spack-stack
  bootstrap:
    - 'cd "$PBS_O_WORKDIR"'
""",
        encoding="utf-8",
    )

    config = load_config(config_path)
    assert value(config, "pbs.bootstrap")[0] == 'cd "$PBS_O_WORKDIR"'
