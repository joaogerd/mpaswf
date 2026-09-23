# MPASWF documentation

The documentation is organized so a new user can learn the workflow from first
principles and then move to reference material.

## Recommended reading order

1. **[Getting started](getting-started.md)** — start here if you have never run
   MPAS/WPS or have never used MPASWF. It explains the terminology, external
   requirements, JACI setup, GFS/WPS preparation, PBS smoke test, MPAS static and
   initialization stages, f024/f048 forecasts, manifest generation, logs, reruns,
   and troubleshooting.
2. **[Configuration reference](configuration.md)** — field-by-field explanation
   of the split YAML model, merge rules, environment variables, template
   placeholders, PBS settings, validation, and backward compatibility.
3. **[JACI quasi-uniform mesh catalog](jaci-quasi-uniform-meshes.md)** — site
   inventory of the MPAS grid, graph, archive, and validated partition assets
   available under `projects/mpas_meshes/quasi_uniform`, including the rule for
   matching a partition to the configured MPI rank count.
4. **[Design](design.md)** — software boundaries, dependency layers,
   idempotence, and operational design decisions.
5. **[CD-CT mapping](cdct_mapping.md)** — mapping between the validated CD-CT
   reference responsibilities and MPASWF phases.

## Configuration files

The recommended JACI/x1.10242 configuration lives in [`../configs`](../configs):

```text
configs/
├── jaci-x1.10242.yaml   # machine/platform settings
└── mpas-x1.10242.yaml   # campaign/workflow contract
```

Both YAML files are heavily commented in English and are intended to be usable
as documentation while editing the configuration.

The user still passes a single file:

```bash
CONFIG=configs/jaci-x1.10242.yaml
```

The platform file loads the workflow contract internally. No existing MPASWF or
MPAS-BMatrix invocation needs to change.
