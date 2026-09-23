# JACI quasi-uniform MPAS mesh catalog

This page records the quasi-uniform MPAS meshes currently available on JACI for
MPASWF runs. These files are site assets: they are **not** versioned in this
repository because the NetCDF grids and mesh archives are large. MPASWF
configuration files should reference them by path.

Inventory snapshot: 2026-09-04.

## Site root

The catalog below is stored under:

```text
/p/projetos/monan_das/$USER/projects/mpas_meshes/quasi_uniform
```

Each mesh directory follows the same general layout:

```text
<mesh>_<nominal-resolution>/
├── README.md
├── archives/
├── graph/
├── mesh/
├── partitions/
└── static/
```

For the current inventory, every `static/` directory is empty.

## Available meshes

| Mesh directory | Nominal resolution | Grid file | Graph file | Available partition counts |
| --- | ---: | --- | --- | --- |
| `x1.1024002_24km` | 24 km | `mesh/x1.1024002.grid.nc` | `graph/x1.1024002.graph.info` | 16, 32, 64, 128, 144, 256, 288, 512, 576, 768, 1024, 1152, 1536, 2048 |
| `x1.10242_240km` | 240 km | `mesh/x1.10242.grid.nc` | `graph/x1.10242.graph.info` | 2, 4, 6, 8, 12, 16, 24, 32, 36, 48, 64, 128, 256 |
| `x1.163842_60km` | 60 km | `mesh/x1.163842.grid.nc` | `graph/x1.163842.graph.info` | 12, 16, 24, 32, 48, 64, 96, 128, 192, 256, 384, 512, 768, 1024 |
| `x1.256002_48km` | 48 km | `mesh/x1.256002.grid.nc` | `graph/x1.256002.graph.info` | 16, 20, 32, 36, 64, 128, 144, 256, 288, 512 |
| `x1.2562_480km` | 480 km | `mesh/x1.2562.grid.nc` | `graph/x1.2562.graph.info` | 2, 4, 6, 8, 12, 16 |
| `x1.2621442_15km` | 15 km | `mesh/x1.2621442.grid.nc` | `graph/x1.2621442.graph.info` | 240, 256, 480, 512, 960, 1024, 1920, 2048, 3840, 4096 |
| `x1.4002_384km` | 384 km | `mesh/x1.4002.grid.nc` | `graph/x1.4002.graph.info` | 2, 4, 6, 8, 12, 16, 20, 24, 32, 36 |
| `x1.40962_120km` | 120 km | `mesh/x1.40962.grid.nc` | `graph/x1.40962.graph.info` | 2, 4, 6, 8, 12, 16, 24, 36, 48, 64, 96, 128 |
| `x1.655362_30km` | 30 km | `mesh/x1.655362.grid.nc` | `graph/x1.655362.graph.info` | 48, 64, 96, 128, 192, 256, 384, 512, 768, 1024, 1536, 2048 |

## Archived mesh bundles

Each mesh directory also contains one archive under `archives/`:

| Mesh directory | Archive |
| --- | --- |
| `x1.1024002_24km` | `archives/x1.1024002.tar.gz` |
| `x1.10242_240km` | `archives/x1.10242.tar.gz` |
| `x1.163842_60km` | `archives/x1.163842.tar.gz` |
| `x1.256002_48km` | `archives/x1.256002.tar.gz` |
| `x1.2562_480km` | `archives/x1.2562.tar.gz` |
| `x1.2621442_15km` | `archives/x1.2621442.tar.gz` |
| `x1.4002_384km` | `archives/x1.4002.tar.gz` |
| `x1.40962_120km` | `archives/x1.40962.tar.gz` |
| `x1.655362_30km` | `archives/x1.655362.tar.gz` |

The archives are provenance/distribution assets. Normal MPASWF execution should
reference the extracted `mesh/`, `graph/`, and `partitions/` files instead of
unpacking archives inside a run directory.

## Partition selection rule

The suffix in a partition file is the number of MPI partitions represented by
that decomposition:

```text
<mesh>.graph.info.part.<N>
```

For example, the current x1.10242 JACI reference run uses 128 MPI ranks and
therefore stages:

```text
x1.10242_240km/partitions/x1.10242.graph.info.part.128
```

The configured MPI rank count and the staged partition must agree. Do not assume
that an arbitrary rank count is available: select one of the partition counts
listed in the table above or generate and validate a new partition explicitly.

## x1.10242 note

The `x1.10242_240km/graph/` directory contains an additional file named
`x1.10242.graph.info.part.64`. A 64-way partition also exists under the canonical
`partitions/` directory, and the two files have different byte sizes in the
2026-09-04 inventory. MPASWF configuration should use files under
`partitions/` unless the provenance of the alternate file has been established
and intentionally selected.

## MPASWF configuration example

The JACI x1.10242 platform configuration stages the grid, graph, and matching
partition as fixed symbolic links:

```yaml
static:
  links:
    - source: /p/projetos/monan_das/$USER/projects/mpas_meshes/quasi_uniform/x1.10242_240km/mesh/x1.10242.grid.nc
      target: x1.10242.grid.nc

    - source: /p/projetos/monan_das/$USER/projects/mpas_meshes/quasi_uniform/x1.10242_240km/graph/x1.10242.graph.info
      target: x1.10242.graph.info

    - source: /p/projetos/monan_das/$USER/projects/mpas_meshes/quasi_uniform/x1.10242_240km/partitions/x1.10242.graph.info.part.128
      target: x1.10242.graph.info.part.128
```

The corresponding PBS configuration uses `mpiprocs: 128`, matching the selected
partition.

## Refreshing the inventory

From the site root, the following commands are useful when this page needs to be
updated:

```bash
cd /p/projetos/monan_das/$USER/projects/mpas_meshes/quasi_uniform

find . -maxdepth 3 -type f \
  \( -name '*.grid.nc' -o -name '*.graph.info' -o -name '*.graph.info.part.*' -o -name '*.tar.gz' \) \
  -print | sort
```

To inspect file ownership, permissions, timestamps, and byte sizes:

```bash
ls -l */*
```

Update this catalog whenever meshes or validated partition files are added,
removed, or replaced on JACI.
