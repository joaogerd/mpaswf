# MPASWF

`mpaswf` is a small MPAS-only workflow that prepares GFS/WPS inputs, generates
MPAS initial conditions, runs f024/f048 forecasts, and writes the neutral
forecast-pair manifest consumed by MPAS-BMatrix.

```text
GFS f000
  -> WPS / ungrib
  -> mesh-level static interpolation
  -> date-dependent MPAS initialization
  -> f024 and f048 MPAS forecasts
  -> restart + da_state products
  -> neutral MPAS manifest
```

It does **not** run BFLOW, BUMP, JEDI/SABER calibration, observation processing,
or B-matrix diagnostics.

## New to MPAS or WPS?

Start with **[docs/getting-started.md](docs/getting-started.md)**. It is written
for a user who has never run MPAS before and explains, in order:

- what GFS, WPS, MPAS mesh, partitions, static interpolation, initialization,
  forecast leads, and valid times mean;
- which external executables/data/files must exist before MPASWF can run;
- how to verify the JACI paths;
- which seven validated template files are required and why MPASWF does not
  invent generic MPAS namelists/streams;
- how the f024/f048 same-valid-time pair is constructed for NMC;
- how to run the real PBS smoke test;
- how to execute `prepare`, `init`, `forecast`, and `manifest`;
- what directories/files should appear after each phase;
- where logs and PBS scripts are written;
- how safe reruns and `--force` work;
- how to diagnose the most common failures.

The repository documentation and the shipped configuration comments are in
English and are intended to be sufficient for an independent first run.

## What must already exist

MPASWF orchestrates existing software; it does not compile the model. A real run
needs:

```text
Python >= 3.10
WPS: link_grib.csh + ungrib.exe + Vtable.GFS
MPAS: mpas_init_atmosphere + mpas_atmosphere
MPAS mesh + MPI partition
validated WPS/MPAS namelist/streams templates
GFS f000 input files (or a configured download URL)
PBS/qsub/qstat + MPI launcher when using the PBS backend
```

The getting-started guide shows how to verify each dependency before spending
scheduler time on a model run.

## Installation

```bash
git clone https://github.com/joaogerd/mpaswf.git
cd mpaswf
python -m pip install --no-deps -e .
mpaswf --help
```

For development:

```bash
python -m pip install -e '.[dev]'
pytest
```

## Configuration

The recommended layout mirrors MPAS-BMatrix and separates machine-specific
settings from the workflow/campaign contract:

```text
configs/
├── jaci-x1.10242.yaml   # paths, executables, mesh assets, PBS/MPI
└── mpas-x1.10242.yaml   # campaign, GFS/WPS, products, templates
```

Both files contain extensive inline English documentation. The platform file
references the workflow contract with:

```yaml
workflow:
  configuration: mpas-x1.10242.yaml
```

MPASWF loads both files and deep-merges them internally. **The command-line
interface is unchanged**: always pass only one configuration path.

```bash
CONFIG=configs/jaci-x1.10242.yaml
```

The historical all-in-one YAML remains fully supported. `examples/config.yaml`
is retained as the compatibility/reference example, so existing scripts and the
MPAS-BMatrix forecast-pair tutorial do not need to change their invocation.

See [docs/configuration.md](docs/configuration.md) for the complete field
reference and [configs/README.md](configs/README.md) for the configuration-file
organization.

## The f024/f048 campaign contract

`campaign.start_valid_time` and `campaign.end_valid_time` are **valid times**,
not initialization times.

With:

```yaml
campaign:
  start_valid_time: "2026-06-22T00:00:00Z"
  end_valid_time: "2026-06-25T00:00:00Z"
  interval_hours: 24
  leads_hours: [24, 48]
```

for each valid time `T`, MPASWF produces:

```text
f048 initialized at T - 48 h, valid at T
f024 initialized at T - 24 h, valid at T
```

For example, for valid time `2026-06-22 00Z`:

```text
2026-06-20 00Z -> 48 h forecast -> 2026-06-22 00Z
2026-06-21 00Z -> 24 h forecast -> 2026-06-22 00Z
```

