from __future__ import annotations

from pathlib import Path

from mpaswf.config import load_config, value


def test_split_configuration_loads_and_deep_merges(monkeypatch) -> None:
    """Platform and workflow YAMLs merge without changing the public config API."""
    monkeypatch.setenv("USER", "mpaswf-test-user")
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

    # Environment expansion happens before the workflow sees paths.
    assert "mpaswf-test-user" in value(config, "paths.work_dir")
    assert config.data["workflow_contract_path"].endswith("configs/mpas-x1.10242.yaml")


def test_legacy_all_in_one_configuration_remains_supported() -> None:
    """The historical examples/config.yaml contract remains loadable unchanged."""
    root = Path(__file__).resolve().parents[1]
    config = load_config(root / "examples" / "config.yaml")

    assert value(config, "campaign.leads_hours") == [24, 48]
    assert "workflow_contract_path" not in config.data
