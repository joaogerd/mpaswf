"""Small PBS renderer, submission, and observable scheduler waiting."""

from __future__ import annotations

import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from .config import WorkflowConfig, render, string, value
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


def render_pbs_job(
    config: WorkflowConfig,
    *,
    run_dir: Path,
    job_name: str,
    executable: Path,
    walltime: str,
    context: Mapping[str, str],
    queue: str | None = None,
) -> PBSJob:
    """Render a PBS script for one MPAS executable.

    The script loads only explicitly configured modules and exports only the
    configured environment variables. The command is passed through the
    configured MPI launcher.
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
        f"#PBS -l walltime={walltime}",
        f"#PBS -o {run_dir / 'logs' / 'pbs.stdout.log'}",
        f"#PBS -e {run_dir / 'logs' / 'pbs.stderr.log'}",
        "set -euo pipefail",
        f"cd {run_dir}",
        "ulimit -s unlimited",
    ]
    for module_line in pbs.get("modules", []):
        lines.append(str(module_line))
    for key, item in pbs.get("environment", {}).items():
        lines.append(f"export {key}={item}")
    lines.append(" ".join(command))
    script = run_dir / "job.pbs"
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
