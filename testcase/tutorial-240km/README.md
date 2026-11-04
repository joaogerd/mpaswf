# Testcase: MPAS-JEDI NMC tutorial, 240 km

This directory is an **explicit, version-controlled testcase**, not a set of
library defaults. It reproduces the original 240-km MPASWF input configuration
while making it possible to copy and adapt the case for a different mesh or
time interval. The MPASWF program does **not** load this testcase unless the
user selects its YAML.

## Files

- `jaci.yaml`: site inputs, mesh/partition, runtime dependencies, PBS and
  **explicit** forecast namelist, streams, support files and physics tables.
- `mpas.yaml`: campaign dates, lead times, product names, timestep, validation.
- `templates/`: parameterized WPS/MPAS init templates; for x1.10242 and
  55 vertical levels they render the same original template values.
- `run.sh`: checks or executes this selected testcase; nothing runs on import.

## Reproduce the original campaign

From a checkout with MPASWF installed:

```bash
bash testcase/tutorial-240km/run.sh check
bash testcase/tutorial-240km/run.sh run
```

Equivalent manual steps:

```bash
CASE=testcase/tutorial-240km/jaci.yaml
mpaswf check-config --config "$CASE"
mpaswf run --phase prepare --config "$CASE"
mpaswf run --phase init --config "$CASE" --submit --wait
mpaswf run --phase forecast --config "$CASE" --submit --wait
mpaswf run --phase manifest --config "$CASE"
```

The original campaign uses 2026-06-22T00:00:00Z through
2026-06-25T00:00:00Z, 24-hour intervals, forecast leads 24 and 48 h,
the x1.10242 mesh, 55 vertical levels, 128 MPI ranks and
`runtime.config_dt: 60`. All these settings are **case data**.

The original JACI paths identify externally installed programs, GFS/MPAS
assets and archived tutorial inputs. They are **not bundled here**; the files
must exist in the user's JACI environment with suitable permissions.
`MONAN_JEDI_INSTALL_ROOT` and `STACK_ROOT` can select compatible site
installations. The testcase does not download or fabricate those assets.

At the original default work directory, the output manifest is:

```text
/p/projetos/monan_das/$USER/work/mpaswf/products/mpas-forecast-manifest.tsv
```

Pass that manifest to the matching MPAS-BMatrix testcase.

## Adapt for another resolution or period

**Copy this directory** to `testcase/<your-case>/` (or another location)
and change both YAML files. Specifically:

1. In `mpas.yaml`, set `mesh.name`, `mesh.nvertlevels`,
   `campaign.start_valid_time`, `campaign.end_valid_time`,
   `campaign.interval_hours`, `runtime.config_dt`, and
   mesh-specific `products.*` / `static.product_template`.
2. In `jaci.yaml`, update `static.source`, every `static.links`
   mesh/graph/partition path, forecast `runtime.forecast_namelist` and
   `runtime.forecast_streams`, and any case-specific physics/stream-list
   inputs; choose matching PBS ranks. Do not borrow physics settings blindly.
3. Change `paths.work_dir` and `paths.static_dir` to fresh directories.
   Update `paths.cdct_templates_dir` only if you move the templates;
   it is relative to `jaci.yaml`. Review all template settings (including
   physical/vertical-grid parameters), WPS/GFS availability and timestep
   stability.
4. Run `check` and a **single** forecast pair first, inspect the actual
   MPAS logs, geometry and output metadata, then extend the campaign.

For 15 km, 60 km or other meshes there is *no universal timestep* or
vertically appropriate namelist supplied by the software. These choices
must be scientifically validated for the selected case.

## Reproducibility limitations

The testcase preserves source configuration values and template renderings,
not a bundled numerical gold standard. Bitwise identity may depend on the
installed MPAS-JEDI version, compiler, parallel decomposition and external
GFS data. A complete JACI execution plus comparison to a frozen set of
reference NetCDF products is necessary before claiming numerical equivalence.
CI checks the config and template structure but cannot run HPC forecasts.
