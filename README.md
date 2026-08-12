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

It does **not** run BFLOW, BUMP, JEDI, observation processing, or B-matrix
calibration.

## Installation

```bash
python -m pip install --no-deps -e .
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

`configs/jaci-x1.10242.yaml` references the second file with:

```yaml
workflow:
  configuration: mpas-x1.10242.yaml
```

MPASWF loads both files and deep-merges them internally. **The command-line
interface is unchanged**: always pass only one configuration path.

```bash
CONFIG=configs/jaci-x1.10242.yaml

mpaswf run --phase prepare  --config "$CONFIG"
mpaswf run --phase init     --config "$CONFIG" --submit --wait
mpaswf run --phase forecast --config "$CONFIG" --submit --wait
mpaswf run --phase manifest --config "$CONFIG"
```

The historical all-in-one YAML remains fully supported. `examples/config.yaml`
is retained as the compatibility/reference example, so existing scripts and the
MPAS-BMatrix forecast-pair tutorial do not need to change their invocation.

See [docs/configuration.md](docs/configuration.md) for the complete description
and [configs/README.md](configs/README.md) for the configuration directory.

## f024/f048 campaign contract

`campaign.start_valid_time` and `campaign.end_valid_time` are **valid times**,
not initialization times. With:

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

The final manifest therefore contains same-valid-time NMC pairs expected by
MPAS-BMatrix.

## Public interface

```bash
mpaswf run --phase prepare  --config config.yaml
mpaswf run --phase init     --config config.yaml
mpaswf run --phase forecast --config config.yaml
mpaswf run --phase manifest --config config.yaml

# Real scheduler smoke: qsub + qstat + one MPI rank on a compute node.
mpaswf pbs-smoke --config config.yaml
```

### `prepare`

Reuses or acquires required GFS files and executes WPS `link_grib`/`ungrib` for
each initialization time.

### `init`

Generates the one-time mesh-level static product when missing, then generates
the date-dependent MPAS initial states.

For PBS, a robust non-blocking campaign can submit the static boundary first
and rerun after it completes:

```bash
mpaswf run --phase init --config "$CONFIG" --submit
mpaswf run --phase init --config "$CONFIG" --submit
```

For a smoke/small campaign:

```bash
mpaswf run --phase init --config "$CONFIG" --submit --wait
```

### `forecast`

Runs the requested f024/f048 forecasts and produces both `restart` and
`da_state` products:

```bash
mpaswf run --phase forecast --config "$CONFIG" --submit --wait
```

### `manifest`

Validates the forecast products and writes:

```text
<work_dir>/products/mpas-forecast-manifest.tsv
```

with columns:

```text
valid_time    f048_state    f024_state    f048_restart    f024_restart
```

This file is the hand-off to MPAS-BMatrix.

## PBS script names

Rendered submission files are stage-specific:

```text
static/qsub_static.pbs
init/2018041500/qsub_init_2018041500.pbs
forecast/2018041500/f024/qsub_forecast_2018041500_f024.pbs
forecast/2018041500/f048/qsub_forecast_2018041500_f048.pbs
```

The scheduler `#PBS -N` names remain compact while the files on disk identify
the stage, cycle, and forecast lead.

## Real PBS smoke

Before a campaign on the PBS login node:

```bash
mpaswf pbs-smoke --config "$CONFIG"
```

The smoke performs a real scheduler round trip. It:

1. renders `<work_dir>/.mpaswf/pbs-smoke/qsub_pbs_smoke.pbs`;
2. submits through the configured `qsub` command;
3. monitors the job through the configured `qstat` command;
4. loads the configured modules/environment;
5. requests only 1 CPU / 1 MPI rank and runs `/bin/hostname` on a compute node;
6. requires `<work_dir>/.mpaswf/pbs-smoke/pbs-smoke.ok` before succeeding.

Typical output:

```text
• PBS smoke: rendered .../qsub_pbs_smoke.pbs.
• PBS: submitting qsub_pbs_smoke.pbs
✓ PBS: submitted qsub_pbs_smoke.pbs as 328134.pbs-ha (00:00)
⠋ PBS job 328134.pbs-ha: state R elapsed 00:04 next check in 25s
✓ PBS job 328134.pbs-ha: no longer listed; validating outputs
✓ PBS smoke: compute-node execution validated by .../pbs-smoke.ok.
```

## Terminal progress

Interactive sessions use a compact braille spinner for long-running operations.
PBS waiting shows the scheduler state, elapsed time, and countdown until the next
real `qstat` query. Redirected output uses durable `[RUN]`, `[OK]`, and `[FAIL]`
lines.

Color follows terminal conventions:

```bash
MPASWF_COLOR=always mpaswf run --phase prepare --config "$CONFIG"
MPASWF_COLOR=never  mpaswf run --phase prepare --config "$CONFIG"
NO_COLOR=1          mpaswf run --phase prepare --config "$CONFIG"
```

## Design documentation

- [Configuration](docs/configuration.md)
- [Design](docs/design.md)
- [CD-CT mapping](docs/cdct_mapping.md)
