# MPASWF configuration reference

MPASWF accepts either:

1. a platform YAML plus a referenced workflow contract; or
2. a historical self-contained YAML.

The recommended JACI files are:

```text
configs/jaci-x1.10242.yaml
configs/mpas-x1.10242.yaml
```

The public CLI always receives one path:

```bash
mpaswf run --phase prepare --config configs/jaci-x1.10242.yaml
```

## `workflow`

```yaml
workflow:
  configuration: mpas-x1.10242.yaml
```

The referenced workflow YAML is loaded first and the platform YAML is deep-merged
over it. Relative paths are resolved from the platform configuration directory.

## `software`

### `software.monan_jedi_root`

Canonical public installation prefix produced by MONAN-JEDI.

```yaml
software:
  monan_jedi_root: /p/projetos/monan_das/$USER/build/monan-jedi
```

MPASWF derives:

```text
bin/mpas_init_atmosphere
bin/mpas_atmosphere
bin/ungrib.exe
bin/link_grib.csh
share/wps/Variable_Tables/<wps.vtable_name>
```

This is the preferred software contract. Do not point it to the MONAN-JEDI
checkout, `work/` tree, or versioned WPS release directory.

## Legacy `executables`

When `software.monan_jedi_root` is absent, historical configs remain supported:

```yaml
executables:
  wps_dir: /path/to/legacy/WPS
  mpas_init: /path/to/mpas_init_atmosphere
  mpas_atmosphere: /path/to/mpas_atmosphere
```

In this mode WPS executable paths remain relative to `executables.wps_dir` and a
legacy `wps.vtable` template may use `{wps_dir}`.

New platform configs should not need these three independently configured paths.

## `paths`

### `paths.work_dir`

Root for generated WPS/init/forecast/product workspaces.

### `paths.static_dir`

Reusable mesh-level static-product workspace.

### `paths.gfs_dir`

Root containing GFS analysis inputs.

### `paths.cdct_templates_dir`

Directory containing the validated WPS/MPAS namelist and streams templates used
by this case.

## `campaign`

```yaml
campaign:
  start_valid_time: "2026-06-22T00:00:00Z"
  end_valid_time: "2026-06-25T00:00:00Z"
  interval_hours: 24
  leads_hours: [24, 48]
```

The start/end values are valid times. The standard NMC workflow requires exactly
24 h and 48 h forecast leads.

## `gfs`

```yaml
gfs:
  file_template: "gfs.t{init_hour}z.pgrb2.0p25.f000"
  url_template: null
  minimum_size_bytes: 1048576
```

The local lookup convention is:

```text
<paths.gfs_dir>/<YYYYMMDDHH>/<file_template>
```

A null URL means missing files are an input error rather than automatically
downloaded.

## `wps`

Recommended current contract:

```yaml
wps:
  vtable_name: Vtable.GFS
  output_template: "FILE:{init_date_yyyy_mm_dd_hh}"
  namelist_target: namelist.wps
  link_grib_command: ["./link_grib.csh", "{gfs_file}"]
  ungrib_command: ["./ungrib.exe"]
```

`vtable_name` is a filename only. Under the canonical MONAN-JEDI contract it is
resolved as:

```text
${software.monan_jedi_root}/share/wps/Variable_Tables/${wps.vtable_name}
```

Legacy configs may instead provide:

```yaml
wps:
  vtable: "{wps_dir}/ungrib/Variable_Tables/Vtable.GFS"
```

## `products`

Defines the expected MPAS output names:

```yaml
products:
  init_state_template: "x1.10242.init.{init_date_yyyy_mm_dd_hh_mm_ss}.nc"
  restart_template: "restart.{valid_date_yyyy_mm_dd_hh_mm_ss}.nc"
  da_state_template: "mpasout.{valid_date_yyyy_mm_dd_hh_mm_ss}.nc"
```

These names must agree with the validated streams templates.

## `templates`

```yaml
templates:
  wps: namelist.wps.in
  static_namelist: namelist.init_atmosphere.static.in
  static_streams: streams.init_atmosphere.static.in
  init_namelist: namelist.init_atmosphere.in
  init_streams: streams.init_atmosphere.in
  forecast_namelist: namelist.atmosphere.in
  forecast_streams: streams.atmosphere.in
```

The filenames are resolved below `paths.cdct_templates_dir`.

## `static`

The workflow contract declares the generated static product and reference time:

```yaml
static:
  reference_time: "2010-10-23T00:00:00Z"
  product_template: x1.10242.static.nc
```

The platform config declares fixed input links such as the grid and matching MPI
partition:

```yaml
static:
  links:
    - source: /path/to/x1.10242.grid.nc
      target: x1.10242.grid.nc
    - source: /path/to/x1.10242.graph.info.part.128
      target: x1.10242.graph.info.part.128
```

Do not list the generated static product itself as an input link.

## `execution`

```yaml
execution:
  backend: pbs
```

Supported values are `local` and `pbs`.

## `pbs`

When the backend is PBS, configure queue/resources/launcher, compute-node runtime
bootstrap and stage walltimes. The x1.10242 JACI case uses a partition matching
`mpiprocs: 128`.

Important keys include:

```text
queue
select
ncpus
mpiprocs
walltime_static
walltime_init
walltime_forecast
launcher
qsub_command
qstat_command
poll_seconds
bootstrap
modules
environment
```

`pbs.bootstrap` is an ordered list of literal shell commands executed inside
every PBS job before `pbs.modules`, environment exports and the MPI launcher.
Use it for site/runtime initialization that cannot be represented by a simple
`module load`, such as exposing and loading the validated spack-stack/JEDI module
hierarchy on JACI. The same bootstrap is used by `pbs-smoke`, initialization and
forecast jobs, so the smoke test exercises the actual runtime environment rather
than only scheduler submission.

The MONAN-JEDI installation root and the external stack remain separate
contracts:

```text
software.monan_jedi_root -> installed MPAS/WPS/JEDI runtime products
pbs.bootstrap            -> compute-node dependency/MPI environment
```

`pbs.modules` remains supported for direct module commands in simpler sites or
legacy configurations.

Optional `queue_static`, `queue_init`, and `queue_forecast` values may override
the default queue for individual stages.

## `validation`

```yaml
validation:
  require_netcdf: false
  minimum_size_bytes: 1024
```

These checks prevent reuse of empty or obviously incomplete products.

## Environment expansion

Environment variables in YAML strings are expanded before validation. For JACI,
`$USER` is therefore sufficient for user-specific roots.

## Path ownership rule

A useful way to decide where a setting belongs is:

```text
compiled MONAN/MPAS/JEDI/WPS software -> software.monan_jedi_root
mesh/GFS/templates/campaign data       -> explicit workflow input paths
work/output products                   -> paths.work_dir / paths.static_dir
scheduler/runtime policy               -> execution / pbs
```

Keeping these responsibilities separate is part of the MPASWF runtime contract.
