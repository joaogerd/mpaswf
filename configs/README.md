# MPASWF configuration files

The recommended configuration separates site/runtime settings from the campaign
contract while keeping the CLI simple.

```text
configs/
├── jaci-x1.10242.yaml   # site, MONAN-JEDI root, mesh inputs, PBS/MPI
└── mpas-x1.10242.yaml   # campaign, GFS/WPS conventions, products, templates
```

Pass only the platform file:

```bash
CONFIG=configs/jaci-x1.10242.yaml

mpaswf pbs-smoke --config "$CONFIG"
mpaswf run --phase prepare  --config "$CONFIG"
mpaswf run --phase init     --config "$CONFIG" --submit --wait
mpaswf run --phase forecast --config "$CONFIG" --submit --wait
mpaswf run --phase manifest --config "$CONFIG"
```

## Site/runtime file

`jaci-x1.10242.yaml` answers **where and how the workflow runs**. Its most
important software setting is one public MONAN-JEDI prefix:

```yaml
software:
  monan_jedi_root: /p/projetos/monan_das/$USER/build/monan-jedi
```

From that root MPASWF derives:

```text
bin/mpas_init_atmosphere
bin/mpas_atmosphere
bin/ungrib.exe
bin/link_grib.csh
share/wps/Variable_Tables/Vtable.GFS
```

Do not configure a WPS source/build/release directory for normal use. Those are
private to MONAN-JEDI.

The same platform file also owns:

- workflow/data directories;
- mesh and partition input paths;
- validated template directory;
- local/PBS backend selection;
- queue, CPU/MPI resources, walltimes and runtime environment.

## Workflow/campaign file

`mpas-x1.10242.yaml` answers **what is produced**:

- requested valid times;
- f024/f048 forecast leads;
- GFS filename/acquisition convention;
- WPS intermediate naming and Vtable filename;
- expected MPAS products;
- template filenames;
- static-product reference time/name;
- validation rules.

It deliberately contains no installed-software paths.

## Composition

The platform file contains:

```yaml
workflow:
  configuration: mpas-x1.10242.yaml
```

MPASWF loads the workflow contract first and deep-merges the platform document
over it. Nested mappings are merged recursively and lists are replaced atomically.

## Environment variables

Environment variables are expanded recursively. The standard JACI configuration
therefore resolves `$USER` automatically, including the default MONAN-JEDI
installation:

```text
/p/projetos/monan_das/$USER/build/monan-jedi
```

## Backward compatibility

Historical self-contained YAMLs remain supported. If no
`software.monan_jedi_root` is configured, MPASWF still accepts the legacy keys:

```yaml
executables:
  wps_dir: /legacy/WPS
  mpas_init: /legacy/bin/mpas_init_atmosphere
  mpas_atmosphere: /legacy/bin/mpas_atmosphere
```

and legacy `wps.vtable` templates using `{wps_dir}`. These keys are maintained to
avoid breaking existing experiments; new site configurations should use the
single MONAN-JEDI root.

See [docs/getting-started.md](../docs/getting-started.md) and
[docs/configuration.md](../docs/configuration.md).
