"""Tests for MPASWF PBS terminal status and script rendering."""

from __future__ import annotations

from pathlib import Path

from mpaswf.config import WorkflowConfig
from mpaswf.pbs import _format_elapsed, _wait_message, render_pbs_job


def test_format_elapsed_matches_bmatrix_clock_style() -> None:
    """PBS elapsed time uses the same compact clock form as MPAS-BMatrix."""
    assert _format_elapsed(239.9) == "03:59"
    assert _format_elapsed(3661.8) == "01:01:01"


def test_wait_message_matches_bmatrix_live_status() -> None:
    """The live wait line exposes state, elapsed time, and next-check countdown."""
    assert _wait_message("328134.pbs-ha", "R", 239.9, 0.8) == (
        "PBS job 328134.pbs-ha: state R elapsed 03:59 next check in 0s"
    )


def test_render_pbs_job_uses_explicit_stage_filename(tmp_path: Path) -> None:
    """Rendered PBS files keep the informative stage-specific submission name."""
    bootstrap = [
        "module --force purge 2>/dev/null || module purge",
        "module use /stack/modules",
        "module load jedi-mpas-env/1.0.0",
    ]
    config = WorkflowConfig(
        path=tmp_path / "config.yaml",
        data={
            "pbs": {
                "queue": "pesqmini",
                "select": 1,
                "ncpus": 128,
                "mpiprocs": 128,
                "place": "excl",
                "launcher": ["mpiexec", "-n", "{mpi_ranks}"],
                "bootstrap": bootstrap,
                "modules": [],
                "environment": {"OMP_NUM_THREADS": "1"},
            }
        },
    )
    executable = tmp_path / "mpas_init_atmosphere"
    run_dir = tmp_path / "init" / "2018041500"

    job = render_pbs_job(
        config,
        run_dir=run_dir,
        job_name="mpasinit_2018041500",
        executable=executable,
        walltime="00:30:00",
        context={},
        script_name="qsub_init_2018041500.pbs",
    )

    assert job.script.name == "qsub_init_2018041500.pbs"
    assert job.script.parent == run_dir
    rendered = job.script.read_text(encoding="utf-8")
    assert "#PBS -N mpasinit_2018041500" in rendered
    assert "#PBS -l place=excl" in rendered
    assert "umask 002" in rendered
    assert "module load jedi-mpas-env/1.0.0" in rendered
    assert "export OMP_NUM_THREADS=1" in rendered
    assert "mpiexec -n 128" in rendered
    assert rendered.index(bootstrap[0]) < rendered.index("mpiexec -n 128")
    assert rendered.index(bootstrap[-1]) < rendered.index("mpiexec -n 128")
