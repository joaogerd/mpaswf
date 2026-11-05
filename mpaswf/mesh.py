"""Mesh identity and parallel decomposition shared by init and forecasts."""

import re
import json
from pathlib import Path

from .config import ConfigurationError, WorkflowConfig, string, value
from .files import write_json


def positive_integer(raw: object, key: str) -> int:
    if isinstance(raw, bool) or not isinstance(raw, int) or raw < 1:
        raise ConfigurationError(f"{key} must be a positive integer.")
    return raw


def mpi_ranks(config: WorkflowConfig) -> int:
    """PBS mpiprocs is per chunk, not the whole allocation."""
    return positive_integer(
        value(config, "pbs.select", required=False, default=1), "pbs.select"
    ) * positive_integer(value(config, "pbs.mpiprocs"), "pbs.mpiprocs")


def mesh_name(config: WorkflowConfig) -> str:
    name = string(config, "mesh.name", required=False, default=None)
    if name is None:
        product = string(config, "static.product_template") or ""
        match = re.fullmatch(r"([A-Za-z0-9_.-]+)\.(?:static|invariant)\.nc", product)
        if match is None:
            raise ConfigurationError(
                "Declare mesh.name explicitly for this static.product_template."
            )
        name = match.group(1)
    if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]*", name):
        raise ConfigurationError("mesh.name must be a filename-safe mesh identifier.")
    return name


def _run_filename(config: WorkflowConfig, key: str, fallback: str) -> str:
    """A mesh run filename is configurable, but must remain within the run directory."""
    raw = string(config, key, required=False, default=None)
    filename = raw if raw is not None else fallback
    if not filename or Path(filename).name != filename or filename in {".", ".."}:
        raise ConfigurationError(
            f"{key} must be a filename, not a path. Set the staged filename "
            "matching the destination in static.links."
        )
    return filename


def mesh_grid_filename(config: WorkflowConfig) -> str:
    return _run_filename(config, "mesh.grid_filename", f"{mesh_name(config)}.grid.nc")


def mesh_graph_filename(config: WorkflowConfig) -> str:
    return _run_filename(config, "mesh.graph_filename", f"{mesh_name(config)}.graph.info")


def partition_prefix(config: WorkflowConfig) -> str:
    return _run_filename(
        config, "mesh.partition_prefix", f"{mesh_graph_filename(config)}.part."
    )


def mesh_context(config: WorkflowConfig) -> dict[str, str]:
    """Names and dimensions selected by the case, not by a particular resolution."""
    result = {
        "mesh_name": mesh_name(config),
        "grid_filename": mesh_grid_filename(config),
        "graph_filename": mesh_graph_filename(config),
        "partition_prefix": partition_prefix(config),
    }
    levels = value(config, "mesh.nvertlevels", required=False, default=None)
    if levels is not None:
        result["nvertlevels"] = str(positive_integer(levels, "mesh.nvertlevels"))
    return result


def staging_preflight_enabled(config: WorkflowConfig) -> bool:
    """Enable mesh-aware checks, accepting the old flag for existing campaigns."""
    setting = value(
        config, "validation.require_staging_preflight", required=False, default=None
    )
    if setting is None:
        setting = value(
            config, "validation.require_reference_preflight",
            required=False, default=False,
        )
    if not isinstance(setting, bool):
        raise ConfigurationError(
            "validation.require_staging_preflight must be true or false."
        )
    return setting


def ensure_campaign_identity(config: WorkflowConfig, work_dir: Path) -> None:
    """Do not reuse neutral forecast filenames from another mesh/campaign."""
    if not staging_preflight_enabled(config):
        return
    identity = {
        "mesh": mesh_name(config),
        "nvertlevels": value(config, "mesh.nvertlevels", required=False, default=None),
    }
    marker = work_dir / ".mpaswf" / "mesh.json"
    if marker.is_file():
        if json.loads(marker.read_text()) != identity:
            raise ConfigurationError(
                f"Work directory belongs to a different mesh or vertical grid: {work_dir}. Use a new paths.work_dir."
            )
        return
    if any(
        path.is_dir() and any(path.iterdir())
        for path in (work_dir / "init", work_dir / "forecast", work_dir / "products")
    ):
        raise ConfigurationError(
            f"Work directory contains unidentified existing outputs: {work_dir}. Use a new paths.work_dir."
        )
    write_json(marker, identity)
