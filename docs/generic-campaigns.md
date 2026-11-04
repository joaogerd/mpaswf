# Mesh-independent campaigns

For a concrete, reproducible starting point, use
[the archived 240-km testcase](../testcase/tutorial-240km/README.md).
It is a selected experiment, not an implicit software default.

MPASWF is a generic MPAS forecast producer for NMC/BMatrix experiments. The
historical x1.10242 tutorial is **only a compatibility example**, not a source
of scientific settings for new meshes. A new campaign must provide its own
validated MPAS inputs and use its own directories.

## Configuration layout

Pass the site/platform YAML to the CLI. That YAML can include a
`workflow.configuration` pointing to the campaign YAML. The campaign YAML is
loaded first; the site YAML can override its fields.

Relevant **campaign YAML excerpt** (not a complete configuration):

```yaml
mesh:
  name: x1.163842          # Replace with your selected mesh.
  nvertlevels: 55          # Set to the actual number of levels in this case.

runtime:
  config_dt: 150           # Example only; choose and validate for your mesh.
  output_interval: "24:00:00"
  forecast_namelist: /absolute/path/to/your/case/namelist.atmosphere
  forecast_streams: /absolute/path/to/your/case/streams.atmosphere

validation:
  require_staging_preflight: true
```

The two `runtime.forecast_*` fields identify **complete MPAS case files**,
not Python templates. MPASWF updates the runtime-specific fields required for
the NMC forecast but preserves other scientific settings from those files.

Do not copy the tutorial timestep, physics, vertical grid, or stream settings
without independent validation. The numbers in this documentation are
illustrative and do not certify a stable configuration.

## Optional stream-list files

MPASWF detects `<file name="stream_list.*"/>` entries in the selected
`streams.atmosphere` XML when `runtime.stream_lists` is omitted. It searches
for these files alongside `runtime.forecast_streams` by default.

When the files are stored elsewhere, configure:

```yaml
runtime:
  stream_list_directory: /absolute/path/to/your/case/support
```

To override XML-based discovery, declare the exact list explicitly:

```yaml
runtime:
  stream_lists:
    - stream_list.atmosphere.analysis
```

Use `runtime.stream_lists: []` only if no external stream-list files are
required. For new campaigns there is **no inherited tutorial list**.

`runtime.physics_files` is optional: if supplied, MPASWF checks the named
files in the installed MPAS share directory. New campaigns inherit no
physics-file requirement from the old tutorial. The runtime still stages
the installed MPAS share files.

## Mesh identity and paths

The static/invariant state, mesh grid, graph, MPI partition, MPAS namelist,
streams, output product names, and directory names must agree with your
selected mesh and vertical grid. In the site YAML provide
`static.source`, `static.links`, `paths.work_dir`,
`paths.static_dir`, and the matching PBS allocation. The graph partition
must match the total MPI ranks (`pbs.select * pbs.mpiprocs`).

Use separate work/static directories for distinct meshes and campaigns.
Do not relabel or reuse a previous mesh's recorded identity or outputs.

## Configuration checks

```bash
mpaswf check-config --config configs/jaci-YOURMESH.yaml
mpaswf check-config --config configs/jaci-YOURMESH.yaml --verbose
mpaswf check-config --config configs/jaci-YOURMESH.yaml --json
```

The default command prints **only problems**, naming the editable YAML field
or a descriptive resource, the missing file path, and a correction. Use
`--verbose` to inspect all successful checks. Use `--json` for automation;
its diagnostic identifiers are not intended as user-editable configuration keys.

For example, when the two source fields are missing:

```text
1. runtime.forecast_namelist
   How to fix: Add runtime.forecast_namelist: /absolute/path/to/your/case/namelist.atmosphere under runtime: in your campaign YAML.
2. runtime.forecast_streams
   How to fix: Add runtime.forecast_streams: /absolute/path/to/your/case/streams.atmosphere under runtime: in your campaign YAML.
```

Start with one valid date and one f024/f048 pair. Review the MPAS logs and state
dimensions before increasing the campaign size.

## Backward compatibility

Existing tutorial-based x1.10242 configs using
`static.tutorial_physics_files` and
`validation.require_reference_preflight` still work. The old validation
option remains an alias for `validation.require_staging_preflight`;
when both are supplied, the new name takes precedence. These compatibility
behaviors are **not** templates for new campaigns.

Refer to [configuration.md](configuration.md) and
[jaci-quasi-uniform-meshes.md](jaci-quasi-uniform-meshes.md) for general
settings and available mesh assets.
