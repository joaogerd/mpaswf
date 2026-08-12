# Getting started with MPASWF

This guide is written for a user who has **never run MPAS or WPS before**. Its
goal is to make the complete MPASWF workflow understandable and executable
without relying on undocumented local knowledge.

The guide uses the JACI/x1.10242 configuration shipped in `configs/`, because
that is the validated operational context currently targeted by the repository.
The same concepts apply to another machine after adapting the platform paths and
scheduler settings.

## 1. What MPASWF does

MPASWF is an orchestration tool around existing meteorological software. It
creates the MPAS forecast pairs required by the downstream MPAS-BMatrix NMC
workflow.

The data flow is:

```text
GFS analysis (GRIB2)
        |
        v
WPS ungrib -> FILE:YYYY-MM-DD_HH
        |
        v
MPAS static interpolation -> x1.10242.static.nc   [once per mesh]
        |
        v
MPAS atmospheric initialization -> initial state  [once per init time]
        |
        v
MPAS forecast integration -> f024 / f048 products
        |
        v
forecast-pair manifest -> consumed by MPAS-BMatrix
```

MPASWF does **not** compile MPAS or WPS. It also does not run BFLOW, BUMP,
SABER/JEDI calibration, observation processing, or B-matrix diagnostics. Those
are separate responsibilities.

## 2. The minimum terminology you need

### GFS

The Global Forecast System provides the meteorological analysis used to
initialize MPAS. In this workflow, MPASWF expects a GFS `f000` GRIB2 file for
every required model initialization time.

### WPS / `ungrib`

WPS is the Weather Research and Forecasting Preprocessing System. MPASWF uses
`link_grib.csh` and `ungrib.exe` to decode the GFS GRIB2 fields into a WPS
intermediate file named like:

```text
FILE:2026-06-20_00
```

That intermediate file becomes an input to `mpas_init_atmosphere`.

### MPAS mesh

MPAS uses an unstructured mesh rather than a regular latitude/longitude grid.
This repository's standard configuration targets `x1.10242`, a mesh with 10,242
cells.

### Partition file

MPI distributes mesh cells across ranks. A partition file tells MPAS which cells
belong to which rank. A filename ending in `.part.128` is intended for 128 MPI
ranks and must be used with `pbs.mpiprocs: 128`.

### Static interpolation

Before date-dependent atmospheric initialization, MPAS needs mesh/geographic
information mapped to the mesh. `mpas_init_atmosphere` generates a static product
once:

```text
x1.10242.static.nc
```

MPASWF reuses this file for all cycles as long as it passes validation.

### Atmospheric initialization

For each required model start time, `mpas_init_atmosphere` combines the static
mesh information and the WPS meteorological input to create a date-dependent MPAS
initial state.

### Forecast lead

A forecast lead is the number of hours integrated after initialization:

```text
f024 = 24-hour forecast
f048 = 48-hour forecast
```

### Valid time

The valid time is the time represented by the forecast output:

```text
valid time = initialization time + forecast lead
```

For example:

```text
initialization: 2026-06-20 00Z
lead:           48 h
valid time:     2026-06-22 00Z
```

### NMC forecast pair

MPAS-BMatrix needs two forecasts valid at the **same time**:

```text
valid time T
├── f048 initialized at T - 48 h
└── f024 initialized at T - 24 h
```

The NMC perturbation is built downstream from those same-valid-time forecasts.
MPASWF's campaign configuration therefore starts from **valid times**, not from
initialization times.

## 3. What must already exist before MPASWF can run

MPASWF orchestrates existing components. A real run requires all of the
following:

```text
1. Python 3.10 or newer
2. PyYAML
3. WPS installation
   - link_grib.csh
   - ungrib.exe
   - Vtable.GFS
4. MPAS executables
   - mpas_init_atmosphere
   - mpas_atmosphere
5. MPAS mesh file
6. MPI partition matching the configured rank count
7. validated WPS/MPAS template files
8. GFS f000 files, or a configured download URL
9. PBS commands and MPI launcher when execution.backend = pbs
10. a shared filesystem visible from login and compute nodes
```

