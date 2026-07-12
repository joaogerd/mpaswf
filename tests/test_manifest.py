"""Tests for loading the distributed example campaign configuration."""

from pathlib import Path

from mpaswf.config import load_config
from mpaswf.workflow import load_campaign


def test_example_configuration_loads() -> None:
    """Verify that the example configuration resolves sixteen product pairs.

    Notes
    -----
    The test loads ``examples/config.yaml`` relative to the repository root and
    checks only the deterministic campaign size; it does not access configured
    external files or execute workflow stages.
    """
    root = Path(__file__).resolve().parents[1]
    config = load_config(root / "examples" / "config.yaml")
    campaign = load_campaign(config)
    assert len(campaign.pairs) == 16