The final manifest therefore contains the same-valid-time NMC pairs expected by
MPAS-BMatrix.

## First-run sequence on JACI

After reviewing the paths and dependencies described in the getting-started
guide:

```bash
CONFIG=configs/jaci-x1.10242.yaml

# 1. Verify real PBS + MPI + compute-node execution with one rank.
mpaswf pbs-smoke --config "$CONFIG"

# 2. Decode every required GFS analysis through WPS/ungrib.
mpaswf run --phase prepare --config "$CONFIG"

# 3. Generate/reuse the static product and create all MPAS initial states.
mpaswf run --phase init --config "$CONFIG" --submit --wait

# 4. Run all required 24 h / 48 h MPAS forecasts.
mpaswf run --phase forecast --config "$CONFIG" --submit --wait

# 5. Validate the products and write the MPAS-BMatrix hand-off manifest.
mpaswf run --phase manifest --config "$CONFIG"
```

The manifest is written to:

```text
<work_dir>/products/mpas-forecast-manifest.tsv
```

with columns:

```text
valid_time    f048_state    f024_state    f048_restart    f024_restart
```

## Phase behavior

### `prepare`

For every unique initialization time, MPASWF locates/acquires the GFS f000 file,
stages WPS, renders `namelist.wps`, runs `link_grib.csh` and `ungrib.exe`, and
validates the expected `FILE:YYYY-MM-DD_HH` intermediate product.

### `init`

MPASWF first generates or reuses the one-time mesh-level static product. Once the
static dependency is valid, it generates one date-dependent MPAS initial state
for each required initialization cycle.

For a non-blocking production pattern, `--wait` can be omitted and the command
rerun after the static job completes. For a first/small campaign,
`--submit --wait` is easier to follow because the terminal remains attached to
the dependency chain.

### `forecast`

MPASWF validates each initial state, stages `mpas_atmosphere`, runs the requested
f024/f048 integrations, and requires both restart and `da_state` products.

### `manifest`

MPASWF validates every requested pair and writes the neutral TSV hand-off used by
MPAS-BMatrix.

## PBS script names and terminal progress

Rendered submission files identify their purpose:

```text
static/qsub_static.pbs
init/2018041500/qsub_init_2018041500.pbs
forecast/2018041500/f024/qsub_forecast_2018041500_f024.pbs
forecast/2018041500/f048/qsub_forecast_2018041500_f048.pbs
```

Interactive PBS waiting uses the MPAS-BMatrix-style live status line:

```text
⠋ PBS job 328134.pbs-ha: state R elapsed 03:59 next check in 0s
```

Actual `qstat` calls still respect `pbs.poll_seconds`; only the terminal spinner,
elapsed clock, and countdown are refreshed continuously.

## Real PBS smoke

Before a campaign:

```bash
mpaswf pbs-smoke --config "$CONFIG"
```

The smoke performs a real scheduler round trip. It:

1. renders `<work_dir>/.mpaswf/pbs-smoke/qsub_pbs_smoke.pbs`;
2. submits through the configured `qsub` command;
3. monitors through the configured `qstat` command;
4. loads the configured modules/environment;
5. requests only 1 CPU / 1 MPI rank and runs `/bin/hostname` on a compute node;
6. requires `<work_dir>/.mpaswf/pbs-smoke/pbs-smoke.ok` before succeeding.

If this smoke fails, fix scheduler/MPI/runtime access before running MPAS.

## Safe reruns

The workflow is idempotent: valid existing products are reused. Use `--force`
only when you deliberately want to regenerate a selected phase. Persistent logs
and `.mpaswf` metadata remain in the stage directories to support diagnosis.

## Documentation

- **[Documentation index](docs/README.md)**
- **[Getting started](docs/getting-started.md)** — first-time user guide
- **[Configuration reference](docs/configuration.md)**
- **[Design](docs/design.md)**
- **[CD-CT mapping](docs/cdct_mapping.md)**
- **[Configuration directory](configs/README.md)**
