# JACI WPS functional smoke test

This procedure validates the runtime boundary between MONAN-JEDI and MPASWF:
MONAN-JEDI publishes WPS, and the MPASWF `prepare` phase consumes a real local
GFS GRIB2 file to produce the `FILE:*` intermediate used by
`mpas_init_atmosphere`.

## Runtime contract

The preferred MONAN-JEDI installation is:

```text
/p/projetos/monan_das/${USER}/builds/monan-jedi/
  bin/ungrib.exe
  bin/link_grib.csh
  share/wps/Vtable
```

Configure:

```yaml
executables:
  wps_dir: /p/projetos/monan_das/USER/builds/monan-jedi

wps:
  vtable: "{wps_root}/share/wps/Vtable"
```

`executables.wps_dir` may also point directly to the `bin` directory. MPASWF
records the resolved runtime paths in each cycle's `.mpaswf/wps.json` file.

## Input layout

For each initialization time MPASWF expects:

```text
<paths.gfs_dir>/<YYYYMMDDHH>/gfs.t<HH>z.pgrb2.0p25.f000
```

The campaign section contains forecast valid times. With leads 24 and 48 hours,
a single valid time requires two initialization analyses. For example:

```yaml
campaign:
  start_valid_time: "2026-06-24T00:00:00Z"
  end_valid_time: "2026-06-24T00:00:00Z"
  interval_hours: 6
  leads_hours: [24, 48]
```

requires:

```text
2026062200/gfs.t00z.pgrb2.0p25.f000
2026062300/gfs.t00z.pgrb2.0p25.f000
```

## Run

Activate the environment containing MPASWF and load any site runtime environment
required by the published WPS executable. Then run:

```bash
mpaswf run --phase prepare --config config.yaml
```

Use `--force` to regenerate WPS products while reusing valid local GFS inputs:

```bash
mpaswf run --phase prepare --config config.yaml --force
```

## Validate

Expected products:

```text
<paths.work_dir>/wps/2026062200/FILE:2026-06-22_00
<paths.work_dir>/wps/2026062300/FILE:2026-06-23_00
```

Inspect:

```bash
find <paths.work_dir>/wps -maxdepth 2 -type f -name 'FILE:*' -size +0c -ls
find <paths.work_dir>/wps -path '*/logs/ungrib.stdout.log' -exec tail -n 40 {} \;
find <paths.work_dir>/wps -path '*/.mpaswf/wps.json' -exec cat {} \;
```

A non-empty `FILE:*` for every required initialization time completes the real
GRIB2-to-WPS functional validation. The following `init` phase consumes these
files through the configured `FILE` meteorological prefix.
