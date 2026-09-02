# x1.10242 case templates

These templates are versioned with MPASWF because they are part of the scientific/runtime contract of the x1.10242 reference case, not compiled MONAN-JEDI software.

## WPS

The WPS namelist is adapted from the CD-CT reference template:

- repository: `monanadmin/scripts_CD-CT`
- source commit: `46bea86f6843cde387c9192b524be3cd7780134f`
- source path: `scripts/namelists/namelist.wps.TEMPLATE`

Only placeholder syntax and the local rendering mechanism differ. The WPS semantics remain the CD-CT values, including `prefix = 'GFS'`.

## MPAS initialization

The initialization templates encode the invariant-based x1.10242 setup previously used by the NMC/MPAS workflow in `joaogerd/mpas-bmatrix-global` (commit `6c96750306d2b2ebb0effb8d1cd266161a517aaa`). The relevant implementation is `src/mpas_workflow/mpas_init.py`.

The preserved contract is:

- reuse the consolidated `x1.10242.invariant.nc` rather than recomputing static fields from WPS_GEOG;
- 55 model vertical levels;
- `config_static_interp = .false.`;
- `config_native_gwd_static = .false.` and `config_native_gwd_gsl_static = .false.`;
- `config_vertical_grid = .true.` and `config_met_interp = .true.`;
- partition prefix `x1.10242.graph.info.part.`;
- one timestamped `x1.10242.init.<time>.nc` output.

The historical workflow used WPS prefix `FILE`; MPASWF now uses `GFS` because its WPS stage was validated end-to-end with the CD-CT `prefix = 'GFS'` contract. This is a naming alignment only; the same GFS f000 meteorological input is used.

The current MPASWF JACI run remains the authoritative integration validation for these versioned templates.
