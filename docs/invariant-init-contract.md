# x1.10242 invariant-based MPAS initialization

The JACI x1.10242 reference campaign reuses a consolidated MPAS-JEDI invariant file instead of recomputing static fields from WPS_GEOG.

This follows the validated NMC/MPAS workflow previously implemented in `joaogerd/mpas-bmatrix-global`.

## Inputs

The initialization stage consumes:

- `${MONAN_JEDI_INSTALL_ROOT}/bin/mpas_init_atmosphere`;
- one validated WPS product `GFS:YYYY-MM-DD_HH` produced by the `prepare` phase;
- `x1.10242.invariant.nc` from the pinned MPAS-JEDI tutorial input set;
- `x1.10242.graph.info.part.128`;
- the repository-versioned x1.10242 init namelist and streams templates.

The invariant is staged as `x1.10242.static.nc` inside the MPAS init run directory. Its content, not its original filename, defines the invariant/static state used by MPAS.

## Scientific settings

The reference init preflight requires:

```text
config_init_case = 7
config_nvertlevels = 55
config_met_prefix = 'GFS'
config_sfc_prefix = 'GFS'
config_static_interp = .false.
config_native_gwd_static = .false.
config_native_gwd_gsl_static = .false.
config_vertical_grid = .true.
config_met_interp = .true.
config_block_decomp_file_prefix = 'x1.10242.graph.info.part.'
```

The output is:

```text
x1.10242.init.YYYY-MM-DD_HH.MM.SS.nc
```

## Validation

Before PBS submission, MPASWF verifies the invariant link, WPS product, partition file, rendered namelist and rendered streams contract.

After a submitted job completes, the reference configuration requires both the NetCDF product and a clean `log.init_atmosphere.0000.out` containing zero critical and ordinary error messages.

This preflight/postflight pair is intended to prevent a partially generated NetCDF from being accepted as a valid initialization.
