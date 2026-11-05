"""Mesh identity and parallel decomposition shared by init and forecasts."""

import re
import json
import hashlib
import warnings
from pathlib import Path

from .config import ConfigurationError, WorkflowConfig, string, value
from .files import write_json


def positive_integer(raw: object, key: str) -> int:
    if isinstance(raw, bool) or not isinstance(raw, int) or raw < 1:
        raise ConfigurationError(f"{key} must be a positive integer.")
    return raw


def mpi_ranks(config: WorkflowConfig) -> int:
    """Total model ranks; the local backend currently launches a serial process."""
    backend = string(config, "execution.backend", required=False, default="pbs")
    if backend == "local":
        ranks = positive_integer(
            value(config, "execution.mpi_ranks", required=False, default=1),
            "execution.mpi_ranks",
        )
        if ranks != 1:
            raise ConfigurationError(
                "The local backend runs the MPAS executable directly. "
                "Set execution.mpi_ranks: 1, or use execution.backend: pbs "
                "with a matching partition for parallel forecasts."
            )
        return 1
    if backend != "pbs":
        raise ConfigurationError("execution.backend must be 'local' or 'pbs'.")
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


def initialization_context(config: WorkflowConfig) -> dict[str, str]:
    """Scientific init dimensions come from the case, never from a tutorial.

    Each field is optional unless referenced by the selected namelist
    template. Vertical model levels and forcing/aerosol/soil levels describe
    different grids and must not be inferred from one another.
    """
    result = mesh_context(config)
    for field in ("nsoillevels", "nfglevels", "nfgsoillevels", "gocartlevels"):
        raw = value(config, f"initialization.levels.{field}", required=False, default=None)
        if raw is None:
            continue
        if isinstance(raw, bool) or not isinstance(raw, int) or (
            raw < 0 if field == "gocartlevels" else raw < 1
        ):
            raise ConfigurationError(
                f"initialization.levels.{field} must be "
                + ("a non-negative" if field == "gocartlevels" else "a positive")
                + " integer appropriate to this experiment."
            )
        result[field] = str(raw)
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


def _scientific_signature(config: WorkflowConfig) -> str:
    """Fingerprint fields that affect model inputs and produced forecast products.

    Requested date ranges are deliberately omitted: users may extend an
    otherwise identical campaign and safely reuse completed forecast cycles.
    """
    data = config.data
    science = {
        key: data.get(key)
        for key in (
            "mesh", "static", "runtime", "gfs", "wps",
            "templates", "products", "software", "executables",
        )
    }
    pbs = data.get("pbs")
    if isinstance(pbs, dict):
        science["decomposition"] = {
            "select": pbs.get("select", 1),
            "mpiprocs": pbs.get("mpiprocs"),
        }
    campaign = data.get("campaign")
    if isinstance(campaign, dict):
        science["lead_hours"] = campaign.get("leads_hours")
    encoded = json.dumps(science, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def ensure_campaign_identity(config: WorkflowConfig, work_dir: Path) -> None:
    """Refuse to reuse outputs generated with incompatible scientific settings."""
    if not staging_preflight_enabled(config):
        return
    identity = {
        "mesh": mesh_name(config),
        "nvertlevels": value(config, "mesh.nvertlevels", required=False, default=None),
        "scientific_sha256": _scientific_signature(config),
    }
    marker = work_dir / ".mpaswf" / "mesh.json"
    output_dirs = (work_dir / "init", work_dir / "forecast", work_dir / "products")
    has_outputs = any(path.is_dir() and any(path.iterdir()) for path in output_dirs)
    if marker.is_file():
        recorded = json.loads(marker.read_text(encoding="utf-8"))
        if not isinstance(recorded, dict) or any(
            recorded.get(key) != identity[key] for key in ("mesh", "nvertlevels")
        ):
            raise ConfigurationError(
                f"Work directory belongs to a different mesh or vertical grid: {work_dir}. "
                "Choose a new paths.work_dir."
            )
        previous = recorded.get("scientific_sha256")
        if previous is not None and previous != identity["scientific_sha256"]:
            raise ConfigurationError(
                f"Work directory contains forecasts from a different scientific configuration: {work_dir}. "
                "The mesh name may be unchanged, but its physics, timestep, input sources or "
                "parallel decomposition changed. Choose a new paths.work_dir."
            )
        if previous is None:
            if has_outputs:
                warnings.warn(
                    "Existing MPASWF workspace has an older mesh-only identity record. "
                    "Its scientific inputs cannot be verified against existing outputs. "
                    "Use a new paths.work_dir to guarantee isolation; this legacy run "
                    "will continue for backward compatibility.",
                    FutureWarning,
                    stacklevel=2,
                )
            else:
                write_json(marker, identity)
        return
    if has_outputs:
        raise ConfigurationError(
            f"Work directory contains unidentified existing outputs: {work_dir}. Use a new paths.work_dir."
        )
    write_json(marker, identity)
