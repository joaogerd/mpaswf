"""Deterministic directory and product-path layout for `mpaswf`."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .config import WorkflowConfig, resolve_path, string
from .model import render_time_context


@dataclass(frozen=True)
class Layout:
    """Resolved top-level campaign directories."""

    work_dir: Path
    static_dir: Path
    gfs_dir: Path
    templates_dir: Path

    @classmethod
    def from_config(cls, config: WorkflowConfig) -> "Layout":
        """Build a layout from the `paths` section."""
        return cls(
            work_dir=resolve_path(config, string(config, "paths.work_dir") or ""),
            static_dir=resolve_path(config, string(config, "paths.static_dir") or ""),
            gfs_dir=resolve_path(config, string(config, "paths.gfs_dir") or ""),
            templates_dir=resolve_path(config, string(config, "paths.cdct_templates_dir") or ""),
        )

    @property
    def metadata_dir(self) -> Path:
        """Return the workflow-private state directory."""
        return self.work_dir / ".mpaswf"

    @property
    def products_dir(self) -> Path:
        """Return the directory containing neutral MPAS product hand-offs."""
        return self.work_dir / "products"

    def wps_dir(self, init_time: datetime) -> Path:
        """Return the WPS run directory for one initialization time."""
        return self.work_dir / "wps" / init_time.strftime("%Y%m%d%H")

    def init_dir(self, init_time: datetime) -> Path:
        """Return the MPAS initialization run directory for one time."""
        return self.work_dir / "init" / init_time.strftime("%Y%m%d%H")

    def forecast_dir(self, init_time: datetime, lead_hours: int) -> Path:
        """Return the MPAS forecast run directory for one request."""
        return self.work_dir / "forecast" / init_time.strftime("%Y%m%d%H") / f"f{lead_hours:03d}"

    def gfs_dir_for_time(self, init_time: datetime) -> Path:
        """Return the local GFS directory for one initialization time."""
        return self.gfs_dir / init_time.strftime("%Y%m%d%H")

    def context(self, init_time: datetime, valid_time: datetime, lead_hours: int, run_dir: Path) -> dict[str, str]:
        """Return standard template context enriched with configured directories."""
        context = render_time_context(init_time, valid_time, lead_hours)
        context.update(
            {
                "work_dir": str(self.work_dir),
                "static_dir": str(self.static_dir),
                "templates_dir": str(self.templates_dir),
                "run_dir": str(run_dir),
            }
        )
        return context