The repository configuration tells MPASWF where each item is located. It does
not silently search the machine for alternatives.

## 4. Clone and install MPASWF

```bash
git clone https://github.com/joaogerd/mpaswf.git
cd mpaswf
python -m pip install --no-deps -e .
```

Confirm that the command is available:

```bash
mpaswf --help
```

For repository development/testing:

```bash
python -m pip install -e '.[dev]'
pytest
```

## 5. Understand the two configuration files

The recommended configuration is split into:

```text
configs/
├── jaci-x1.10242.yaml
└── mpas-x1.10242.yaml
```

`jaci-x1.10242.yaml` describes **where and how the workflow runs**:

```text
paths
executables
mesh/support links
PBS/MPI
runtime environment
```

`mpas-x1.10242.yaml` describes **what the workflow produces**:

```text
campaign valid times
24 h / 48 h forecast leads
GFS naming
WPS naming
MPAS output naming
template filenames
static product contract
validation
```

The platform file references the workflow contract internally, so the user still
passes only one file:

```bash
CONFIG=configs/jaci-x1.10242.yaml
```

Do not add a second `--config`; there is no new execution syntax.

## 6. Configure JACI paths before the first run

Open:

```text
configs/jaci-x1.10242.yaml
```

The file contains detailed comments above every setting. Review each section in
order.

### 6.1 Working directories

Verify the intended roots:

```bash
echo "$USER"
```

With the shipped configuration, MPASWF expands `$USER` in paths such as:

```text
/p/projetos/monan_das/$USER/work/mpaswf
/p/projetos/monan_das/$USER/data/gfs
```

Create the writable work/data roots if needed:

```bash
mkdir -p "/p/projetos/monan_das/$USER/work/mpaswf"
mkdir -p "/p/projetos/monan_das/$USER/data/gfs"
```

### 6.2 WPS installation

Read `executables.wps_dir` from the YAML and verify that the required files
exist. For the default JACI layout:

```bash
WPS=/p/projetos/monan_das/$USER/data/mpas-bmatrix-global/external/WPS/WPS-4.6.0

test -d "$WPS" && echo "WPS root: OK"
test -x "$WPS/ungrib.exe" && echo "ungrib.exe: OK"
test -x "$WPS/link_grib.csh" && echo "link_grib.csh: OK"
test -f "$WPS/ungrib/Variable_Tables/Vtable.GFS" && echo "Vtable.GFS: OK"
```

If any check fails, correct `executables.wps_dir` before continuing.

### 6.3 MPAS executables

Verify both configured executables:

```bash
MPAS_INIT=/p/projetos/monan_das/$USER/builds/monan-jedi-mpas/bin/mpas_init_atmosphere
MPAS_ATM=/p/projetos/monan_das/$USER/builds/monan-jedi-mpas/bin/mpas_atmosphere

test -x "$MPAS_INIT" && echo "mpas_init_atmosphere: OK"
test -x "$MPAS_ATM" && echo "mpas_atmosphere: OK"
```

Both should come from the same compatible MPAS installation/build used by the
configured runtime modules.

### 6.4 Mesh and partition

Verify the paths under `static.links`:

```bash
GRID=/p/projetos/monan_das/$USER/projects/mpas_meshes/quasi_uniform/x1.10242_240km/mesh/x1.10242.grid.nc
PART=/p/projetos/monan_das/$USER/projects/mpas_meshes/quasi_uniform/x1.10242_240km/partitions/x1.10242.graph.info.part.128

test -f "$GRID" && echo "grid: OK"
test -f "$PART" && echo "partition: OK"
```

The shipped partition is for 128 ranks. Keep:

```yaml
pbs:
  mpiprocs: 128
```

unless you deliberately select a different partition file.

### 6.5 Validated template files

This is the dependency most likely to be unfamiliar to a first-time MPAS user.
MPASWF does not generate generic namelist/streams settings because those settings
are tied to the MPAS build, mesh, physics, and validated reference case.

