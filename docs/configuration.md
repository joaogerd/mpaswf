# MPASWF configuration reference

This document is the field-by-field reference for MPASWF configuration. If you
have never run MPAS or WPS before, start with [Getting started](getting-started.md)
first. That guide explains the workflow concepts and gives a complete first-run
procedure. Return here when you need to understand or change a specific setting.

## 1. Configuration model

MPASWF accepts two equivalent layouts:

1. a **split configuration**, recommended for normal use;
2. a **self-contained single YAML**, preserved for backward compatibility.

The command-line interface is identical in both cases:

```bash
mpaswf run --phase prepare --config <file.yaml>
```

In the split layout, `<file.yaml>` is the platform configuration. It points to a
second YAML through `workflow.configuration`. MPASWF loads the workflow contract
first and deep-merges the platform configuration over it.

Recommended repository layout:

```text
configs/
├── jaci-x1.10242.yaml   # machine/platform configuration
└── mpas-x1.10242.yaml   # campaign/workflow contract
```

### Platform configuration

`configs/jaci-x1.10242.yaml` contains settings that depend on the machine or
installation:

- `paths`;
- `executables`;
- `static.links`;
- `execution`;
- `pbs`.

It includes:

```yaml
workflow:
  configuration: mpas-x1.10242.yaml
```

The referenced path is resolved relative to the platform YAML unless it is
absolute.

### Workflow contract

`configs/mpas-x1.10242.yaml` contains settings that define the campaign and file
contracts:

- `campaign`;
- `gfs`;
- `wps`;
- `products`;
- `templates`;
- `static.reference_time`;
- `static.product_template`;
- `validation`.

This separation lets one workflow contract be reused on another machine without
copying scheduler and installation paths, and lets machine settings remain stable
while campaign dates change.

## 2. Deep merge behavior

Mappings are merged recursively. Lists are atomic and are replaced rather than
concatenated.

Example workflow contract:

```yaml
static:
  reference_time: "2010-10-23T00:00:00Z"
  product_template: "x1.10242.static.nc"
```

Example platform fragment:

```yaml
static:
  links:
    - source: /path/to/x1.10242.grid.nc
      target: x1.10242.grid.nc
```

The workflow receives:

```yaml
static:
  reference_time: "2010-10-23T00:00:00Z"
  product_template: "x1.10242.static.nc"
  links:
    - source: /path/to/x1.10242.grid.nc
      target: x1.10242.grid.nc
```

The path originally passed to `--config` remains the root used to resolve
relative machine paths. The loaded workflow-contract path is retained internally
for provenance.

## 3. Environment-variable expansion

Environment variables are expanded recursively in YAML string values before
validation. For example:

```yaml
paths:
  work_dir: /p/projetos/monan_das/$USER/work/mpaswf
```

If `USER=joao.gerd`, MPASWF sees:

```text
/p/projetos/monan_das/joao.gerd/work/mpaswf
```

Use environment variables only when the resulting path is unambiguous on the
machine where the command runs.

## 4. Time concepts used by the campaign

Three time concepts appear throughout MPASWF:

- **initialization time**: when the model forecast starts;
- **forecast lead**: integration length in hours;
- **valid time**: initialization time plus forecast lead.

For a 48-hour forecast valid at `2026-06-22T00:00:00Z`:

```text
initialization = 2026-06-20T00:00:00Z
lead           = 48 h
valid          = 2026-06-22T00:00:00Z
```

For the NMC pair consumed by MPAS-BMatrix, both forecasts must have the same
valid time `T`:

```text
f048: init = T - 48 h, valid = T
f024: init = T - 24 h, valid = T
```

This is why `campaign.start_valid_time` and `campaign.end_valid_time` are valid
times, not initialization times.

## 5. `workflow`

Only needed in the split format:

```yaml
workflow:
  configuration: mpas-x1.10242.yaml
```

`configuration` may be absolute or relative to the platform file. Do not point
it back to the same platform file.

## 6. `paths`

```yaml
paths:
  work_dir: /path/to/work/mpaswf
  static_dir: /path/to/work/mpaswf/static
  gfs_dir: /path/to/data/gfs
  cdct_templates_dir: /path/to/validated/templates
```

### `paths.work_dir`

Root for run directories, workflow metadata, logs, PBS smoke files, and the final
forecast-pair manifest.

Typical generated structure:

```text
<work_dir>/
├── .mpaswf/
├── wps/
├── init/
├── forecast/
└── products/
```

### `paths.static_dir`

Directory where the one-time mesh-level static product is generated and reused.
It may be inside `work_dir` or elsewhere on a shared filesystem.

### `paths.gfs_dir`

Root of local GFS analysis data. With the default contract, the structure is:

```text
<gfs_dir>/<YYYYMMDDHH>/gfs.tHHz.pgrb2.0p25.f000
```

