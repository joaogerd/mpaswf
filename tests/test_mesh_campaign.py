from pathlib import Path

import pytest

from mpaswf.config import WorkflowConfig
from mpaswf.forecast import (
    ForecastRun,
    _render_reference_forecast,
    _validate_reference_setup as validate_forecast,
)
from mpaswf.init import InitRun, _validate_reference_setup as validate_init
from mpaswf.model import ForecastRequest, parse_time
from mpaswf.pbs import render_pbs_job
from test_forecast_reference import _namelist_template, _streams_template


def config_for(tmp_path):
    return WorkflowConfig(
        tmp_path / "config.yaml",
        {
            "mesh": {"name": "x1.2621442", "nvertlevels": 100},
            "static": {"product_template": "x1.2621442.static.nc"},
            "runtime": {
                "config_dt": 90,
                "output_interval": "24:00:00",
                "stream_lists": [],
            },
            "validation": {"require_reference_preflight": True},
            "pbs": {
                "select": 4,
                "mpiprocs": 120,
                "ncpus": 120,
                "queue": "test",
                "place": "excl",
                "launcher": ["mpiexec", "-n", "{mpi_ranks}"],
            },
        },
    )


def test_init_preflight_accepts_15km_480_ranks_and_100_levels(tmp_path):
    config = config_for(tmp_path)
    time = parse_time("2026-06-20T00:00:00Z")
    run = InitRun(time, tmp_path, tmp_path / "state.nc", tmp_path / "init.json")
    for name in ("GFS", "x1.2621442.static.nc", "x1.2621442.graph.info.part.480"):
        (tmp_path / name).write_text("data")
    (tmp_path / "namelist.init_atmosphere").write_text("""
config_init_case = 7
config_start_time = '2026-06-20_00:00:00'
config_stop_time = '2026-06-20_00:00:00'
config_nvertlevels = 100
config_met_prefix = 'GFS'
config_sfc_prefix = 'GFS'
config_static_interp = .false.
config_native_gwd_static = .false.
config_native_gwd_gsl_static = .false.
config_vertical_grid = .true.
config_met_interp = .true.
config_block_decomp_file_prefix = 'x1.2621442.graph.info.part.'
""")
    (tmp_path / "streams.init_atmosphere").write_text(
        '<streams><stream filename_template="x1.2621442.static.nc" />'
        '<stream filename_template="state.nc" clobber_mode="overwrite" /></streams>'
    )
    validate_init(config, run, tmp_path / "GFS")


def test_forecast_15km_render_and_preflight(tmp_path):
    config = config_for(tmp_path)
    request = ForecastRequest(
        parse_time("2026-06-20T00:00:00Z"), parse_time("2026-06-22T00:00:00Z"), 48
    )
    run = ForecastRun(
        request,
        tmp_path,
        tmp_path / "restart.nc",
        tmp_path / "mpasout.nc",
        tmp_path / "forecast.json",
    )
    nml, xml = tmp_path / "source.nml", tmp_path / "source.xml"
    nml.write_text(_namelist_template())
    xml.write_text(_streams_template())
    _render_reference_forecast(config, run, nml, xml)
    assert "x1.10242" not in (tmp_path / "namelist.atmosphere").read_text()
    assert "x1.2621442.invariant.nc" in (tmp_path / "streams.atmosphere").read_text()
    from mpaswf.forecast import REFERENCE_PHYSICS_FILES

    for name in (
        "init.nc",
        "x1.2621442.invariant.nc",
        "x1.2621442.grid.nc",
        "x1.2621442.graph.info",
        "x1.2621442.graph.info.part.480",
        *REFERENCE_PHYSICS_FILES,
    ):
        (tmp_path / name).write_text("data")
    validate_forecast(config, run)
    (tmp_path / "x1.2621442.graph.info.part.480").unlink()
    with pytest.raises(FileNotFoundError, match="part.480"):
        validate_forecast(config, run)


def test_pbs_launches_total_ranks_across_nodes(tmp_path):
    job = render_pbs_job(
        config_for(tmp_path),
        run_dir=tmp_path,
        job_name="test",
        executable=Path("/bin/true"),
        walltime="01:00:00",
        context={},
    )
    assert "mpiexec -n 480" in job.script.read_text()


