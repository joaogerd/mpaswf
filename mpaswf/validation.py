"""Artifact validation used by all workflow phases."""

from __future__ import annotations

from pathlib import Path

from .files import is_valid_file


def validate_file(path: Path, minimum_size_bytes: int, *, require_netcdf: bool = False) -> None:
    """Validate a non-empty output file and optionally open it as NetCDF.

    Parameters
    ----------
    path : pathlib.Path
        Product file path.
    minimum_size_bytes : int
        Lower bound used to reject empty or clearly incomplete products.
    require_netcdf : bool, default=False
        When true, try opening the file with `netCDF4.Dataset`.

    Raises
    ------
    FileNotFoundError
        Raised when the product is absent or too small.
    RuntimeError
        Raised when NetCDF inspection is requested but fails.
    """
    if not is_valid_file(path, minimum_size_bytes):
        raise FileNotFoundError(f"Required product is absent or too small: {path}")
    if not require_netcdf:
        return
    try:
        from netCDF4 import Dataset  # type: ignore[import-not-found]
    except ImportError as error:
        raise RuntimeError("validation.require_netcdf requires the optional netCDF4 dependency.") from error
    try:
        with Dataset(path, "r"):
            pass
    except Exception as error:  # noqa: BLE001 - provide the native NetCDF failure context.
        raise RuntimeError(f"NetCDF validation failed for {path}: {error}") from error
