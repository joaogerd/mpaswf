"""Small PBS renderer, submission, and observable scheduler waiting."""

from __future__ import annotations

import re
import shlex
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from .config import WorkflowConfig, render, resolve_path, string, value
from .files import ensure_directory
from .ui import Spinner, status


@dataclass(frozen=True)
class PBSJob:
    """Rendered PBS job metadata."""

    script: Path
    stdout: Path
    stderr: Path


def _format_elapsed(seconds: float) -> str:
    """Format elapsed PBS time as ``MM:SS`` or ``HH:MM:SS``."""
    seconds = int(max(seconds, 0.0))
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    remainder = seconds % 60
    if hours:
        return f"{hours:02d}:{minutes:02d}:{remainder:02d}"
    return f"{minutes:02d}:{remainder:02d}"


def _wait_message(job_id: str, state: str, elapsed_seconds: float, remaining_seconds: float) -> str:
    """Build the compact live PBS line used while a scheduler job is active."""
    elapsed = _format_elapsed(elapsed_seconds)
    next_check = max(0, int(remaining_seconds))
    return f"PBS job {job_id}: state {state} elapsed {elapsed} next check in {next_check}s"


def _argv(raw: object, context: Mapping[str, str], label: str) -> list[str]:
    """Render one configured command list."""
    if not isinstance(raw, list) or not raw or not all(isinstance(item, str) for item in raw):
        raise ValueError(f"{label} must be a non-empty list of strings.")
    return [render(item, context) for item in raw]


def _configured_shell_lines(raw: object, label: str) -> list[str]:
    """Validate one optional list of literal shell commands."""
    if raw is None:
        return []
    if not isinstance(raw, list) or not all(isinstance(item, str) and item.strip() for item in raw):
        raise ValueError(f"{label} must be a list of non-empty shell command strings.")
    return list(raw)


def _append_pbs_runtime_setup(lines: list[str], pbs: Mapping[str, object]) -> None:
    """Append the explicitly configured compute-node runtime bootstrap.

    ``pbs.bootstrap`` is intended for site/runtime initialization that must run
    before MPI is invoked, for example loading the exact spack-stack/JEDI module
    hierarchy on JACI. ``pbs.modules`` is retained for backwards compatibility
    with older configurations that only needed direct module-load statements.
    """
    lines.extend(_configured_shell_lines(pbs.get("bootstrap"), "pbs.bootstrap"))
    lines.extend(_configured_shell_lines(pbs.get("modules"), "pbs.modules"))
    environment = pbs.get("environment", {})
    if not isinstance(environment, Mapping):
        raise ValueError("pbs.environment must be a mapping.")
    for key, item in environment.items():
        lines.append(f"export {key}={item}")


def _append_pbs_placement(lines: list[str], pbs: Mapping[str, object]) -> None:
    """Append an optional PBS placement resource such as ``place=excl``."""
    place = pbs.get("place")
    if place is None:
        return
    if not isinstance(place, str) or not place.strip():
        raise ValueError("pbs.place must be a non-empty string when configured.")
    lines.append(f"#PBS -l place={place}")


