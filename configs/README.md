# MPASWF configuration files

This directory contains the recommended split configuration used by MPASWF.
The goal is to keep machine-specific details separate from the workflow/campaign
contract while preserving the original command-line interface.

A first-time user should read [`docs/getting-started.md`](../docs/getting-started.md)
before editing these files. That guide explains the MPAS/WPS concepts, required
external files, installation checks, execution order, expected outputs, and
common failures.

## Files

```text
configs/
├── jaci-x1.10242.yaml   # platform: paths, executables, mesh assets, PBS/MPI
└── mpas-x1.10242.yaml   # workflow: campaign, GFS/WPS, products, templates
```

You do **not** execute these two files separately. Pass only the platform file:

```bash
CONFIG=configs/jaci-x1.10242.yaml

mpaswf pbs-smoke --config "$CONFIG"
mpaswf run --phase prepare  --config "$CONFIG"
mpaswf run --phase init     --config "$CONFIG" --submit --wait
mpaswf run --phase forecast --config "$CONFIG" --submit --wait
mpaswf run --phase manifest --config "$CONFIG"
```

The interface above is the same interface used by the MPAS-BMatrix forecast-pair
tutorial.

## Which file should I edit?

Edit `jaci-x1.10242.yaml` when the change is about **where or how the software
runs**:

- campaign/work/data directories;
- WPS installation;
- `mpas_init_atmosphere` and `mpas_atmosphere` executables;
- mesh, partition, invariant, tables, or other fixed support files;
- local versus PBS execution;
- PBS queue, CPU/MPI resources, walltime, modules, and environment variables.

Edit `mpas-x1.10242.yaml` when the change is about **what campaign is produced**:

- requested valid times;
- 24 h / 48 h forecast leads;
- GFS filename convention or acquisition URL;
- WPS intermediate filename convention;
- expected MPAS output filenames;
- source template filenames;
- static-product naming/reference time;
- output validation rules.

For ordinary use on JACI, most machine setup belongs in `jaci-x1.10242.yaml`,
while the most common campaign edit is the `campaign` block in
`mpas-x1.10242.yaml`.

## How the two files are connected

The platform file contains:

```yaml
workflow:
  configuration: mpas-x1.10242.yaml
```

MPASWF loads the workflow contract first and then deep-merges the platform file
over it. Nested mappings are combined recursively. Lists are atomic: if the
platform file defines a list, that list replaces the corresponding list instead
of being concatenated implicitly.

For example, the workflow contract can define:

```yaml
static:
  reference_time: "2010-10-23T00:00:00Z"
  product_template: "x1.10242.static.nc"
```

while the platform file defines only the machine-specific inputs:

```yaml
static:
  links:
    - source: /path/to/x1.10242.grid.nc
      target: x1.10242.grid.nc
```

The running workflow sees one merged `static` block containing all three keys.

## Environment variables

Environment variables are expanded recursively in YAML string values. This is
why the JACI configuration can use:

```yaml
paths:
  work_dir: /p/projetos/monan_das/$USER/work/mpaswf
```

Before a first run, verify every required path. The comments inside
`jaci-x1.10242.yaml` include concrete `test -d` / `test -x` checks and explain
what each path must contain.

## Backward compatibility

The historical single-YAML format remains supported. `examples/config.yaml` is
kept as a self-contained compatibility example. Therefore existing scripts may
continue to do:

```bash
mpaswf run --phase forecast --config "$MPASWF_CONFIG" --submit --wait
```

regardless of whether `$MPASWF_CONFIG` points to a complete single YAML or to a
platform YAML that references a workflow contract.

For the complete field-by-field reference, see
[`docs/configuration.md`](../docs/configuration.md).
