# MONAN-JEDI / MPASWF WPS contract

The responsibility boundary is intentionally strict:

- MONAN-JEDI builds, patches, validates, versions, and publishes WPS;
- MPASWF consumes the published runtime during `run --phase prepare`;
- MPASWF never edits or rebuilds the WPS source tree;
- the generated `FILE:*` products are consumed by `mpas_init_atmosphere`.

## Published layout

Preferred layout:

```text
<install-root>/
  bin/
    ungrib.exe
    link_grib.csh
  share/wps/
    Vtable
    Variable_Tables/
  wps/WPS-<version>/
    build-manifest.json
```

MPASWF accepts either `<install-root>` or `<install-root>/bin` through
`executables.wps_dir`. It resolves the actual binary directory and makes the
following render variables available:

- `wps_root`: installation root;
- `wps_bin_dir`: directory containing the two runtime programs;
- `wps_dir`: compatibility alias for `wps_bin_dir`.

## Prepare-phase behavior

For each required initialization time, MPASWF:

1. resolves and validates the WPS runtime and Vtable;
2. reuses a valid local GFS analysis or downloads it only when absent and a URL
   template is configured;
3. creates cycle-local links to `ungrib.exe`, `link_grib.csh`, and `Vtable`;
4. renders `namelist.wps` from the approved CD-CT template;
5. runs `link_grib.csh` and `ungrib.exe` without shell evaluation;
6. validates a non-empty configured `FILE:*` product;
7. records the resolved runtime and input/output paths in `.mpaswf/wps.json`.

`--force` applies to generated WPS products. It removes stale `GRIBFILE.*`,
`FILE:*`, and `PFILE:*` files and reruns the two WPS commands, while continuing
to reuse a valid local GFS input.