### `paths.cdct_templates_dir`

Directory containing the validated WPS/MPAS source templates listed in the
`templates` block. MPASWF renders copies of these files into stage directories;
it does not generate scientifically meaningful MPAS namelists/streams from
scratch.

The default x1.10242 contract expects seven files:

```text
namelist.wps.in
namelist.init_atmosphere.static.in
streams.init_atmosphere.static.in
namelist.init_atmosphere.in
streams.init_atmosphere.in
namelist.atmosphere.in
streams.atmosphere.in
```

## 7. `executables`

```yaml
executables:
  wps_dir: /path/to/WPS
  mpas_init: /path/to/mpas_init_atmosphere
  mpas_atmosphere: /path/to/mpas_atmosphere
```

### `executables.wps_dir`

WPS installation root. MPASWF expects at least:

```text
<wps_dir>/link_grib.csh
<wps_dir>/ungrib.exe
<wps_dir>/ungrib/Variable_Tables/Vtable.GFS
```

### `executables.mpas_init`

`mpas_init_atmosphere` executable. MPASWF uses it for both the static
interpolation and date-dependent atmospheric initialization stages.

### `executables.mpas_atmosphere`

Atmosphere-model executable used for f024/f048 integration.

MPASWF does not compile these executables. They must already exist and be
compatible with the runtime environment configured under `pbs.modules` and
`pbs.environment`.

## 8. `campaign`

```yaml
campaign:
  start_valid_time: "2026-06-22T00:00:00Z"
  end_valid_time: "2026-06-25T00:00:00Z"
  interval_hours: 24
  leads_hours: [24, 48]
```

### `start_valid_time` / `end_valid_time`

Inclusive UTC valid-time bounds. Timestamps must contain a timezone; a trailing
`Z` means UTC.

### `interval_hours`

Positive spacing between valid times. With the example above, valid times occur
once every 24 hours.

### `leads_hours`

Forecast integration lengths required for every valid time. The MPAS-BMatrix NMC
workflow expects `[24, 48]`.

## 9. `gfs`

```yaml
gfs:
  file_template: "gfs.t{init_hour}z.pgrb2.0p25.f000"
  url_template: null
  minimum_size_bytes: 1048576
```

### `gfs.file_template`

Filename rendered for each required initialization time.

### `gfs.url_template`

Optional acquisition URL. `null` means MPASWF will only use local input. When a
URL template is configured, missing files may be downloaded into the expected
local location.

### `gfs.minimum_size_bytes`

Minimum accepted GFS file size. This is a guard against empty or obviously
truncated downloads; it is not a full GRIB2 integrity test.

## 10. `wps`

```yaml
wps:
  output_template: "FILE:{init_date_yyyy_mm_dd_hh}"
  vtable: "{wps_dir}/ungrib/Variable_Tables/Vtable.GFS"
  namelist_target: namelist.wps
  link_grib_command: ["./link_grib.csh", "{gfs_file}"]
  ungrib_command: ["./ungrib.exe"]
```

`output_template` is the intermediate WPS product expected after `ungrib.exe`.
`vtable` selects the variable table. `link_grib_command` and `ungrib_command` are
argument lists executed without implicit shell parsing.

## 11. `products`

```yaml
products:
  init_state_template: "x1.10242.init.{init_date_yyyy_mm_dd_hh_mm_ss}.nc"
  restart_template: "restart.{valid_date_yyyy_mm_dd_hh_mm_ss}.nc"
  da_state_template: "mpasout.{valid_date_yyyy_mm_dd_hh_mm_ss}.nc"
```

These names must agree with the configured MPAS streams files. They are the files
MPASWF validates and records in the final manifest.

## 12. `templates`

```yaml
templates:
  wps: "namelist.wps.in"
  static_namelist: "namelist.init_atmosphere.static.in"
  static_streams: "streams.init_atmosphere.static.in"
  init_namelist: "namelist.init_atmosphere.in"
  init_streams: "streams.init_atmosphere.in"
  forecast_namelist: "namelist.atmosphere.in"
  forecast_streams: "streams.atmosphere.in"
```

Every filename is resolved under `paths.cdct_templates_dir`.

MPASWF template rendering uses Python `str.format` placeholders. Literal braces
inside a template that are not MPASWF placeholders must therefore be escaped as
`{{` and `}}`.

## 13. Supported template placeholders

Time context available to rendered templates includes:

