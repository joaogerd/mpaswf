# Second mesh/resolution independence audit — 2026-11-05

This is a **source-level audit**, backed by unit/CI tests on the current main
and the second-audit branch. It is not a claim of full numerical reproducibility
on JACI. Follow the original [case-independence audit](case-independence-audit.md)
and the [240-km testcase](../testcase/tutorial-240km/README.md).

## Reviewed components

- `config.py`, `mesh.py`, `assets.py`, `static.py`, `init.py`,
  `forecast.py`, `workflow.py`, `model.py`, `layout.py`, `preflight.py`,
  `pbs.py`, `gfs.py`, `wps.py`, tests, generic init templates and testcase.
- Looked for literals referring to `x1.10242`, `_240km`, `55`, `64`,
  `128`, f024/f048, model time steps, PBS decomposition, fixed mesh
  filename patterns and cross-experiment output reuse.

## Confirmed fixes in this audit

| Risk | Correction |
| --- | --- |
| Mesh files had to be named `<mesh>.grid.nc`, `<mesh>.graph.info` and `<mesh>.graph.info.part.<ranks>` | Optional `mesh.grid_filename`, `mesh.graph_filename`, and `mesh.partition_prefix` now control the *staged filenames*. Defaults preserve the old naming scheme. These names must match `static.links[].target`. Paths are not permitted in these keys. |
| Work directories were protected only by mesh.name and nvertlevels | New `.mpaswf/mesh.json` includes a SHA-256 fingerprint of model/runtime, mesh, static, GFS/WPS, template/product and decomposition configuration. Reuse after changing timestep/physics inputs is rejected. Date-window extensions are allowed. Old records remain compatible but warn when scientific identity cannot be proven. |
| A strict local case required PBS resource settings to calculate the partition name | The direct-execution local backend explicitly uses one rank; use PBS for a parallel model run. Local requests for more ranks fail clearly. |
| Operational messages could report a missing file without explaining mesh-specific conventions | Users can now configure the exact filenames and preflight checks those selected names rather than assuming a fixed naming convention. |

## Intentional contracts, not tutorial leaks

- Current NMC producer protocol `monan-nmc-forecast-pairs-v1` represents
  exactly f024/f048. `campaign.start_valid_time`, `end_valid_time` and
  `interval_hours` are independent of mesh resolution. Arbitrary leads would
  require a coordinated v2 schema in MPASWF and BMatrix.
- MPAS physics, NAMELIST keys, stream semantics, and supported NetCDF
  fields remain MPAS-specific. Generic means **compatible MPAS meshes and
  campaigns**, not arbitrary numerical models.
- PBS site configuration and scientific initialization templates are
  selected inputs, not values inferred from mesh resolution.

## Remaining limitations requiring scientific or architectural work

1. **Physics templates are not universally physical.** The
   `templates/invariant/namelist.init_atmosphere.in` template parameterizes
   `config_nvertlevels` and graph partition, but retains fixed soil, GFS,
   GOCART, vertical-grid and interpolation choices (e.g.
   `config_nsoillevels=4`, `config_nfglevels=35`,
   `config_gocartlevels=30`). Treat it as a starting template, review these
   fields for every new case, and keep validated science inputs with the case.
2. **The strict init/forecast validator has an explicit MPAS-GFS/NMC
   contract.** It checks the GFS prefix and NMC DA cycling flags, and the
   forecast renderer modifies several MPAS options. This is not fully generic
   across alternative meteorological data sources or initialization methods.
3. **Geometry validation is distributed.** MPASWF preflight checks selected
   resource paths and stages; full comparison of NetCDF cell coordinates and
   vertical interfaces against the BMatrix mesh is performed by the latter's
   `check-manifest --config` scientific preflight.
4. **Source content may change in place.** The new workdir identity hashes the
   selected YAML settings and paths, not full mesh/GFS/NetCDF bytes. Replacing
   a model binary, mesh or GFS file at the same path still requires fresh
   workspaces or explicit data checksums.
5. **Static files need case isolation.** Keep `paths.static_dir` distinct
   for unrelated meshes or physical configurations, as well as
   `paths.work_dir`; the workdir marker does not protect a shared static
   directory against two concurrent campaigns.
6. **NMC numerical reproducibility has not been proved.** A frozen GFS input,
   compiled MPAS/JEDI version, partition and full JACI output comparisons
   remain mandatory. Unit tests cannot prove identical forecast fields.

## Example of custom mesh filenames

```yaml
mesh:
  name: regional_2027
  nvertlevels: 72
  grid_filename: regional.mesh.nc
  graph_filename: regional.graph
  partition_prefix: regional.graph.part.

static:
  links:
    - source: /data/regional.mesh.nc
      target: regional.mesh.nc
    - source: /data/regional.graph
      target: regional.graph
    - source: /data/regional.graph.part.96
      target: regional.graph.part.96

pbs:
  select: 1
  mpiprocs: 96
```

The example is a **structural demonstration** only. A correct 96-rank
partition, invariant/vertical grid, physics files, timestep and executable
must be supplied and independently validated.
