"""Generic MPAS campaign configuration regression tests."""

from pathlib import Path

from mpaswf.config import WorkflowConfig, forecast_input_mode
from mpaswf.forecast import forecast_sources, stream_list_directory, stream_lists
from mpaswf.mesh import staging_preflight_enabled


def _config(tmp_path: Path) -> WorkflowConfig:
    return WorkflowConfig(
        tmp_path / "config.yaml",
        {
            "mesh": {"name": "x1.163842"},
            "static": {"product_template": "x1.163842.static.nc"},
            "runtime": {},
            "validation": {"require_staging_preflight": True},
        },
    )


def test_forecast_sources_are_mesh_independent(tmp_path: Path) -> None:
    config = _config(tmp_path)
    case = tmp_path / "case"
    case.mkdir()
    namelist = case / "namelist.atmosphere"
    streams = case / "streams.atmosphere"
    namelist.write_text("a = 1\n")
    streams.write_text("<streams/>")
    config.data["runtime"].update(
        forecast_namelist=str(namelist),
        forecast_streams=str(streams),
    )
    assert forecast_sources(config) == (namelist, streams)
    assert stream_list_directory(config) == case
    assert stream_lists(config) == []


def test_stream_list_discovery_uses_selected_case(tmp_path: Path) -> None:
    config = _config(tmp_path)
    streams = tmp_path / "streams.atmosphere"
    streams.write_text(
        '<streams><stream name="analysis">'
        '<file name="stream_list.atmosphere.analysis" />'
        '</stream></streams>'
    )
    config.data["runtime"].update(
        forecast_namelist=str(tmp_path / "namelist.atmosphere"),
        forecast_streams=str(streams),
    )
    assert stream_lists(config) == ["stream_list.atmosphere.analysis"]


def test_new_validation_key_overrides_legacy_key(tmp_path: Path) -> None:
    config = _config(tmp_path)
    config.data["validation"]["require_reference_preflight"] = True
    config.data["validation"]["require_staging_preflight"] = False
    assert staging_preflight_enabled(config) is False
    config.data["validation"]["require_staging_preflight"] = True
    assert staging_preflight_enabled(config) is True


def test_input_mode_is_not_controlled_by_preflight(tmp_path: Path) -> None:
    from mpaswf.forecast import _reference_enabled
    config = _config(tmp_path)
    assert forecast_input_mode(config) == 'templates'
    for strict in (True, False):
        config.data['validation']['require_staging_preflight'] = strict
        assert _reference_enabled(config) is False
    config.data['runtime']['forecast_namelist'] = 'namelist.atmosphere'
    for strict in (True, False):
        config.data['validation']['require_staging_preflight'] = strict
        assert forecast_input_mode(config) == 'sources'
        assert _reference_enabled(config) is True
