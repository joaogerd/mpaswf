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
    spinner = Spinner(f"PBS: submitting {script.name}").start()
    completed = subprocess.run([*qsub, str(script)], text=True, capture_output=True, check=False)
    if completed.returncode != 0:
        spinner.fail(f"PBS: submission failed for {script.name}")
        raise RuntimeError(f"qsub failed: {completed.stderr.strip()}")
    job_id = completed.stdout.strip()
    if not job_id:
        spinner.fail(f"PBS: submission returned no job identifier for {script.name}")
        raise RuntimeError("qsub returned success without a job identifier.")
    spinner.succeed(f"PBS: submitted {script.name} as {job_id}")
    return job_id


def _job_state(output: str) -> str | None:
    """Extract ``job_state`` from `qstat -f` output when available."""
    match = re.search(r"(?m)^\s*job_state\s*=\s*([A-Za-z])\s*$", output)
    return match.group(1) if match else None


def wait_pbs(config: WorkflowConfig, job_id: str) -> None:
    """Wait visibly until `qstat -f <job_id>` no longer finds the job.

    The spinner rotates between scheduler polls and updates its message with the
    latest PBS state (for example ``Q`` or ``R``). Output validation remains
    the authoritative success check after scheduler completion.
    """
    qstat = value(config, "pbs.qstat_command", required=False, default=["qstat", "-f"])
    if not isinstance(qstat, list) or not all(isinstance(item, str) for item in qstat):
        raise ValueError("pbs.qstat_command must be a list of strings.")
    poll_seconds = int(value(config, "pbs.poll_seconds", required=False, default=30))
    spinner = Spinner(f"PBS job {job_id}: waiting for scheduler completion").start()
    while True:
        result = subprocess.run([*qstat, job_id], text=True, capture_output=True, check=False)
        if result.returncode != 0:
            spinner.succeed(f"PBS job {job_id}: no longer listed; validating outputs")
            return
        state = _job_state(result.stdout) or "unknown"
        spinner.update(f"PBS job {job_id}: state {state}; checking again in {poll_seconds}s")
        time.sleep(poll_seconds)
