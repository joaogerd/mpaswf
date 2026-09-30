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
compiled runtime software. On JACI, the maintained platform configuration
derives it automatically from the current user:

```text
/p/projetos/monan_das/$USER/build/monan-jedi
```

A non-empty `MONAN_JEDI_INSTALL_ROOT` environment variable remains available as
an explicit override for alternate/test installations.
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

The dependency environment is selected separately. The maintained JACI
configuration already points to the validated shared spack-stack; a non-empty
`STACK_ROOT` environment variable may override that default for controlled
tests or migrations.

MPASWF does not duplicate the spack-stack environment name, generated JEDI
module name, or site setup script. Those values are read from:

```text
${MONAN_JEDI_INSTALL_ROOT}/share/monan-jedi/install-manifest.json
```

using `ecosystem_contract_version: 2`. This guarantees that the runtime
installation and the module environment used on PBS compute nodes are the same
contract. `STACK_ROOT` remains operator-selectable as an override; the manifest describes
the compatible environment inside that stack.

Historical all-in-one configs using `executables.wps_dir`,
`executables.mpas_init`, and `executables.mpas_atmosphere` remain supported for
compatibility. The former `software.monan_jedi_root` spelling is also accepted
with a deprecation warning. New JACI configurations should use
`software.monan_jedi_install_root`.

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
  monan_jedi_install_root: ${MONAN_JEDI_INSTALL_ROOT}
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

After installing MONAN-JEDI, use the maintained JACI defaults directly:

```bash
CONFIG=configs/jaci-x1.10242.yaml

# Resolve $USER and validate software, templates, invariant, mesh/partition,
# and writable campaign/data directories before submitting anything.
mpaswf check-config --config "$CONFIG"

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

The same phase also writes `mpas-forecast-manifest.json`. The TSV is the
portable data-plane interface; the JSON sidecar identifies the versioned
`monan-nmc-forecast-pairs-v1` contract, producer/consumer, exact column set,
pair semantics, pair count and SHA-256 of the TSV. Downstream tools can therefore
reject a changed or stale hand-off before BFLOW without depending on mpaswf's
private directory layout.

## Safe reruns

Valid existing products are reused. Use `--force` only when a selected phase
must be regenerated. Logs and `.mpaswf` metadata remain in each stage directory.

## Documentation

- [Getting started](docs/getting-started.md)
- [Configuration reference](docs/configuration.md)
- [Design](docs/design.md)
- [CD-CT mapping](docs/cdct_mapping.md)
- [Configuration directory](configs/README.md)
