"""Side-effect-free validation of configured MPASWF filesystem resources."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import os
from pathlib import Path
import shlex
from typing import Iterable

from .config import ConfigurationError, WorkflowConfig, render, resolve_path, string, value
from .forecast import (
    forecast_sources, stream_list_directory, stream_lists,
    physics_files,
)
from .layout import Layout
from .software import (
    atmosphere_share,
    installed_executable,
    monan_jedi_root,
    runtime_contract,
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
        if not self.ok:
            payload["detail"] = explain_failure(self)
        return payload


def explain_failure(check: ResourceCheck) -> str:
    """Explain an actionable filesystem failure without changing status IDs."""
    guidance = {
        "MISSING": "Required resource does not exist. Check its configured path and stage or install the file.",
        "WRONG_TYPE": "The path exists, but is not the expected file or directory. Correct the path.",
        "NOT_READABLE": "File cannot be read. Check ownership, ACLs, and read permission.",
        "NOT_ACCESSIBLE": "Directory cannot be accessed. Grant read and traverse (execute) permission.",
        "NOT_EXECUTABLE": "Executable cannot be run. Check installation and execute permission.",
        "NOT_WRITABLE": "Directory is not writable. Check ownership, ACLs, and write/traverse permissions.",
        "PARENT_NOT_WRITABLE": "Directory does not exist and its parent cannot be written. Create it in a writable location or adjust permissions.",
        "NO_EXISTING_PARENT": "No existing directory ancestor was found. Check the configured path.",
        "INVALID": "The installed runtime contract is invalid or incompatible. Review the manifest and installation.",
        "NOT_CONFIGURED": "Required forecast inputs are not fully configured. Review the runtime YAML entries.",
    }
    base = check.detail.strip()
    advice = guidance.get(check.status, "Review this configuration resource.")
    if check.name == "paths.gfs_dir" and check.status in {"NOT_WRITABLE", "PARENT_NOT_WRITABLE"}:
        advice += (
            " Automatic GFS downloads need a writable destination; to use pre-existing "
            "read-only files, set gfs.acquisition: external."
        )
    if check.name.startswith("reference.forecast_") and check.status == "MISSING":
        advice += " Set runtime.forecast_namelist and runtime.forecast_streams to existing MPAS case files."
    if check.name.startswith("reference.stream_list.") and check.status == "MISSING":
        advice += " Check runtime.stream_list_directory and runtime.stream_lists."
    if check.name == "paths.cdct_templates_dir":
        advice += " Inspect paths.cdct_templates_dir in the platform YAML."
    if check.name == "static.source":
        advice += " Check static.source (the precomputed invariant input)."
    if check.name.startswith("static.links["):
        advice += " Check the matching static.links entry and its source path."
    return f"{base} {advice}".strip() if base else advice


def _forecast_configuration_failure(config: WorkflowConfig, error: Exception) -> ResourceCheck:
    """Convert a missing forecast configuration to a user-facing diagnosis."""
    from .mesh import mesh_name

    mesh = mesh_name(config)
    nml = string(config, "runtime.forecast_namelist", required=False, default=None)
    streams = string(config, "runtime.forecast_streams", required=False, default=None)
    directory = string(config, "runtime.stream_list_directory", required=False, default=None)
    if not nml or not streams:
        missing = [
            key for key, configured in (
                ("runtime.forecast_namelist", nml),
                ("runtime.forecast_streams", streams),
            ) if not configured
        ]
        if mesh == "x1.10242" and not nml and not streams:
            missing.append("static.tutorial_physics_files (legacy 240-km fallback)")
        suggestion = (
            "Provide the MPAS namelist.atmosphere and streams.atmosphere files "
            "for the selected mesh. "
        )
    elif not directory:
        missing = ["runtime.stream_list_directory"]
        suggestion = (
            "Set runtime.stream_list_directory to the directory containing "
            "the configured stream_list files (or set runtime.stream_lists: [] "
            "if none are needed). "
        )
    else:
        missing = []
        suggestion = "Verify runtime.stream_lists and the selected forecast inputs. "
    detail = (
        f"Forecast source configuration for mesh {mesh} is incomplete or invalid. "
        f"{'Missing: ' + ', '.join(missing) + '. ' if missing else ''}"
        f"{suggestion}Cause: {error}. "
        "See docs/mesh-independent-campaigns.md."
    )
    return ResourceCheck(
        "runtime.forecast_sources", Path("<configuration>"),
        "MPAS forecast input configuration", "NOT_CONFIGURED", False, detail
    )


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


def _resolve_bootstrap_path(
    raw: str,
    base: Path,
    *,
    stack_root: str | None = None,
) -> tuple[Path | None, str | None]:
    expanded = raw
    if stack_root:
        expanded = expanded.replace("${STACK_ROOT}", stack_root).replace("$STACK_ROOT", stack_root)
    expanded = os.path.expandvars(expanded)
    if "$" in expanded:
        return None, f"Deferred shell variable in bootstrap path: {raw}"
    path = Path(expanded).expanduser()
    return (path if path.is_absolute() else (base / path).resolve()), None


def _bootstrap_checks(config: WorkflowConfig) -> Iterable[ResourceCheck]:
    commands = value(config, "pbs.bootstrap", required=False, default=[])
    if not isinstance(commands, list):
        return

    current_dir = config.root
    directory_stack: list[Path] = []
    stack_root = string(config, "pbs.stack_root", required=False, default=None)

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
            path, error = _resolve_bootstrap_path(tokens[1], current_dir, stack_root=stack_root)
            if error is not None or path is None:
                yield ResourceCheck(
                    f"pbs.bootstrap[{index}]",
                    Path(tokens[1]),
                    "bootstrap directory",
                    "DEFERRED_SHELL",
                    True,
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
            path, error = _resolve_bootstrap_path(tokens[1], current_dir, stack_root=stack_root)
            if error is not None or path is None:
                yield ResourceCheck(
                    f"pbs.bootstrap[{index}]",
                    Path(tokens[1]),
                    "bootstrap source file",
                    "DEFERRED_SHELL",
                    True,
                    error or "",
                )
                continue
            yield _required_file(f"pbs.bootstrap[{index}].source", path)
            continue

        if tokens[0:2] == ["module", "use"] and len(tokens) >= 3:
            path, error = _resolve_bootstrap_path(tokens[2], current_dir, stack_root=stack_root)
            if error is not None or path is None:
                yield ResourceCheck(
                    f"pbs.bootstrap[{index}]",
                    Path(tokens[2]),
                    "module directory",
                    "DEFERRED_SHELL",
                    True,
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

    # The strict forecast stages its explicitly configured source files.
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
    if reference_forecast:
        try:
            nml, xml = forecast_sources(config)
            directory = stream_list_directory(config)
            yield _required_file("reference.forecast_namelist", nml)
            yield _required_file("reference.forecast_streams", xml)
            for name in stream_lists(config):
                yield _required_file(f"reference.{name}", directory / name)
        except (ValueError, FileNotFoundError) as error:
            yield _forecast_configuration_failure(config, error)

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
        checks.append(_required_dir("software.monan_jedi_install_root", root))
        contract_path = root / "share" / "monan-jedi" / "install-manifest.json"
        checks.append(_required_file("software.runtime_contract", contract_path))

        stack_root_raw = string(config, "pbs.stack_root", required=False, default=None)
        if stack_root_raw is not None and contract_path.is_file():
            stack_root = Path(stack_root_raw).expanduser()
            checks.append(_required_dir("pbs.stack_root", stack_root))
            try:
                contract = runtime_contract(config)
            except ConfigurationError as error:
                checks.append(
                    ResourceCheck(
                        "software.runtime_contract_v2",
                        contract_path,
                        "ecosystem contract v2",
                        "INVALID",
                        False,
                        str(error),
                    )
                )
            else:
                checks.append(
                    ResourceCheck(
                        "software.runtime_contract_v2",
                        contract_path,
                        "ecosystem contract v2",
                        "OK",
                        True,
                    )
                )
                checks.append(
                    _required_file(
                        "stack.site_setup",
                        stack_root / contract.stack_site_setup,
                    )
                )
                checks.append(
                    _required_dir(
                        "stack.module_root",
                        contract.module_root(stack_root),
                    )
                )

            site_module_paths = value(
                config, "pbs.site_module_paths", required=False, default=[]
            )
            if isinstance(site_module_paths, list):
                for index, raw in enumerate(site_module_paths):
                    if isinstance(raw, str) and raw:
                        checks.append(
                            _required_dir(
                                f"pbs.site_module_paths[{index}]",
                                Path(raw).expanduser(),
                            )
                        )

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
            (_required_dir("paths.gfs_dir", layout.gfs_dir)
             if string(config, "gfs.acquisition", required=False, default="automatic") == "external"
             else _writable_dir("paths.gfs_dir", layout.gfs_dir)),
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
        for name in physics_files(config):
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

