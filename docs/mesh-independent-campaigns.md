# An example of a 15-km campaign

For the general configuration contract, **start with
[generic campaigns](generic-campaigns.md)**. This page preserves practical
details of one 15-km case; the provided timestep and number of vertical levels
are not validated defaults.

The strict init and forecast path uses the campaign mesh and PBS allocation.
`validation.require_staging_preflight: true` is the switch for mesh-aware
staging checks; it no longer means that x1.10242 or 128 ranks are required.

For the supplied 15-km campaign, add this to `mpas-x1.2621442.yaml`:

```yaml
mesh:
  name: x1.2621442
  nvertlevels: 55  # Confirm against the actual invariant and initial states.

runtime:
  config_dt: 90   # Existing campaign setting; stability is not validated here.
  output_interval: "24:00:00"
  forecast_namelist: /absolute/path/to/15km/namelist.atmosphere
  forecast_streams: /absolute/path/to/15km/streams.atmosphere
  stream_list_directory: /absolute/path/to/15km/support
  stream_lists:
    - stream_list.atmosphere.analysis
    - stream_list.atmosphere.background
    - stream_list.atmosphere.control
    - stream_list.atmosphere.ensemble
```

Use the actual case files and only the stream lists referenced by those files.
The forecast sources are complete MPAS namelist/XML files, not Python format
templates. MPASWF patches time, duration, timestep, decomposition, invariant,
initial-state input and NMC outputs; all other scientific settings remain in
the selected sources. Do not copy low-resolution physics or vertical-grid
settings without reviewing them. The example does not establish that 90 s or
55 levels is appropriate for a particular invariant/model build.

`runtime.physics_files` optionally replaces the default required MPAS table
list when selecting different physics. Tables are sourced from the installed
MPAS atmosphere share, not from a software source/build tree.

In `jaci-x1.2621442.yaml`, point `paths.cdct_templates_dir` at
`../templates/invariant` to use the shared invariant-init templates, or keep
the reviewed case-specific init templates. Shared init templates accept
`{nvertlevels}`, `{partition_prefix}`, `{static_filename}`, `{init_filename}`
and the standard time placeholders. The shared template retains the existing
invariant/GFS initialization settings; scientific vertical-grid parameters
must still match the selected case.

Keep the supplied `static.product_template`, invariant source and
`static.links` consistently on x1.2621442. Remove
`static.tutorial_physics_files` after declaring the explicit forecast sources
and stream-list directory. Relative source paths resolve from the platform
YAML passed to `--config`.

PBS `select` is the number of chunks; `mpiprocs` and `ncpus` are per chunk.
The launcher and partition use `select * mpiprocs` total ranks. For example,
4 chunks with 120 MPI ranks each require `*.graph.info.part.480`. Set queue,
CPU counts and walltimes to the actual machine; `select: 1, ncpus: 480` requests
480 CPUs in one chunk and must not be assumed to fit a JACI node.

Use separate work/static directories for every mesh and scientific campaign.
Strict campaigns record mesh/level identity in `.mpaswf/mesh.json`. A directory
with a different identity, or legacy outputs with no identity, is rejected
before cached forecast products can be reused. Preserve old outputs and select
a new work directory rather than deleting or relabeling the identity record.
Start with one valid date (one f024/f048 pair), validate model logs and state
dimensions, then expand the campaign. Passing staging tests does not replace
an MPAS execution on JACI.

The historical x1.10242 configuration can still read the old tutorial filenames
for compatibility. New campaigns must declare their forecast sources explicitly;
they cannot silently fall back to the 240-km namelist/streams.

The BMatrix consumer must independently select the same mesh, vertical-level
count and scientific contract. See its `docs/mesh-independent-campaigns.md`.

## Versioned NMC forecast lead pairs

MPASWF no longer assumes the historic f024/f048 lead pair in campaign
generation. Declare any **two distinct positive integer durations in hours**:

```yaml
campaign:
  start_valid_time: "2027-01-01T00:00:00Z"
  end_valid_time: "2027-01-10T00:00:00Z"
  interval_hours: 12
  leads_hours: [12, 36]

runtime:
  config_dt: 135  # Case-specific and scientifically validated, not a default.
  output_interval: "12:00:00"
```

Both forecasts have exactly the same final valid time. The longer lead
starts earlier and is subtracted from the shorter lead in the NMC/BFLOW
consumer (older-minus-newer). Model timestep, mesh and horizontal
resolution are independent settings.

For the MPAS-source-forecast staging path, the configured output interval
must divide **both lead durations exactly**, otherwise the selected MPAS
streams will not necessarily write at the required forecast valid time.
MPASWF checks this before launching that forecast.

The original `campaign.leads_hours: [24, 48]` continues to emit the
unchanged `monan-nmc-forecast-pairs-v1` TSV and JSON sidecar.

Other lead pairs emit `monan-nmc-forecast-pairs-v2`, with these TSV
columns:

```text
valid_time
older_lead_hours
newer_lead_hours
older_state
newer_state
older_restart
newer_restart
```

The sidecar includes `schema_version: 2`, the actual lead pair,
`pair_count`, exact column names, and a SHA-256 binding to the TSV.
No consumer needs to reconstruct MPASWF directories or infer a forecast
duration from a filename. Use the matching MPAS-BMatrix v2 reader and
configure `bflow.nmc.older_lead_hours` and
`bflow.nmc.newer_lead_hours` to the same pair.

**Scientific boundary:** this generalizes the *two-lead NMC pairing*,
not arbitrary ensemble statistics, FGAT or multi-lead variational schemes.
The value of B may change substantially with lead pair and the resulting
samples require independent statistical validation. The CI verifies
contract serialization and input geometry, not the numerical quality of
the resulting covariance on JACI.
