"""Tests for MPASWF PBS terminal status and script rendering."""

from __future__ import annotations

import json
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
    install_root = tmp_path / "install"
    manifest = install_root / "share" / "monan-jedi" / "install-manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "ecosystem_contract_version": 2,
                "contract": "monan-jedi-runtime-v2",
                "public_anchors": ["MONAN_JEDI_INSTALL_ROOT", "STACK_ROOT"],
                "stack": {
                    "env_name": "jaci-test",
                    "env_module": "cray-mpich/test/jedi-mpas-env/2.0.0",
                    "site_setup": "configs/sites/test/setup.sh",
                    "module_root_template": "envs/{env_name}/modules",
                },
                "layout": {},
                "capabilities": {"mpas": True, "mpas_jedi": True},
            }
        ),
        encoding="utf-8",
    )
    config = WorkflowConfig(
        path=tmp_path / "config.yaml",
        data={
            "software": {"monan_jedi_install_root": str(install_root)},
            "pbs": {
                "queue": "pesqmini",
                "select": 1,
                "ncpus": 128,
                "mpiprocs": 128,
                "place": "excl",
                "launcher": ["mpiexec", "-n", "{mpi_ranks}"],
                "stack_root": "/runtime/spack-stack",
                "bootstrap": [],
                "modules": [],
                "environment": {"OMP_NUM_THREADS": "1"},
            },
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
    assert "module load cray-mpich/test/jedi-mpas-env/2.0.0" in rendered
    assert "export STACK_ROOT=/runtime/spack-stack" in rendered
    assert rendered.index("export STACK_ROOT=/runtime/spack-stack") < rendered.index("module purge")
    assert "source configs/sites/test/setup.sh" in rendered
    assert "module use /runtime/spack-stack/envs/jaci-test/modules" in rendered
    assert "set +u" in rendered
    assert "export OMP_NUM_THREADS=1" in rendered
    assert "mpiexec -n 128" in rendered
    assert rendered.index("module load cray-mpich/test/jedi-mpas-env/2.0.0") < rendered.index("mpiexec -n 128")