def render_pbs_job(
    config: WorkflowConfig,
    *,
    run_dir: Path,
    job_name: str,
    executable: Path,
    walltime: str,
    context: Mapping[str, str],
    queue: str | None = None,
    script_name: str | None = None,
) -> PBSJob:
    """Render a PBS script for one MPAS executable.

    The script applies the explicitly configured runtime bootstrap, modules and
    environment before invoking MPI. The command is passed through the
    configured MPI launcher. ``script_name`` gives each rendered submission
    file a stage-specific, human-readable name instead of the former generic
    ``job.pbs``.
    """
    pbs = value(config, "pbs")
    if not isinstance(pbs, dict):
        raise ValueError("pbs must be a mapping when execution.backend is pbs.")
    selected_queue = queue or str(pbs["queue"])
    ensure_directory(run_dir / "logs")
    mpi_ranks = str(pbs.get("mpiprocs"))
    merged_context = {**context, "mpi_ranks": mpi_ranks, "executable": str(executable)}
    launcher = _argv(pbs.get("launcher"), merged_context, "pbs.launcher")
    command = [*launcher, str(executable)]
    lines = [
        "#!/bin/bash",
        f"#PBS -N {job_name}",
        f"#PBS -q {selected_queue}",
        f"#PBS -l select={pbs['select']}:ncpus={pbs['ncpus']}:mpiprocs={pbs['mpiprocs']}",
    ]
    _append_pbs_placement(lines, pbs)
    lines.extend(
        [
            f"#PBS -l walltime={walltime}",
            f"#PBS -o {run_dir / 'logs' / 'pbs.stdout.log'}",
            f"#PBS -e {run_dir / 'logs' / 'pbs.stderr.log'}",
            "set -euo pipefail",
            "umask 002",
            f"cd {shlex.quote(str(run_dir))}",
            "ulimit -s unlimited",
        ]
    )
    _append_pbs_runtime_setup(lines, pbs)
    lines.append(" ".join(shlex.quote(part) for part in command))
    filename = script_name or f"qsub_{job_name}.pbs"
    if Path(filename).name != filename:
        raise ValueError("PBS script_name must be a filename, not a path.")
    script = run_dir / filename
    script.write_text("\n".join(lines) + "\n", encoding="utf-8")
    status(f"PBS {job_name}: rendered {script}.")
    return PBSJob(script=script, stdout=run_dir / "logs" / "pbs.stdout.log", stderr=run_dir / "logs" / "pbs.stderr.log")


def submit_pbs(config: WorkflowConfig, script: Path) -> str:
    """Submit a PBS script and return the scheduler job identifier visibly."""
    qsub = value(config, "pbs.qsub_command", required=False, default=["qsub"])
    if not isinstance(qsub, list) or not all(isinstance(item, str) for item in qsub):
        raise ValueError("pbs.qsub_command must be a list of strings.")
    status(f"PBS: submitting {script.name}")
    started = time.monotonic()
    completed = subprocess.run([*qsub, str(script)], text=True, capture_output=True, check=False)
    elapsed = _format_elapsed(time.monotonic() - started)
    if completed.returncode != 0:
        status(f"PBS: submission failed for {script.name}", style="error")
        raise RuntimeError(f"qsub failed: {completed.stderr.strip()}")
    job_id = completed.stdout.strip().split()[0] if completed.stdout.strip() else ""
    if not job_id:
        status(f"PBS: submission returned no job identifier for {script.name}", style="error")
        raise RuntimeError("qsub returned success without a job identifier.")
    status(f"PBS: submitted {script.name} as {job_id} ({elapsed})", style="success")
    if completed.stderr.strip():
        status(completed.stderr.strip(), style="warning")
    return job_id


def _job_state(output: str) -> str | None:
    """Extract ``job_state`` from `qstat -f` output when available."""
    match = re.search(r"(?m)^\s*job_state\s*=\s*([A-Za-z])\s*$", output)
    return match.group(1) if match else None


def wait_pbs(config: WorkflowConfig, job_id: str) -> None:
    """Wait visibly until `qstat -f <job_id>` no longer finds the job.

    Scheduler queries remain limited to ``pbs.poll_seconds``. Between polls the
    braille spinner stays active and the same terminal row shows the latest PBS
    state, elapsed wall-clock time, and a live countdown to the next scheduler
    query, matching the MPAS-BMatrix waiting presentation.

    Output validation remains the authoritative success check after scheduler
    completion.
    """
    qstat = value(config, "pbs.qstat_command", required=False, default=["qstat", "-f"])
    if not isinstance(qstat, list) or not all(isinstance(item, str) for item in qstat):
        raise ValueError("pbs.qstat_command must be a list of strings.")
    poll_seconds = max(1, int(value(config, "pbs.poll_seconds", required=False, default=30)))
    started = time.monotonic()
    next_poll = started
    state = "checking scheduler"
    spinner = Spinner(_wait_message(job_id, state, 0.0, 0.0)).start()

    while True:
        now = time.monotonic()
        if now >= next_poll:
            result = subprocess.run([*qstat, job_id], text=True, capture_output=True, check=False)
            now = time.monotonic()
            if result.returncode != 0:
                spinner.succeed(f"PBS job {job_id}: no longer listed; validating outputs")
                return
            state = _job_state(result.stdout) or "unknown"
            next_poll = now + poll_seconds

        now = time.monotonic()
        remaining = next_poll - now
        spinner.update(_wait_message(job_id, state, now - started, remaining))
        time.sleep(min(0.1, max(0.01, remaining)))


