# MPASWF case-independence audit (2026-11-04)

## Boundary and acceptance rules

The MPASWF package is a generic producer of NMC forecast pairs. Its code
must not infer the mesh, physical model settings, cycle dates, input archives,
or PBS rank count from the historic tutorial. A scientifically reproducible
example belongs under `testcase/` and must be selected explicitly by
`--config`.

The audit covers configuration loading, mesh identity, GFS/WPS preparation,
static interpolation/reuse, MPAS initial state, forecast setup, PBS staging,
NMC pair enumeration, manifest output, resource preflight and user messages.
Python tests run on CI; real JACI jobs are outside CI.

## Findings and actions

| Area | Observed coupling / risk | Resolution / policy |
| --- | --- | --- |
| Config entrypoint | Historic `configs/jaci-x1.10242.yaml` mixed tutorial paths with the only maintained example | Complete copy under `testcase/tutorial-240km/`, including site, campaign and local templates. No implicit loading. Old config retained for compatibility. |
| Forecast source files | Original 240-km namelist and streams fallback under `static.tutorial_physics_files` | Historical compatibility remains guarded to that old mesh. Testcase explicitly sets both `runtime.forecast_*` fields. New campaigns must supply their own files. |
| Stream lists | Four tutorial stream lists were a default | Generic cases use explicit `runtime.stream_lists` or XML discovery. The selected streams-file directory is the default support location. |
| MPAS physics tables | Tutorial-specific table list was a default | Generic cases do not inherit that requirement; stage selection comes from the installed MPAS share and explicit `runtime.physics_files` when used. Testcase pins the original table list. |
| Static and init templates | Tutorial init contained literal `x1.10242` and 55 levels | Testcase templates use `{partition_prefix}`, `{nvertlevels}`, `{static_filename}` and `{init_filename}`. CI checks original rendered text is preserved. |
| Forecast periods | Old start/end times embedded in science YAML | `campaign.start_valid_time`, `end_valid_time`, `interval_hours` remain editable and drive the pair enumeration. CI changes mesh and time window without code modifications. |
| Mesh and MPI | Risk of staged 240-km graph/partition under other resolutions | Selected mesh, graph, partition and MPI ranks validated; strict staging records mesh identity to prevent cross-campaign reuse. |
| User errors | Internal `runtime.forecast_sources` appeared as if a YAML key | Diagnostics identify actual user-editable fields; default `check-config` prints only failures with fixes. |
| Output contract | NMC f024/f048 manifest uses fixed names | **Intentional contract**: `monan-nmc-forecast-pairs-v1` supports only 24/48 h. Period and mesh can vary. Generalized lead pairs require a versioned producer/consumer schema change in *both* repositories. |

## Tutorial reproducibility

`testcase/tutorial-240km/jaci.yaml` references the same original external
JACI inputs, time window, 128 MPI ranks, 55 vertical levels, runtime timestep
and forecast stream file names. The WPS and initial-state templates produce
the same text after substituting the original mesh/time placeholders.

`bash testcase/tutorial-240km/run.sh check` checks the selected case.
`bash testcase/tutorial-240km/run.sh run` executes preparation,
initialization, f024/f048 forecasts and manifest generation on an available
JACI system.

The actual NetCDF files, installed MPAS-JEDI release, GFS inputs and
reference numerical outputs are not part of this repository. Consequently:
**config/template equivalence is verified in CI; numerical equivalence
to the old tutorial is not yet verified here.** End-to-end validation
requires frozen inputs/software, a full JACI run, matching output geometry,
and comparison of NetCDF fields with declared tolerances.

## Adaptation checklist

- Copy the testcase folder, then change the mesh ID, levels, topology,
  invariant/static inputs and partition (not just the filename).
- Review physical/vertical grid parameters, timestep, GFS input, namelist,
  streams and stream lists; no automatically inferred physics is promised.
- Select a new work and static directory for each experiment.
- Update valid-time window and interval independently of model resolution.
- Run one f024/f048 pair first and inspect the MPAS logs before scaling.
- Feed the resulting producer manifest into the matching BMatrix case.
