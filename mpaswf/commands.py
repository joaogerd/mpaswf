"""Execute external commands with persistent logs and terminal progress.

The helpers in this module run already-tokenized commands without shell
interpretation. Standard output and standard error are retained in separate
UTF-8 log files while the terminal receives concise progress information.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping

from .files import ensure_directory
from .ui import Spinner, status


@dataclass(frozen=True)
class CommandResult:
    """Record the result and log locations of one external process.

    Parameters
    ----------
    argv : tuple of str
        Fully tokenized command passed to :func:`subprocess.run`.
    cwd : pathlib.Path
        Working directory used by the child process.
    returncode : int
        Exit status returned by the child process.
    stdout_log : pathlib.Path
        File containing the captured standard output.
    stderr_log : pathlib.Path
        File containing the captured standard error.
    """

    argv: tuple[str, ...]
    cwd: Path
    returncode: int
    stdout_log: Path
    stderr_log: Path


def run_command(
    argv: Iterable[str],
    *,
    cwd: Path,
    logs_dir: Path,
    name: str,
    environment: Mapping[str, str] | None = None,
    label: str | None = None,
) -> CommandResult:
    """Run a command without shell evaluation or silent waiting.

    A braille spinner is shown for terminal users while stdout and stderr are
    captured into persistent log files. This deliberately avoids streaming a
    noisy external program directly into the workflow console.

    Parameters
    ----------
    argv : iterable of str
        Fully tokenized command. Shell quoting and expansion are not
        interpreted.
    cwd : pathlib.Path
        Working directory passed to the child process. It is created when
        absent.
    logs_dir : pathlib.Path
        Directory receiving ``<name>.stdout.log`` and
        ``<name>.stderr.log``. It is created when absent.
    name : str
        Stable prefix used for both log-file names.
    environment : mapping of str to str, optional
        Complete environment mapping passed to the child process. When
        omitted, the current process environment is inherited.
    label : str, optional
        Human-readable activity shown in terminal progress output. By default,
        ``name`` is displayed with underscores replaced by spaces.

    Returns
    -------
    CommandResult
        Process metadata and paths to the captured logs.

    Raises
    ------
    ValueError
        Raised when ``argv`` contains no command token.
    OSError
        Propagated when the child process cannot be started.
    RuntimeError
        Raised after logs are written when the external process returns a
        nonzero status.

    Notes
    -----
    When ``environment`` is provided, it replaces rather than augments the
    inherited process environment because it is passed directly as ``env`` to
    :func:`subprocess.run`.
    """
    tokens = tuple(str(item) for item in argv)
    if not tokens:
        raise ValueError("A command cannot be empty.")
    ensure_directory(cwd)
    ensure_directory(logs_dir)
    stdout_log = logs_dir / f"{name}.stdout.log"
    stderr_log = logs_dir / f"{name}.stderr.log"
    activity = label or name.replace("_", " ")
    spinner = Spinner(f"{activity}: running").start()
    try:
        completed = subprocess.run(
            tokens,
            cwd=cwd,
            text=True,
            capture_output=True,
            check=False,
            env=dict(environment) if environment is not None else None,
        )
    except Exception:
        spinner.fail(f"{activity}: could not start")
        raise
    stdout_log.write_text(completed.stdout, encoding="utf-8")
    stderr_log.write_text(completed.stderr, encoding="utf-8")
    result = CommandResult(tokens, cwd, completed.returncode, stdout_log, stderr_log)
    if completed.returncode != 0:
        spinner.fail(f"{activity}: failed; inspect {stderr_log}")
        raise RuntimeError(
            f"Command failed with return code {completed.returncode}: {' '.join(tokens)}\n"
            f"stdout: {stdout_log}\nstderr: {stderr_log}"
        )
    spinner.succeed(f"{activity}: completed")
    status(f"Logs: {stdout_log} and {stderr_log}")
    return result