```text
{init_time}                       2026-06-20T00:00:00Z
{valid_time}                      2026-06-22T00:00:00Z
{init_yyyymmddhh}                 2026062000
{init_yyyymmdd}                   20260620
{init_year}                       2026
{init_month}                      06
{init_day}                        20
{init_hour}                       00
{valid_yyyymmddhh}                2026062200
{init_date_yyyy_mm_dd_hh}         2026-06-20_00
{valid_date_yyyy_mm_dd_hh}        2026-06-22_00
{init_date_yyyy_mm_dd_hh_mm_ss}   2026-06-20_00.00.00
{valid_date_yyyy_mm_dd_hh_mm_ss}  2026-06-22_00.00.00
{lead_hours}                      48
{lead_hours_03d}                  048
{mpas_run_duration}               0002_00:00:00
```

Stage-specific code adds further values when appropriate, including paths such
as `{gfs_file}`, `{wps_file}`, `{init_state}`, `{restart_path}`,
`{da_state_path}`, and `{static_state}`. Directory context also includes
`{work_dir}`, `{static_dir}`, `{templates_dir}`, and `{run_dir}`.

The WPS configuration additionally provides `{wps_dir}` before rendering the
Vtable path.

## 14. `static`

The split configuration divides this block between the workflow and platform
files.

Workflow contract:

```yaml
static:
  reference_time: "2010-10-23T00:00:00Z"
  product_template: "x1.10242.static.nc"
```

Platform configuration:

```yaml
static:
  links:
    - source: /path/to/x1.10242.grid.nc
      target: x1.10242.grid.nc
    - source: /path/to/x1.10242.graph.info.part.128
      target: x1.10242.graph.info.part.128
```

`links` contains fixed inputs staged into MPAS run directories. The generated
`x1.10242.static.nc` must **not** be listed as an input link.

The MPI partition must match the number of MPI ranks used for the job. For
example, a `.part.128` partition belongs with `pbs.mpiprocs: 128`.

## 15. `execution`

```yaml
execution:
  backend: pbs
```

Accepted values:

- `local`: execute MPAS directly from the current process;
- `pbs`: render and optionally submit PBS jobs.

## 16. `pbs`

Typical block:

```yaml
pbs:
  queue: pesqmini
  select: 1
  ncpus: 128
  mpiprocs: 128
  walltime_static: "00:20:00"
  walltime_init: "00:30:00"
  walltime_forecast: "03:00:00"
  queue_smoke: pesqmini
  walltime_smoke: "00:02:00"
  launcher: ["mpiexec", "-n", "{mpi_ranks}"]
  qsub_command: ["qsub"]
  qstat_command: ["qstat", "-f"]
  poll_seconds: 30
  modules:
    - "module load PrgEnv-gnu"
    - "module load cray-mpich"
  environment:
    OMP_NUM_THREADS: "1"
```

### Queue selection

`queue` is the default. Optional `queue_static`, `queue_init`, and
`queue_forecast` may override it by stage. `queue_smoke` controls only the
one-rank scheduler smoke.

### Resource selection

`select`, `ncpus`, and `mpiprocs` render the normal MPAS PBS resource request.
They must be consistent with the mesh partition file and site policy.

### Walltime

`walltime_static`, `walltime_init`, and `walltime_forecast` are hard scheduler
limits. `walltime_smoke` defaults to two minutes when omitted.

### Launcher

`launcher` is rendered as an argv list. `{mpi_ranks}` becomes the configured
normal `mpiprocs` value, or `1` for `pbs-smoke`.

### Scheduler commands

`qsub_command` and `qstat_command` are argv prefixes. Keeping them configurable
allows site wrappers without changing MPASWF code.

### Polling

`poll_seconds` is the minimum interval between actual `qstat` calls. Interactive
terminal output continues to update the spinner, elapsed time, and countdown in
between polls.

### Modules and environment

Every configured module command and environment variable is written into the PBS
script before the MPI command. They must match the runtime requirements of the
installed MPAS executables.

## 17. `validation`

```yaml
validation:
  require_netcdf: false
  minimum_size_bytes: 1024
```

`minimum_size_bytes` is applied to generated products before reuse. If
`require_netcdf` is enabled, NetCDF-aware validation is added when the optional
NetCDF dependency is installed.

## 18. Recommended JACI invocation

The split configuration does not change any commands:

```bash
CONFIG=configs/jaci-x1.10242.yaml

mpaswf pbs-smoke --config "$CONFIG"
mpaswf run --phase prepare  --config "$CONFIG"
mpaswf run --phase init     --config "$CONFIG" --submit --wait
mpaswf run --phase forecast --config "$CONFIG" --submit --wait
mpaswf run --phase manifest --config "$CONFIG"
```

The final hand-off remains:

```text
<work_dir>/products/mpas-forecast-manifest.tsv
```

with columns:

```text
valid_time    f048_state    f024_state    f048_restart    f024_restart
```

## 19. Backward compatibility

A single YAML containing every required block remains valid.
`examples/config.yaml` intentionally exercises this historical format. External
scripts and the MPAS-BMatrix tutorial therefore do not need a new invocation or
new flags.
