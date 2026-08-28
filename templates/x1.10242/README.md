# x1.10242 case templates

These templates are versioned with MPASWF because they are part of the scientific/runtime contract of the x1.10242 reference case, not compiled MONAN-JEDI software.

The WPS namelist is adapted from the CD-CT reference template:

- repository: `monanadmin/scripts_CD-CT`
- source commit: `46bea86f6843cde387c9192b524be3cd7780134f`
- source path: `scripts/namelists/namelist.wps.TEMPLATE`

Only placeholder syntax and the local rendering mechanism differ. The WPS semantics remain the CD-CT values, including `prefix = 'GFS'`.

Additional MPAS initialization/forecast templates are added here only after their runtime inputs and output contracts are validated end-to-end on JACI.
