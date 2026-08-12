"""Command-line interface for the small MPAS-only workflow."""

from __future__ import annotations

import argparse
from pathlib import Path

from .config import load_config
from .pbs import run_pbs_smoke
from .workflow import run_forecast, run_init, run_manifest, run_prepare
from .ui import status


def build_parser() -> argparse.ArgumentParser:
    """Build the public `mpaswf` argument parser."""
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

    smoke = commands.add_parser(
        "pbs-smoke",
        help="Submit a real one-rank PBS job and validate compute-node execution.",
    )
    smoke.add_argument("--config", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the `mpaswf` command-line interface.

    Parameters
    ----------
    argv : list of str, optional
        Command-line arguments excluding the executable name.

    Returns
    -------
    int
        Process status code.
    """
    args = build_parser().parse_args(argv)

    if args.command == "pbs-smoke":
        status(f"MPASWF PBS smoke: loading {args.config}.")
        config = load_config(args.config)
        path = run_pbs_smoke(config)
        status(f"MPASWF PBS smoke: complete. Sentinel: {path}")
        print(path)
        return 0

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
