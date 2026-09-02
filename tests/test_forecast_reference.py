from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from mpaswf.config import WorkflowConfig
from mpaswf.forecast import ForecastRun, _forecast_walltime, _render_reference_forecast
from mpaswf.model import ForecastRequest


def _config() -> WorkflowConfig:
    return WorkflowConfig(
        path=Path("/tmp/configs/reference.yaml"),
        data={
            "runtime": {"config_dt": 60, "output_interval": "24:00:00"},
            "pbs": {
                "walltime_forecast": "03:00:00",
                "walltime_forecast_f024": "01:00:00",
                "walltime_forecast_f048": "02:00:00",
            },
        },
    )


def _namelist_template() -> str:
    keys = {
        "config_dt": "500.0",
        "config_start_time": "'2000-01-01_00:00:00'",
        "config_run_duration": "'1_00:00:00'",
        "config_do_restart": ".true.",
        "config_block_decomp_file_prefix": "'x1.10242.graph.info.part.'",
        "config_sst_update": ".true.",
        "config_sstdiurn_update": ".true.",
        "config_deepsoiltemp_update": ".true.",
        "config_do_DAcycling": ".false.",
        "config_jedi_da": ".false.",
    }
    return "\n".join(f"    {key} = {value}," for key, value in keys.items()) + "\n"


def _streams_template() -> str:
    return """<streams>
<immutable_stream name="input" type="input" filename_template="old.init.nc" input_interval="initial_only" />
<stream name="output" type="output" filename_template="history.$Y-$M-$D_$h.$m.$s.nc" output_interval="6:00:00" />
<stream name="diagnostics" type="output" filename_template="diag.$Y-$M-$D_$h.$m.$s.nc" output_interval="3:00:00" />
</streams>
"""


def test_reference_forecast_renders_nmc_contract(tmp_path: Path) -> None:
    config = _config()
    init_time = datetime(2026, 6, 20, tzinfo=timezone.utc)
    valid_time = datetime(2026, 6, 22, tzinfo=timezone.utc)
    request = ForecastRequest(init_time=init_time, valid_time=valid_time, lead_hours=48)
    run = ForecastRun(
        request=request,
        run_dir=tmp_path,
        restart_path=tmp_path / "restart.2026-06-22_00.00.00.nc",
        da_state_path=tmp_path / "mpasout.2026-06-22_00.00.00.nc",
        manifest_path=tmp_path / ".mpaswf/forecast.json",
    )
    namelist_source = tmp_path / "namelist.atmosphere_240km"
    streams_source = tmp_path / "streams.atmosphere_240km"
    namelist_source.write_text(_namelist_template(), encoding="utf-8")
    streams_source.write_text(_streams_template(), encoding="utf-8")

    _render_reference_forecast(config, run, namelist_source, streams_source)

    namelist = (tmp_path / "namelist.atmosphere").read_text(encoding="utf-8")
    streams = (tmp_path / "streams.atmosphere").read_text(encoding="utf-8")
    for token in (
        "config_dt = 60.0",
        "config_start_time = '2026-06-20_00:00:00'",
        "config_run_duration = '2_00:00:00'",
        "config_do_restart = .false.",
        "config_do_DAcycling = .true.",
        "config_jedi_da = .true.",
    ):
        assert token in namelist

    for token in (
        'filename_template="x1.10242.invariant.nc"',
        'filename_template="init.nc"',
        'name="da_state"',
        'filename_template="mpasout.$Y-$M-$D_$h.$m.$s.nc"',
        'packages="jedi_da"',
        'output_interval="24:00:00"',
        'name="restart"',
        'filename_template="restart.$Y-$M-$D_$h.$m.$s.nc"',
    ):
        assert token in streams


def test_reference_forecast_uses_lead_specific_walltime() -> None:
    config = _config()
    assert _forecast_walltime(config, 24) == "01:00:00"
    assert _forecast_walltime(config, 48) == "02:00:00"
