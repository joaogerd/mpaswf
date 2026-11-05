# Optional generic MPAS initialization templates

These templates are **not tutorial defaults**. They are selected only when
the experiment sets `paths.cdct_templates_dir` and the corresponding
`templates.*` entries. The archived 240-km testcase keeps its own independent
templates, preserving its original numerical parameters.

The generic `namelist.init_atmosphere.in` uses:

- `mesh.nvertlevels` for the model's vertical resolution.
- `initialization.levels.nsoillevels` for MPAS soil layers.
- `initialization.levels.nfglevels` for forcing/first-guess levels.
- `initialization.levels.nfgsoillevels` for forcing soil layers.
- `initialization.levels.gocartlevels` for aerosol/GOCART levels.

These values have **different physical meanings** and cannot safely be
deduced from one another or from the horizontal mesh. Only supply settings
appropriate for the selected initialization inputs and model build.

Example structural configuration (not a scientifically recommended setup):

```yaml
mesh:
  name: custom-mesh
  nvertlevels: 72

initialization:
  levels:
    nsoillevels: 4
    nfglevels: 50
    nfgsoillevels: 4
    gocartlevels: 20
```

The actual choices depend on the land-surface configuration, meteorological
data source and MPAS aerosol/chemistry setup. A no-aerosol MPAS configuration
may permit zero GOCART levels; verify with the installed MPAS version.

Other physical namelist settings, such as `config_fg_interval`,
`config_ztop`, interpolation method and GFS-specific prefixes, remain in the
**selected template**, and must be reviewed for a non-GFS experiment.
Different init data sources should use their own case-specific templates.

MPASWF checks active template placeholders during `check-config` and reports
missing fields with their editable YAML paths before submitting HPC work.
Disabling strict staging checks never changes these rendered values.