def run_pbs_smoke(config: WorkflowConfig) -> Path:
    """Submit and validate a real one-rank PBS smoke job.

    This is intentionally not a mocked/unit-test path. It writes a small PBS
    script under ``<work_dir>/.mpaswf/pbs-smoke``, submits it with the configured
    ``qsub``, monitors it with the configured ``qstat`` helper, applies the same
    runtime bootstrap used by MPAS jobs, launches one MPI rank running
    ``/bin/hostname``, and requires a sentinel file written by the compute node
    before reporting success.
    """
    if string(config, "execution.backend") != "pbs":
        raise ValueError("pbs-smoke requires execution.backend: pbs.")

    pbs = value(config, "pbs")
    if not isinstance(pbs, dict):
        raise ValueError("pbs must be a mapping when execution.backend is pbs.")

    work_dir = resolve_path(config, string(config, "paths.work_dir") or "")
    run_dir = work_dir / ".mpaswf" / "pbs-smoke"
    logs_dir = run_dir / "logs"
    ensure_directory(logs_dir)

    sentinel = run_dir / "pbs-smoke.ok"
    sentinel.unlink(missing_ok=True)
    script = run_dir / "qsub_pbs_smoke.pbs"
    stdout = logs_dir / "pbs-smoke.stdout.log"
    stderr = logs_dir / "pbs-smoke.stderr.log"

    queue = string(
        config,
        "pbs.queue_smoke",
        required=False,
        default=string(config, "pbs.queue_static", required=False, default=string(config, "pbs.queue")),
    )
    walltime = string(config, "pbs.walltime_smoke", required=False, default="00:02:00") or "00:02:00"
    launcher = _argv(
        pbs.get("launcher"),
        {"mpi_ranks": "1", "executable": "/bin/hostname"},
        "pbs.launcher",
    )
    command = [*launcher, "/bin/hostname"]

    lines = [
        "#!/bin/bash",
        "#PBS -N mpaswf_smoke",
        f"#PBS -q {queue}",
        "#PBS -l select=1:ncpus=1:mpiprocs=1",
    ]
    _append_pbs_placement(lines, pbs)
    lines.extend(
        [
            f"#PBS -l walltime={walltime}",
            f"#PBS -o {stdout}",
            f"#PBS -e {stderr}",
            "set -euo pipefail",
            "umask 002",
            f"cd {shlex.quote(str(run_dir))}",
            "ulimit -s unlimited",
        ]
    )
    _append_pbs_runtime_setup(lines, pbs)
    lines.extend(
        [
            'echo "MPASWF PBS smoke: compute node $(hostname)"',
            'echo "MPASWF PBS smoke: mpiexec=$(command -v mpiexec || true)"',
            "module list 2>&1 || true",
            " ".join(shlex.quote(part) for part in command),
            f"printf '%s\\n' 'MPASWF PBS smoke OK' > {shlex.quote(str(sentinel))}",
        ]
    )
    script.write_text("\n".join(lines) + "\n", encoding="utf-8")
    status(f"PBS smoke: rendered {script}.")

    job_id = submit_pbs(config, script)
    wait_pbs(config, job_id)
    if not sentinel.is_file():
        raise RuntimeError(
            "PBS smoke job left the scheduler without producing its success sentinel. "
            f"Inspect {stdout} and {stderr}."
        )

    status(f"PBS smoke: compute-node execution validated by {sentinel}.", style="success")
    return sentinel
