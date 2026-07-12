"""Command-line interface for the small MPAS-only workflow.

This module exposes the ``mpaswf`` console entry point and dispatches the four
public workflow phases without embedding phase-specific implementation logic.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from .config import load_config
from .workflow import run_forecast, run_init, run_manifest, run_prepare
from .ui import status


def build_parser() -> argparse.ArgumentParser:
    """Build the public ``mpaswf`` argument parser.

    Returns
    -------
    argparse.ArgumentParser
        Parser containing the ``run`` command and its phase, configuration,
        submission, waiting, and force options.

    Notes
    -----
    Argument compatibility between phases is checked by :func:`main` after
    parsing so that the public command structure remains compact.
    """
    parser = argparse.ArgumentParser(
        prog="mpaswf",
        description="Small MPAS-only workflow derived from one CD-CT reference case.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="Run one fixed workflow phase.")
    run.add_argument("--phase", required=True, choices=("prepare", "init", "forecast", "manifest"))
    run.add_argument("--config", required=True, type=Path)
    run.add_argument("--submit", action="store_true", help="Submit PBS jobs for init or forecast phases.")
    run.add_argument("--wait", action="store_true", help="Wait for submitted PBS jobs and validate outputs.")
    run.add_argument("--force", action="store_true", help="Ignore reusable valid outputs and rerun the selected phase.")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the ``mpaswf`` command-line interface.

    Parameters
    ----------
    argv : list of str, optional
        Command-line arguments excluding the executable name. When omitted,
        :mod:`argparse` reads the process arguments from ``sys.argv``.

    Returns
    -------
    int
        Process status code. Successful execution returns ``0``.

    Raises
    ------
    SystemExit
        Raised by argument parsing or when phase-specific command-line options
        are combined in an unsupported way.

    Notes
    -----
    Exceptions raised by configuration loading or workflow execution are not
    intercepted and therefore propagate to the command-line caller.
    """
    args = build_parser().parse_args(argv)
    status(f"MPASWF {args.phase} phase: loading {args.config}.")
    config = load_config(args.config)
    if args.phase == "prepare":
        if args.submit or args.wait:
            raise SystemExit("--submit and --wait are only valid for init and forecast phases.")
        path = run_prepare(config, force=args.force)
    elif args.phase == "init":
        path = run_init(config, submit=args.submit, wait=args.wait, force=args.force)
    elif args.phase == "forecast":
        path = run_forecast(config, submit=args.submit, wait=args.wait, force=args.force)
    else:
        if args.submit or args.wait or args.force:
            raise SystemExit("manifest does not accept --submit, --wait, or --force.")
        path = run_manifest(config)
    status(f"MPASWF {args.phase} phase: complete. Record: {path}")
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
