from pathlib import Path

from mpaswf.config import load_config
from mpaswf.workflow import load_campaign


def test_example_configuration_loads() -> None:
    root = Path(__file__).resolve().parents[1]
    config = load_config(root / "examples" / "config.yaml")
    campaign = load_campaign(config)
    assert len(campaign.pairs) == 16