def test_new_mesh_cannot_silently_use_240km_tutorial_sources(tmp_path):
    from mpaswf.forecast import forecast_sources

    config = config_for(tmp_path)
    config.data["static"]["tutorial_physics_files"] = str(tmp_path)
    with pytest.raises(ValueError, match="runtime.forecast_namelist"):
        forecast_sources(config)


def test_explicit_forecast_sources_and_stream_lists_pass_preflight(tmp_path):
    from mpaswf.preflight import _static_checks
    from mpaswf.layout import Layout

    config = config_for(tmp_path)
    config.data["static"]["reference_time"] = "2026-06-20T00:00:00Z"
    nml, xml = tmp_path / "f.nml", tmp_path / "f.xml"
    nml.touch()
    xml.touch()
    config.data["runtime"].update(forecast_namelist=str(nml), forecast_streams=str(xml))
    layout = Layout(tmp_path / "work", tmp_path / "static", tmp_path / "gfs", tmp_path)
    checks = list(_static_checks(config, layout))
    assert checks and all(c.ok for c in checks)


def test_prepare_init_and_forecast_use_only_selected_mesh(tmp_path):
    from mpaswf.layout import Layout
    from mpaswf.init import prepare_init
    from mpaswf.forecast import prepare_forecast
    from mpaswf.static import prepare_static
    from mpaswf.wps import wps_output_path
    from test_preflight import _config

    config = _config(tmp_path)
    config.data.update(config_for(tmp_path).data)
    config.data["paths"] = {
        "work_dir": str(tmp_path / "work15"),
        "static_dir": str(tmp_path / "static15"),
        "gfs_dir": str(tmp_path / "gfs"),
        "cdct_templates_dir": str(Path(__file__).parents[1] / "templates/invariant"),
    }
    config.data["templates"] = {
        "init_namelist": "namelist.init_atmosphere.in",
        "init_streams": "streams.init_atmosphere.in",
    }
    config.data["wps"] = {"output_template": "GFS:{init_date_yyyy_mm_dd_hh}"}
    config.data["products"] = {
        "init_state_template": "x1.2621442.init.{init_date_yyyy_mm_dd_hh_mm_ss}.nc",
        "restart_template": "restart.{valid_date_yyyy_mm_dd_hh_mm_ss}.nc",
        "da_state_template": "mpasout.{valid_date_yyyy_mm_dd_hh_mm_ss}.nc",
    }
    config.data["static"]["reference_time"] = "2026-06-20T00:00:00Z"
    source = tmp_path / "invariant15.nc"
    source.write_text("data")
    config.data["static"]["source"] = str(source)
    links = []
    for name in (
        "x1.2621442.grid.nc",
        "x1.2621442.graph.info",
        "x1.2621442.graph.info.part.480",
    ):
        path = tmp_path / name
        path.write_text("data")
        links.append({"source": str(path), "target": name})
    config.data["static"]["links"] = links
    nml, xml = tmp_path / "forecast.nml", tmp_path / "forecast.xml"
    nml.write_text(_namelist_template())
    xml.write_text(_streams_template())
    config.data["runtime"].update(forecast_namelist=str(nml), forecast_streams=str(xml))
    layout = Layout.from_config(config)
    time = parse_time("2026-06-20T00:00:00Z")
    wps = wps_output_path(config, layout, time)
    wps.parent.mkdir(parents=True)
    wps.write_text("data")
    prepare_static(config, layout)
    init = prepare_init(config, layout, time)
    init.state_path.write_text("data")
    request = ForecastRequest(time, parse_time("2026-06-22T00:00:00Z"), 48)
    forecast = prepare_forecast(config, layout, request)
    for directory in (init.run_dir, forecast.run_dir):
        assert not list(directory.glob("x1.10242*"))
    assert (forecast.run_dir / "x1.2621442.invariant.nc").resolve() == source


def test_campaign_workdir_rejects_a_different_mesh_and_unidentified_outputs(tmp_path):
    from mpaswf.mesh import ensure_campaign_identity

    config = config_for(tmp_path)
    work = tmp_path / "work"
    ensure_campaign_identity(config, work)
    config.data["mesh"]["name"] = "another-mesh"
    with pytest.raises(ValueError, match="different mesh"):
        ensure_campaign_identity(config, work)
    legacy = tmp_path / "legacy"
    (legacy / "forecast").mkdir(parents=True)
    (legacy / "forecast" / "old-state.nc").touch()
    with pytest.raises(ValueError, match="unidentified"):
        ensure_campaign_identity(config, legacy)
