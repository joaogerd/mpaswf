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

### `software.monan_jedi_install_root`

Canonical public installation prefix produced by MONAN-JEDI. The maintained JACI
configuration provides the user-specific default directly:

```yaml
software:
  monan_jedi_install_root: /p/projetos/monan_das/$USER/build/monan-jedi
```

A non-empty `MONAN_JEDI_INSTALL_ROOT` environment variable overrides this value
at configuration-load time.

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

When `software.monan_jedi_install_root` is absent, the deprecated
`software.monan_jedi_root` spelling remains accepted with a deprecation warning.
If neither root key is present, historical executable-specific configs remain supported:

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

Root containing cached GFS analysis inputs.

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
  url_template: "https://noaa-gfs-bdp-pds.s3.amazonaws.com/gfs.{init_yyyymmdd}/{init_hour}/atmos/{gfs_file}"
  minimum_size_bytes: 1048576
```

The local lookup convention is:

```text
<paths.gfs_dir>/<YYYYMMDDHH>/<file_template>
```

The JACI workflow first reuses a valid local file. When it is absent, the
configured URL downloads the complete 0.25-degree GFS GRIB2 product from NOAA's
public AWS archive and stores it at the same local path. The download is written
through a temporary `.download` file and renamed only after completion.

Set `url_template: null` only for campaigns where input acquisition is managed
externally; in that mode a missing local GFS file is an input error.

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
${software.monan_jedi_install_root}/share/wps/Variable_Tables/${wps.vtable_name}
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

Not every declared template is used by every configuration. When
`static.source` is configured, `templates.static_*` are bypassed. When
`validation.require_reference_preflight: true`, the maintained x1.10242
forecast stages the validated tutorial `namelist.atmosphere_240km` and
`streams.atmosphere_240km` instead of `templates.forecast_*`.

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

For the maintained JACI configuration, `pbs.stack_root` already points to the
validated shared spack-stack checkout. A non-empty `STACK_ROOT` environment
variable overrides that site default for controlled tests or migrations.

MPASWF reads
`ecosystem_contract_version: 2` from the selected MONAN-JEDI installation and
derives the compatible stack environment name, generated module name, site
setup path and module-tree layout. Those values are not duplicated in this
repository. `mpaswf check-config` validates the manifest, selected stack,
site setup and derived module tree before submission.

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

When `pbs.stack_root` is configured, MPASWF emits the standard stack bootstrap
itself: export both public anchors, load stack identity from the installed
runtime contract, purge modules, expose any `pbs.site_module_paths`, protect
the site setup from Bash `nounset`, load the derived module tree and only then
apply job-local environment variables.

`pbs.bootstrap` remains an optional list of extra shell commands after that
standard bootstrap. Maintained JACI configuration keeps it empty. The same
standard path is used by `pbs-smoke`, initialization and forecast jobs, so the
smoke test exercises the actual runtime environment rather than only scheduler
submission.

The MONAN-JEDI installation root and the external stack remain separate
contracts:

```text
software.monan_jedi_install_root -> installed MPAS/WPS/JEDI runtime products
pbs.bootstrap            -> compute-node dependency/MPI environment
```

`pbs.modules` remains supported for direct module commands in simpler sites or
legacy configurations.

Optional `queue_static`, `queue_init`, and `queue_forecast` values may override
the default queue for individual stages.

## Filesystem preflight

YAML/schema validation confirms that required keys have the expected shape, but
it does not prove that the resolved user-specific files and directories are
actually usable on the current machine.

Before a first run, or after changing site paths, run:

```bash
mpaswf check-config --config configs/jaci-x1.10242.yaml
```

The command resolves environment variables such as `$USER` and validates:

- `software.monan_jedi_install_root`;
- MPAS/WPS executables derived from that installation;
- the WPS Vtable and MPAS atmosphere share directory;
- `paths.cdct_templates_dir` and only the templates consumed by the active
  configuration path;
- for the strict reference forecast, the exact tutorial namelist/streams,
  required `stream_list.*` files, and installed MPAS physics files;
- `static.source` when configured;
- `static.tutorial_physics_files` when configured;
- every `static.links[*].source` path, including mesh, graph and partition;
- explicit filesystem paths used by `pbs.bootstrap` in `pushd`/`cd`,
  `source`, and `module use` commands;
- `paths.work_dir`, `paths.static_dir`, and `paths.gfs_dir`.

Required inputs must already exist and be readable. Writable workflow/data
directories may still be absent when their nearest existing parent is writable;
those are reported as `CREATABLE` rather than as failures.

For a machine-readable report:

```bash
mpaswf check-config --config configs/jaci-x1.10242.yaml --json
```

Any missing or inaccessible mandatory resource makes the command exit non-zero.

## `validation`

```yaml
validation:
  require_netcdf: false
  minimum_size_bytes: 1024
```

These checks prevent reuse of empty or obviously incomplete products.

## Environment expansion

Environment variables in ordinary configuration strings are expanded before validation.
Any unresolved `${VARIABLE}` reference needed by MPASWF itself is a configuration error
and fails before filesystem work begins.

PBS shell bodies are intentionally different: `pbs.bootstrap`, `pbs.modules`
and `pbs.environment.*` remain literal while configuration is loaded. They may
reference variables such as `${PBS_JOBID}` or `${PBS_O_WORKDIR}` that exist
only on the compute node; even a same-named variable in the login shell must not
replace them. The selected stack is configuration-time input. The maintained JACI YAML carries
the validated site default, while `STACK_ROOT` remains an explicit environment
override.

For JACI, `$USER` supplies user-specific storage roots, including the default
MONAN-JEDI installation. The maintained YAML also selects the validated shared
spack-stack. Users normally need no runtime-anchor exports before
`check-config`, `pbs-smoke`, `init`, or `forecast`; non-empty
`MONAN_JEDI_INSTALL_ROOT` and `STACK_ROOT` values act only as explicit
overrides.

## Path ownership rule

A useful way to decide where a setting belongs is:

```text
compiled MONAN/MPAS/JEDI/WPS software -> software.monan_jedi_install_root
mesh/GFS/templates/campaign data       -> explicit workflow input paths
work/output products                   -> paths.work_dir / paths.static_dir
scheduler/runtime policy               -> execution / pbs
```

Keeping these responsibilities separate is part of the MPASWF runtime contract.
