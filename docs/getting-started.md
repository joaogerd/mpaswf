# Getting started with MPASWF

This guide describes the first JACI run using the current runtime contract.

## 1. What MPASWF does

```text
GFS analysis (GRIB2)
        |
        v
WPS ungrib -> FILE:YYYY-MM-DD_HH
        |
        v
MPAS static interpolation -> x1.10242.static.nc
        |
        v
MPAS atmospheric initialization -> initial state
        |
        v
MPAS f024/f048 forecasts
        |
        v
forecast-pair manifest -> MPAS-BMatrix
```

MPASWF orchestrates existing software. It does not compile MONAN/MPAS, JEDI or
WPS.

## 2. Install MONAN-JEDI first

The compiled software comes from
`GAD-DIMNT-CPTEC/MONAN-JEDI`. The normal JACI installation root is:

```bash
export MONAN_JEDI_INSTALL_ROOT=/p/projetos/monan_das/$USER/build/monan-jedi
```

The installation must expose at least:

```text
$MONAN_JEDI_INSTALL_ROOT/bin/mpas_init_atmosphere
$MONAN_JEDI_INSTALL_ROOT/bin/mpas_atmosphere
$MONAN_JEDI_INSTALL_ROOT/bin/ungrib.exe
$MONAN_JEDI_INSTALL_ROOT/bin/link_grib.csh
$MONAN_JEDI_INSTALL_ROOT/share/wps/Variable_Tables/Vtable.GFS
```

Check it before configuring a campaign:

```bash
test -x "$MONAN_JEDI_INSTALL_ROOT/bin/mpas_init_atmosphere"
test -x "$MONAN_JEDI_INSTALL_ROOT/bin/mpas_atmosphere"
test -x "$MONAN_JEDI_INSTALL_ROOT/bin/ungrib.exe"
test -x "$MONAN_JEDI_INSTALL_ROOT/bin/link_grib.csh"
test -f "$MONAN_JEDI_INSTALL_ROOT/share/wps/Variable_Tables/Vtable.GFS"
```

Do not point MPASWF at MONAN-JEDI `work/`, source checkouts, or a versioned WPS
release directory. Those paths are private to the producer.

## 3. Install MPASWF

```bash
git clone https://github.com/joaogerd/mpaswf.git
cd mpaswf
python -m pip install --no-deps -e .
mpaswf --help
```

For repository development:

```bash
python -m pip install -e '.[dev]'
pytest
```

## 4. Understand the two configuration files

```text
configs/jaci-x1.10242.yaml
configs/mpas-x1.10242.yaml
```

`jaci-x1.10242.yaml` contains machine/site information:

```text
MONAN-JEDI installation root
work/data/template directories
mesh and partition inputs
PBS/MPI resources
runtime environment
```

`mpas-x1.10242.yaml` contains campaign/workflow information:

```text
valid times
24 h / 48 h forecast leads
GFS naming
WPS product naming and Vtable filename
MPAS output names
template filenames
validation rules
```

Users still pass only one file:

```bash
CONFIG=configs/jaci-x1.10242.yaml
```

## 5. Check the JACI platform paths

The shipped configuration contains:

```yaml
software:
  monan_jedi_root: /p/projetos/monan_das/$USER/build/monan-jedi
```

It also defines writable directories such as:

```text
/p/projetos/monan_das/$USER/work/mpaswf
/p/projetos/monan_das/$USER/data/gfs
```

and mesh/partition paths under the user's MPAS mesh repository.

Create only the writable campaign/data directories yourself. The MONAN-JEDI
installation must be produced by the MONAN-JEDI build/install workflow.

## 6. Validated templates remain separate

MPASWF requires the validated case templates named by `templates.*`. The standard
x1.10242 contract expects:

```text
namelist.wps.in
namelist.init_atmosphere.static.in
streams.init_atmosphere.static.in
namelist.init_atmosphere.in
streams.init_atmosphere.in
namelist.atmosphere.in
streams.atmosphere.in
```

Set `paths.cdct_templates_dir` to the directory containing the approved case.
These are scientific/runtime inputs and are not generic files that MPASWF should
invent automatically.

## 7. Configure the campaign

Campaign bounds are **valid times**. With:

```yaml
campaign:
  start_valid_time: "2026-06-22T00:00:00Z"
  end_valid_time: "2026-06-25T00:00:00Z"
  interval_hours: 24
  leads_hours: [24, 48]
```

for every valid time `T` MPASWF needs:

```text
T - 48 h -> f048 -> T
T - 24 h -> f024 -> T
```

This is the same-valid-time NMC pair consumed by MPAS-BMatrix.

## 8. Prepare GFS input

By default the workflow expects:

```text
<gfs_dir>/<YYYYMMDDHH>/gfs.tHHz.pgrb2.0p25.f000
```

When `gfs.url_template` is `null`, all required files must already exist.

## 9. Validate PBS/MPI first

Before a real model job:

```bash
mpaswf pbs-smoke --config "$CONFIG"
```

The smoke performs a real one-rank scheduler round trip and verifies compute-node
execution plus shared-filesystem visibility.

## 10. Run the workflow

### Prepare WPS products

```bash
mpaswf run --phase prepare --config "$CONFIG"
```

For each initialization time MPASWF links the installed:

```text
$MONAN_JEDI_INSTALL_ROOT/bin/link_grib.csh
$MONAN_JEDI_INSTALL_ROOT/bin/ungrib.exe
$MONAN_JEDI_INSTALL_ROOT/share/wps/Variable_Tables/Vtable.GFS
```

into the cycle work directory, renders `namelist.wps`, and creates the expected
`FILE:YYYY-MM-DD_HH` product.

### Static + atmospheric initialization

```bash
mpaswf run --phase init --config "$CONFIG" --submit --wait
```

The static product is generated once per mesh and then reused by the
date-dependent initialization cycles.

### Forecasts

```bash
mpaswf run --phase forecast --config "$CONFIG" --submit --wait
```

MPASWF runs the required f024/f048 integrations using:

```text
$MONAN_JEDI_INSTALL_ROOT/bin/mpas_atmosphere
```

### Manifest

```bash
mpaswf run --phase manifest --config "$CONFIG"
```

The final hand-off is:

```text
<work_dir>/products/mpas-forecast-manifest.tsv
```

## 11. Safe reruns

Existing valid outputs are reused. `--force` deliberately regenerates the
selected phase. Each stage keeps logs and `.mpaswf` metadata for diagnosis.

## 12. Backward compatibility

Existing self-contained configs that still define:

```yaml
executables:
  wps_dir: /old/WPS
  mpas_init: /old/bin/mpas_init_atmosphere
  mpas_atmosphere: /old/bin/mpas_atmosphere
```

remain supported. They are a compatibility path, not the recommended layout for
new JACI runs.

For all new installations, configure one `software.monan_jedi_root` instead.
