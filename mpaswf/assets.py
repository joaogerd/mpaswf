"""Reusable staging of fixed CD-CT assets into MPAS run directories.

The assets declared in ``static.links`` are not a prebuilt static MPAS product.
They are fixed mesh, partition, invariant, table, and support files shared by
static interpolation, dynamic initialization, and forecast stages.
"""

from __future__ import annotations

from pathlib import Path
from typing import Mapping

from .config import WorkflowConfig, render, value
from .files import ensure_link


def stage_common_links(
    config: WorkflowConfig,
    run_dir: Path,
    context: Mapping[str, str],
) -> None:
    """Link fixed CD-CT assets into one MPAS run directory.

    Parameters
    ----------
    config : WorkflowConfig
        Loaded workflow configuration.
    run_dir : pathlib.Path
        Stage-specific working directory.
    context : mapping of str to str
        Render context for configured source and target templates.

    Raises
    ------
    ValueError
        Raised when ``static.links`` is malformed.
    FileNotFoundError
        Raised when a declared source asset is missing.
    """
    entries = value(config, "static.links", required=False, default=[])
    if not isinstance(entries, list):
        raise ValueError("static.links must be a list.")

    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ValueError(f"static.links[{index}] must be a mapping.")
        source_raw = entry.get("source")
        target_raw = entry.get("target")
        if not isinstance(source_raw, str) or not isinstance(target_raw, str):
            raise ValueError(f"static.links[{index}] requires string source and target.")

        source = Path(render(source_raw, context)).expanduser()
        if not source.is_absolute():
            source = (config.root / source).resolve()
        target = run_dir / render(target_raw, context)
        ensure_link(source, target)
