"""Define deterministic campaign directories and product paths for MPASWF.

The :class:`Layout` object centralizes path construction so every workflow phase
uses the same directory conventions for GFS inputs, WPS intermediates, MPAS
initializations, forecasts, metadata, and exported products.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .config import WorkflowConfig, resolve_path, string
from .model import render_time_context


@dataclass(frozen=True)
class Layout:
    """Store resolved top-level directories for one MPASWF campaign.

    Parameters
    ----------
    work_dir : pathlib.Path
        Root directory containing per-stage work directories and workflow
        metadata.
    static_dir : pathlib.Path
        Directory containing the one-time mesh-level static interpolation run.
    gfs_dir : pathlib.Path
        Root directory containing GFS inputs grouped by initialization time.
    templates_dir : pathlib.Path
        Directory containing CD-CT-derived namelist and streams templates.
    """

    work_dir: Path
    static_dir: Path
    gfs_dir: Path
    templates_dir: Path

    @classmethod
    def from_config(cls, config: WorkflowConfig) -> "Layout":
        """Build a resolved layout from the configuration ``paths`` section.

        Parameters
        ----------
        config : WorkflowConfig
            Loaded workflow configuration.

        Returns
        -------
        Layout
            Layout whose configured paths have user-home expansion and
            configuration-relative resolution applied.

        Raises
        ------
        ConfigurationError
            Propagated when a required path value is absent, malformed, or
            references an unknown template placeholder.
        """
        return cls(
            work_dir=resolve_path(config, string(config, "paths.work_dir") or ""),
            static_dir=resolve_path(config, string(config, "paths.static_dir") or ""),
            gfs_dir=resolve_path(config, string(config, "paths.gfs_dir") or ""),
            templates_dir=resolve_path(config, string(config, "paths.cdct_templates_dir") or ""),
        )

    @property
    def metadata_dir(self) -> Path:
        """Return the workflow-private metadata directory.

        Returns
        -------
        pathlib.Path
            ``.mpaswf`` directory below :attr:`work_dir`.
        """
        return self.work_dir / ".mpaswf"

    @property
    def products_dir(self) -> Path:
        """Return the directory containing neutral MPAS product hand-offs.

        Returns
        -------
        pathlib.Path
            ``products`` directory below :attr:`work_dir`.
        """
        return self.work_dir / "products"

    def wps_dir(self, init_time: datetime) -> Path:
        """Return the WPS run directory for one initialization time.

        Parameters
        ----------
        init_time : datetime
            Initialization timestamp used to form the ``YYYYMMDDHH`` directory
            name.

        Returns
        -------
        pathlib.Path
            WPS directory below ``<work_dir>/wps``.
        """
        return self.work_dir / "wps" / init_time.strftime("%Y%m%d%H")

    def init_dir(self, init_time: datetime) -> Path:
        """Return the MPAS initialization directory for one timestamp.

        Parameters
        ----------
        init_time : datetime
            Initialization timestamp used to form the ``YYYYMMDDHH`` directory
            name.

        Returns
        -------
        pathlib.Path
            Initialization directory below ``<work_dir>/init``.
        """
        return self.work_dir / "init" / init_time.strftime("%Y%m%d%H")

    def forecast_dir(self, init_time: datetime, lead_hours: int) -> Path:
        """Return the MPAS forecast directory for one forecast request.

        Parameters
        ----------
        init_time : datetime
            Forecast initialization timestamp.
        lead_hours : int
            Forecast lead time in hours, formatted as ``fNNN``.

        Returns
        -------
        pathlib.Path
            Directory below ``<work_dir>/forecast/YYYYMMDDHH/fNNN``.
        """
        return self.work_dir / "forecast" / init_time.strftime("%Y%m%d%H") / f"f{lead_hours:03d}"

    def gfs_dir_for_time(self, init_time: datetime) -> Path:
        """Return the local GFS directory for one initialization time.

        Parameters
        ----------
        init_time : datetime
            GFS initialization timestamp.

        Returns
        -------
        pathlib.Path
            Directory below :attr:`gfs_dir` named ``YYYYMMDDHH``.
        """
        return self.gfs_dir / init_time.strftime("%Y%m%d%H")

    def context(self, init_time: datetime, valid_time: datetime, lead_hours: int, run_dir: Path) -> dict[str, str]:
        """Build the standard template context with resolved directories.

        Parameters
        ----------
        init_time : datetime
            Forecast or initialization start timestamp.
        valid_time : datetime
            Product valid timestamp.
        lead_hours : int
            Forecast lead time in hours.
        run_dir : pathlib.Path
            Stage-specific working directory.

        Returns
        -------
        dict[str, str]
            Time placeholders from :func:`mpaswf.model.render_time_context`
            augmented with ``work_dir``, ``static_dir``, ``templates_dir``, and
            ``run_dir``.
        """
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
