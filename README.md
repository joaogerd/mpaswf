# MPASWF

`mpaswf` prepares the MPAS forecast pairs used by the downstream
[MPAS-BMatrix](https://github.com/joaogerd/MPAS-BMatrix) NMC workflow.

```text
GFS f000
  -> WPS / ungrib
  -> MPAS static interpolation
  -> MPAS atmospheric initialization
  -> f024 and f048 forecasts
  -> neutral forecast-pair manifest
```

It does not compile MPAS/WPS and it does not run the B-matrix calibration.

## Software contract

The normal configuration uses **one MONAN-JEDI installation root** for all
compiled runtime software:

```bash
export MONAN_JEDI_INSTALL_ROOT=/p/projetos/monan_das/$USER/build/monan-jedi
```

`configs/jaci-x1.10242.yaml` points `software.monan_jedi_root` to that prefix.
MPASWF derives the required files from it:

```text
${MONAN_JEDI_INSTALL_ROOT}/bin/mpas_init_atmosphere
${MONAN_JEDI_INSTALL_ROOT}/bin/mpas_atmosphere
${MONAN_JEDI_INSTALL_ROOT}/bin/ungrib.exe
${MONAN_JEDI_INSTALL_ROOT}/bin/link_grib.csh
${MONAN_JEDI_INSTALL_ROOT}/share/wps/Variable_Tables/Vtable.GFS
```

The versioned WPS source/build/release directories are private MONAN-JEDI
implementation details. MPASWF must not point at them.

Historical all-in-one configs using `executables.wps_dir`,
`executables.mpas_init`, and `executables.mpas_atmosphere` remain supported for
compatibility, but new JACI configurations should use `software.monan_jedi_root`.

## Other required inputs

The software installation is only one part of a run. MPASWF also needs:

- the MPAS mesh and an MPI partition matching the configured rank count;
- validated WPS/MPAS namelist and streams templates;
- GFS `f000` files, or a configured acquisition URL;
- PBS/MPI access when `execution.backend: pbs` is used.

These are experiment/site inputs and intentionally remain outside the
MONAN-JEDI software prefix.

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

The recommended JACI configuration is split into two files:

```text
configs/
├── jaci-x1.10242.yaml   # machine, software root, mesh inputs, PBS/MPI
└── mpas-x1.10242.yaml   # campaign and product/scientific conventions
```

The platform file includes the workflow contract internally, so users still pass
one configuration path:

```bash
CONFIG=configs/jaci-x1.10242.yaml
```

The important software setting is:

```yaml
software:
  monan_jedi_root: /p/projetos/monan_das/$USER/build/monan-jedi
```

See [docs/configuration.md](docs/configuration.md) for the complete configuration
contract.

## NMC forecast-pair contract

Campaign dates are **valid times**, not initialization times. For each requested
valid time `T`, MPASWF produces:

```text
f048 initialized at T - 48 h, valid at T
f024 initialized at T - 24 h, valid at T
```

The final manifest therefore contains same-valid-time forecast pairs for
MPAS-BMatrix.

## First-run sequence on JACI

After installing MONAN-JEDI and checking the mesh/templates/GFS paths:

```bash
CONFIG=configs/jaci-x1.10242.yaml

# Verify scheduler + MPI + compute-node filesystem access.
mpaswf pbs-smoke --config "$CONFIG"

# Decode GFS through the installed WPS runtime.
mpaswf run --phase prepare --config "$CONFIG"

# Create/reuse static data and all initial states.
mpaswf run --phase init --config "$CONFIG" --submit --wait

# Run all required f024/f048 forecasts.
mpaswf run --phase forecast --config "$CONFIG" --submit --wait

# Validate the pairs and write the hand-off manifest.
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

## Safe reruns

Valid existing products are reused. Use `--force` only when a selected phase
must be regenerated. Logs and `.mpaswf` metadata remain in each stage directory.

## Documentation

- [Getting started](docs/getting-started.md)
- [Configuration reference](docs/configuration.md)
- [Design](docs/design.md)
- [CD-CT mapping](docs/cdct_mapping.md)
- [Configuration directory](configs/README.md)
