from pathlib import Path

from mpaswf.config import load_config
from mpaswf.workflow import load_campaign


def test_example_configuration_loads() -> None:
    root = Path(__file__).resolve().parents[1]
    config = load_config(root / "examples" / "config.yaml")
    campaign = load_campaign(config)
    assert len(campaign.pairs) == 16


def test_manifest_contract_identity_is_documented_in_workflow_source() -> None:
    # Lightweight regression: the public producer contract must remain explicit
    # even when forecast execution itself is exercised in integration tests.
    root = Path(__file__).resolve().parents[1]
    source = (root / "mpaswf" / "workflow.py").read_text(encoding="utf-8")
    assert '"contract": "monan-nmc-forecast-pairs-v1"' in source
    assert '"producer": "mpaswf"' in source
    assert '"consumer": "MPAS-BMatrix"' in source
    assert '"manifest_sha256": digest' in source
