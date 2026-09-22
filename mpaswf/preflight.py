"""Side-effect-free validation of configured MPASWF filesystem resources."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import os
from pathlib import Path
import shlex
from typing import Iterable

from .config import WorkflowConfig, render, resolve_path, string, value
from .forecast import (
    REFERENCE_NAMELIST_FILE,
    REFERENCE_PHYSICS_FILES,
    REFERENCE_STREAM_LISTS,
    REFERENCE_STREAMS_FILE,
)
from .layout import Layout
from .software import (
    atmosphere_share,
    installed_executable,
    monan_jedi_root,
    wps_executable,
    wps_vtable,
)
from .static import load_static_run


@dataclass(frozen=True)
class ResourceCheck:
    """One resolved filesystem preflight check."""

    name: str
    path: Path
    expectation: str
    status: str
    ok: bool
    detail: str = ""

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["path"] = str(self.path)
        return payload


def _nearest_existing_parent(path: Path) -> Path | None:
    candidate = path
    while not candidate.exists():
        parent = candidate.parent
        if parent == candidate:
            return None
        candidate = parent
    return candidate if candidate.is_dir() else candidate.parent


def _required_file(name: str, path: Path, *, executable: bool = False) -> ResourceCheck:
    if not path.exists():
        return ResourceCheck(name, path, "executable" if executable else "file", "MISSING", False)
    if not path.is_file():
        return ResourceCheck(name, path, "executable" if executable else "file", "WRONG_TYPE", False)
    if executable and not os.access(path, os.X_OK):
        return ResourceCheck(name, path, "executable", "NOT_EXECUTABLE", False)
    if not os.access(path, os.R_OK):
        return ResourceCheck(name, path, "executable" if executable else "file", "NOT_READABLE", False)
    return ResourceCheck(name, path, "executable" if executable else "file", "OK", True)


def _required_dir(name: str, path: Path) -> ResourceCheck:
    if not path.exists():
        return ResourceCheck(name, path, "directory", "MISSING", False)
    if not path.is_dir():
        return ResourceCheck(name, path, "directory", "WRONG_TYPE", False)
    if not os.access(path, os.R_OK | os.X_OK):
        return ResourceCheck(name, path, "directory", "NOT_ACCESSIBLE", False)
    return ResourceCheck(name, path, "directory", "OK", True)


def _writable_dir(name: str, path: Path) -> ResourceCheck:
    if path.exists():
        if not path.is_dir():
            return ResourceCheck(name, path, "writable directory", "WRONG_TYPE", False)
        if not os.access(path, os.W_OK | os.X_OK):
            return ResourceCheck(name, path, "writable directory", "NOT_WRITABLE", False)
        return ResourceCheck(name, path, "writable directory", "OK", True)

    parent = _nearest_existing_parent(path)
    if parent is None:
        return ResourceCheck(
            name,
            path,
            "writable directory",
            "NO_EXISTING_PARENT",
            False,
            "No existing ancestor directory could be resolved.",
        )
    if not os.access(parent, os.W_OK | os.X_OK):
        return ResourceCheck(
            name,
            path,
            "writable directory",
            "PARENT_NOT_WRITABLE",
            False,
            f"Nearest existing parent is not writable: {parent}",
        )
    return ResourceCheck(
        name,
        path,
        "writable directory",
        "CREATABLE",
        True,
        f"Directory does not exist yet; nearest writable parent is {parent}",
    )


def _existing_path(name: str, path: Path) -> ResourceCheck:
    if not path.exists():
        return ResourceCheck(name, path, "existing path", "MISSING", False)
    if not os.access(path, os.R_OK):
        return ResourceCheck(name, path, "existing path", "NOT_READABLE", False)
    return ResourceCheck(name, path, "existing path", "OK", True)


def _resolve_bootstrap_path(raw: str, base: Path) -> tuple[Path | None, str | None]:
    expanded = os.path.expandvars(raw)
    if "$" in expanded:
        return None, f"Unresolved environment variable in bootstrap path: {raw}"
    path = Path(expanded).expanduser()
    return (path if path.is_absolute() else (base / path).resolve()), None


def _bootstrap_checks(config: WorkflowConfig) -> Iterable[ResourceCheck]:
    commands = value(config, "pbs.bootstrap", required=False, default=[])
    if not isinstance(commands, list):
        return

    current_dir = config.root
    directory_stack: list[Path] = []

    for index, command in enumerate(commands):
        if not isinstance(command, str) or not command.strip():
            continue
        try:
            tokens = shlex.split(command)
        except ValueError:
            continue
        if not tokens:
            continue

        if tokens[0] in {"pushd", "cd"} and len(tokens) >= 2:
            path, error = _resolve_bootstrap_path(tokens[1], current_dir)
            if error is not None or path is None:
                yield ResourceCheck(
                    f"pbs.bootstrap[{index}]",
                    Path(tokens[1]),
                    "bootstrap directory",
                    "UNRESOLVED_ENV",
                    False,
                    error or "",
                )
                continue
            yield _required_dir(f"pbs.bootstrap[{index}].directory", path)
            if tokens[0] == "pushd":
                directory_stack.append(current_dir)
            current_dir = path
            continue

        if tokens[0] == "popd":
            if directory_stack:
                current_dir = directory_stack.pop()
            continue

        if tokens[0] == "source" and len(tokens) >= 2:
            path, error = _resolve_bootstrap_path(tokens[1], current_dir)
            if error is not None or path is None:
                yield ResourceCheck(
                    f"pbs.bootstrap[{index}]",
                    Path(tokens[1]),
                    "bootstrap source file",
                    "UNRESOLVED_ENV",
                    False,
                    error or "",
                )
                continue
            yield _required_file(f"pbs.bootstrap[{index}].source", path)
            continue

        if tokens[0:2] == ["module", "use"] and len(tokens) >= 3:
            path, error = _resolve_bootstrap_path(tokens[2], current_dir)
            if error is not None or path is None:
                yield ResourceCheck(
                    f"pbs.bootstrap[{index}]",
                    Path(tokens[2]),
                    "module directory",
                    "UNRESOLVED_ENV",
                    False,
                    error or "",
                )
                continue
            yield _required_dir(f"pbs.bootstrap[{index}].module_use", path)


def _template_checks(config: WorkflowConfig, layout: Layout) -> Iterable[ResourceCheck]:
    """Validate only templates used by the active configuration path."""
    yield _required_dir("paths.cdct_templates_dir", layout.templates_dir)

    always_used = (
        "templates.wps",
        "templates.init_namelist",
        "templates.init_streams",
    )
    for key in always_used:
        name = string(config, key) or ""
        yield _required_file(key, layout.templates_dir / name)

    # Static templates are bypassed when a validated external invariant is
    # supplied through static.source.
    if string(config, "static.source", required=False, default=None) is None:
        for key in ("templates.static_namelist", "templates.static_streams"):
            name = string(config, key) or ""
            yield _required_file(key, layout.templates_dir / name)

    # The strict x1.10242/JACI reference forecast stages the proven tutorial
    # namelist/streams instead of the generic forecast templates.
    reference_forecast = bool(
        value(
            config,
            "validation.require_reference_preflight",
            required=False,
            default=False,
        )
    )
    if not reference_forecast:
        for key in ("templates.forecast_namelist", "templates.forecast_streams"):
            name = string(config, key) or ""
            yield _required_file(key, layout.templates_dir / name)


def _static_checks(config: WorkflowConfig, layout: Layout) -> Iterable[ResourceCheck]:
    run = load_static_run(config, layout)

    raw_source = string(config, "static.source", required=False, default=None)
    if raw_source is not None:
        context = {
            "static_state": str(run.state_path),
            "static_dir": str(run.run_dir),
        }
        yield _required_file("static.source", resolve_path(config, raw_source, context))

    reference_forecast = bool(
        value(
            config,
            "validation.require_reference_preflight",
            required=False,
            default=False,
        )
    )
    tutorial_files = string(
        config,
        "static.tutorial_physics_files",
        required=False,
        default=None,
    )
    if tutorial_files is None and reference_forecast:
        yield ResourceCheck(
            "static.tutorial_physics_files",
            Path("<not configured>"),
            "configured directory",
            "NOT_CONFIGURED",
            False,
            "Required when validation.require_reference_preflight is true.",
        )
    elif tutorial_files is not None:
        tutorial_dir = resolve_path(config, tutorial_files)
        yield _required_dir("static.tutorial_physics_files", tutorial_dir)

        if reference_forecast:
            yield _required_file(
                "reference.forecast_namelist",
                tutorial_dir / REFERENCE_NAMELIST_FILE,
            )
            yield _required_file(
                "reference.forecast_streams",
                tutorial_dir / REFERENCE_STREAMS_FILE,
            )
            for name in REFERENCE_STREAM_LISTS:
                yield _required_file(
                    f"reference.{name}",
                    tutorial_dir / name,
                )

    links = value(config, "static.links", required=False, default=[])
    if not isinstance(links, list):
        return

    context = layout.context(
        run.reference_time,
        run.reference_time,
        0,
        run.run_dir,
    )
    for index, entry in enumerate(links):
        if not isinstance(entry, dict):
            continue
        source = entry.get("source")
        if not isinstance(source, str) or not source:
            continue
        rendered = render(source, context)
        path = Path(rendered).expanduser()
        if not path.is_absolute():
            path = (config.root / path).resolve()
        yield _existing_path(f"static.links[{index}].source", path)


def check_config_resources(config: WorkflowConfig) -> list[ResourceCheck]:
    """Resolve and validate the filesystem resources required by one config.

    The check is intentionally side-effect free. Writable workflow/data
    directories are accepted when they already exist and are writable, or when
    their nearest existing parent is writable so MPASWF can create them later.
    """
    layout = Layout.from_config(config)
    checks: list[ResourceCheck] = []

    root = monan_jedi_root(config)
    if root is not None:
        checks.append(_required_dir("software.monan_jedi_root", root))

    share = atmosphere_share(config)
    checks.extend(
        [
            _required_file(
                "software.mpas_init_atmosphere",
                installed_executable(config, "executables.mpas_init", "mpas_init_atmosphere"),
                executable=True,
            ),
            _required_file(
                "software.mpas_atmosphere",
                installed_executable(
                    config,
                    "executables.mpas_atmosphere",
                    "mpas_atmosphere",
                ),
                executable=True,
            ),
            _required_file(
                "software.ungrib.exe",
                wps_executable(config, "ungrib.exe"),
                executable=True,
            ),
            _required_file(
                "software.link_grib.csh",
                wps_executable(config, "link_grib.csh"),
                executable=True,
            ),
            _required_file("wps.vtable", wps_vtable(config, {})),
            _required_dir("software.atmosphere_share", share),
            _writable_dir("paths.work_dir", layout.work_dir),
            _writable_dir("paths.static_dir", layout.static_dir),
            _writable_dir("paths.gfs_dir", layout.gfs_dir),
        ]
    )

    if bool(
        value(
            config,
            "validation.require_reference_preflight",
            required=False,
            default=False,
        )
    ):
        for name in REFERENCE_PHYSICS_FILES:
            checks.append(
                _required_file(
                    f"reference.physics.{name}",
                    share / name,
                )
            )

    checks.extend(_template_checks(config, layout))
    checks.extend(_static_checks(config, layout))
    checks.extend(_bootstrap_checks(config))
    return checks


def config_preflight_report(config: WorkflowConfig) -> dict[str, object]:
    checks = check_config_resources(config)
    return {
        "config": str(config.path),
        "workflow_contract_path": config.data.get("workflow_contract_path"),
        "valid": all(check.ok for check in checks),
        "checks": [check.to_dict() for check in checks],
    }