Set `paths.cdct_templates_dir` to a directory containing exactly the source
configuration you intend to run. The x1.10242 workflow contract expects:

```text
namelist.wps.in
namelist.init_atmosphere.static.in
streams.init_atmosphere.static.in
namelist.init_atmosphere.in
streams.init_atmosphere.in
namelist.atmosphere.in
streams.atmosphere.in
```

After setting the path, verify all seven files:

```bash
TEMPLATES=/path/to/validated/mpaswf-templates/x1.10242

for f in \
  namelist.wps.in \
  namelist.init_atmosphere.static.in \
  streams.init_atmosphere.static.in \
  namelist.init_atmosphere.in \
  streams.init_atmosphere.in \
  namelist.atmosphere.in \
  streams.atmosphere.in
do
  test -f "$TEMPLATES/$f" || echo "MISSING: $TEMPLATES/$f"
done
```

If a required template is missing, stop here. Do not replace it with an arbitrary
MPAS example. Use templates from the validated case compatible with the
executables and data you are running.

### 6.6 PBS environment

The JACI file configures:

```yaml
modules:
  - "module load PrgEnv-gnu"
  - "module load cray-mpich"
```

and environment variables required by the runtime. These commands are written
into each PBS script before `mpiexec` starts.

Do not assume that a login-shell environment is automatically inherited by a
batch job. The PBS block is the reproducible runtime contract.

## 7. Configure the campaign dates

Open:

```text
configs/mpas-x1.10242.yaml
```

The default campaign is:

```yaml
campaign:
  start_valid_time: "2026-06-22T00:00:00Z"
  end_valid_time: "2026-06-25T00:00:00Z"
  interval_hours: 24
  leads_hours: [24, 48]
```

This requests four valid times:

```text
2026-06-22 00Z
2026-06-23 00Z
2026-06-24 00Z
2026-06-25 00Z
```

For the first valid time, MPASWF needs initialization cycles:

```text
2026-06-20 00Z  -> f048 -> valid 2026-06-22 00Z
2026-06-21 00Z  -> f024 -> valid 2026-06-22 00Z
```

The complete campaign therefore requires every unique initialization time implied
by all requested valid times and leads.

## 8. Prepare the required GFS files

With the default GFS contract:

```yaml
gfs:
  file_template: "gfs.t{init_hour}z.pgrb2.0p25.f000"
  url_template: null
```

MPASWF expects files to already exist locally under:

```text
<gfs_dir>/<YYYYMMDDHH>/gfs.tHHz.pgrb2.0p25.f000
```

For the first example pair:

```text
.../gfs/2026062000/gfs.t00z.pgrb2.0p25.f000
.../gfs/2026062100/gfs.t00z.pgrb2.0p25.f000
```

If `url_template` remains `null`, a missing GFS file is a configuration/data
error, not something MPASWF can repair automatically.

## 9. Run the real PBS smoke before running MPAS

The PBS smoke tests scheduler/MPI infrastructure without spending time on a real
MPAS integration:

```bash
CONFIG=configs/jaci-x1.10242.yaml
mpaswf pbs-smoke --config "$CONFIG"
```

It performs a real `qsub`, monitors the real PBS job with `qstat`, requests one
CPU and one MPI rank, executes `/bin/hostname` on a compute node, and verifies a
sentinel file on the shared filesystem.

Successful output ends with a message similar to:

```text
✓ PBS smoke: compute-node execution validated by .../pbs-smoke.ok.
```

Generated smoke files are under:

```text
<work_dir>/.mpaswf/pbs-smoke/
```

If this smoke fails, fix PBS/MPI/environment access before running MPAS.

## 10. Phase 1 — prepare GFS/WPS input

Run:

```bash
mpaswf run --phase prepare --config "$CONFIG"
```

For every required initialization time, MPASWF:

```text
1. locates or acquires the GFS f000 file;
2. creates a cycle-specific WPS working directory;
3. links link_grib.csh and ungrib.exe;
4. links the configured GFS Vtable;
5. renders namelist.wps;
6. runs link_grib.csh;
7. runs ungrib.exe;
8. validates the expected FILE:YYYY-MM-DD_HH product.
```

Expected directory pattern:

```text
<work_dir>/wps/2026062000/
├── FILE:2026-06-20_00
├── namelist.wps
├── Vtable -> ...
├── link_grib.csh -> ...
├── ungrib.exe -> ...
├── logs/
└── .mpaswf/
```

Do not continue to initialization until `prepare` completes successfully for all
required cycles.

## 11. Phase 2 — static and atmospheric initialization

For a first/small campaign, use the blocking form:

```bash
mpaswf run --phase init --config "$CONFIG" --submit --wait
```

The phase has two dependency layers.

### 11.1 Static product

If `x1.10242.static.nc` does not exist or is invalid, MPASWF stages and submits:

```text
<static_dir>/qsub_static.pbs
```

The terminal waits for PBS completion and validates the static output.

### 11.2 Date-dependent initial states

Once the static product is valid, MPASWF creates one initialization run per
required cycle and submits scripts such as:

```text
<work_dir>/init/2026062000/qsub_init_2026062000.pbs
<work_dir>/init/2026062100/qsub_init_2026062100.pbs
```

Each initialization combines the cycle's WPS file with the static mesh product.

For larger production campaigns, `--wait` may be omitted and scheduler control
handled separately. The command interface remains the same.

## 12. Phase 3 — run f024/f048 forecasts

Run:

```bash
mpaswf run --phase forecast --config "$CONFIG" --submit --wait
```

MPASWF validates each required initial state, stages the atmosphere-model run,
and submits named PBS scripts such as:

```text
<work_dir>/forecast/2026062000/f048/qsub_forecast_2026062000_f048.pbs
<work_dir>/forecast/2026062100/f024/qsub_forecast_2026062100_f024.pbs
```

A successful forecast must produce both expected products:

```text
restart.<valid-time>.nc
mpasout.<valid-time>.nc
```

The exact filenames come from the `products` block.

## 13. Phase 4 — write the forecast-pair manifest

After every requested forecast has completed and validated:

```bash
mpaswf run --phase manifest --config "$CONFIG"
```

The output is:

```text
<work_dir>/products/mpas-forecast-manifest.tsv
```

with columns:

```text
valid_time    f048_state    f024_state    f048_restart    f024_restart
```

Each row is a same-valid-time pair ready for the downstream MPAS-BMatrix
workflow.

## 14. What the work directory should look like

A completed campaign resembles:

```text
<work_dir>/
├── .mpaswf/
│   ├── pbs-smoke/
│   ├── prepare.json
│   ├── init.json
│   ├── forecast.json
│   └── manifest.json
├── wps/
│   └── <initialization cycles>/
├── init/
│   └── <initialization cycles>/
├── forecast/
│   └── <initialization cycle>/
│       ├── f024/
│       └── f048/
└── products/
    └── mpas-forecast-manifest.tsv
```

The separate `static_dir` contains the reusable static product and its metadata.

## 15. Logs and job files

Every stage keeps persistent logs in its run directory. PBS scripts are named by
purpose instead of using a generic `job.pbs`:

```text
qsub_static.pbs
qsub_init_YYYYMMDDHH.pbs
qsub_forecast_YYYYMMDDHH_f024.pbs
qsub_forecast_YYYYMMDDHH_f048.pbs
qsub_pbs_smoke.pbs
```

If a scheduler job fails, inspect both:

```text
logs/pbs.stdout.log
logs/pbs.stderr.log
```

and, for local helper commands such as WPS, the corresponding command logs in the
same stage's `logs/` directory.

## 16. Safe reruns and `--force`

MPASWF is intentionally idempotent. If an output exists and passes validation,
the normal behavior is to reuse it rather than recompute it.

Use `--force` only when you intentionally want to regenerate a selected phase:

```bash
mpaswf run --phase prepare --config "$CONFIG" --force
mpaswf run --phase init --config "$CONFIG" --submit --wait --force
mpaswf run --phase forecast --config "$CONFIG" --submit --wait --force
```

Do not use `--force` as the first response to an unexplained failure. Read the
logs first; otherwise a configuration error may simply be repeated at additional
cost.

## 17. Common failures and how to diagnose them

### `Configuration file not found`

Cause: wrong `--config` path.

Check:

```bash
ls -l configs/jaci-x1.10242.yaml
```

### Missing workflow contract

Cause: `workflow.configuration` points to a nonexistent file.

The shipped JACI file expects:

```text
configs/mpas-x1.10242.yaml
```

### WPS directory or executable does not exist

Cause: `executables.wps_dir` does not match the actual WPS installation.

Verify `link_grib.csh`, `ungrib.exe`, and `Vtable.GFS` as shown in section 6.2.

### MPAS executable does not exist

Cause: `executables.mpas_init` or `executables.mpas_atmosphere` is wrong, or the
build is unavailable on the filesystem.

Use `test -x` on both configured paths.

### Required GFS file is missing

Cause: `url_template: null` and the expected cycle file is not present.

Calculate the initialization times implied by the campaign and leads, then place
the matching files below `paths.gfs_dir`.

### WPS `FILE:*` product is missing

Cause: `ungrib.exe` failed, the Vtable/input is wrong, or the rendered
`namelist.wps` does not match the input.

Inspect the cycle-specific WPS logs before changing downstream MPAS settings.

### PBS job remains in `Q`

`Q` means queued. This may be normal scheduler waiting. MPASWF displays state,
elapsed time, and the next `qstat` check. If queueing is unexpectedly long, use
site PBS tools to inspect scheduler reasons and queue policy.

### PBS job disappears but the expected output is missing

The scheduler finished the job, but MPASWF's output validation failed. Inspect
`pbs.stdout.log` and `pbs.stderr.log`. A scheduler completion is not treated as
scientific success by itself.

### Partition/rank mismatch

Symptoms may include MPAS startup errors or incorrect partition lookup. Ensure a
`.part.128` file is paired with 128 MPI ranks, for example.

### Template-rendering error about an unknown placeholder

MPASWF templates use Python `str.format`. Use only documented placeholders. A
literal `{` or `}` that is not a placeholder must be written as `{{` or `}}`.
See [configuration.md](configuration.md#13-supported-template-placeholders).

## 18. Hand off to MPAS-BMatrix

MPASWF's responsibility ends when this file exists and is valid:

```text
<work_dir>/products/mpas-forecast-manifest.tsv
```

The MPAS-BMatrix tutorial consumes that manifest as its upstream forecast-pair
input. MPASWF should not be extended to perform BFLOW/BUMP work unless the
project boundary is intentionally redesigned.

## 19. First successful campaign checklist

Before considering a setup operational, confirm all of the following:

```text
[ ] `mpaswf --help` works
[ ] platform YAML and workflow YAML both load
[ ] WPS root exists
[ ] link_grib.csh exists and is executable
[ ] ungrib.exe exists and is executable
[ ] Vtable.GFS exists
[ ] mpas_init_atmosphere exists and is executable
[ ] mpas_atmosphere exists and is executable
[ ] x1.10242 grid exists
[ ] partition file exists and matches mpiprocs
[ ] all seven validated templates exist
[ ] all required GFS cycles exist or a real URL template is configured
[ ] `mpaswf pbs-smoke` succeeds
[ ] `prepare` produces every WPS FILE:* input
[ ] `init` produces/reuses static.nc and all initial states
[ ] `forecast` produces all requested f024/f048 outputs
[ ] `manifest` writes mpas-forecast-manifest.tsv
[ ] manifest rows pair f048 and f024 at the same valid time
```

Once this checklist passes, the same documented commands can be reused for later
campaigns by changing only the intended configuration values.
