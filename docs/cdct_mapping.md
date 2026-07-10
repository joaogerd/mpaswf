# CD-CT mapping

| CD-CT responsibility | MPASWF phase | MPASWF implementation |
|---|---|---|
| GFS acquisition | `prepare` | Reuse valid local input or download configured URL |
| `link_grib.csh` + `ungrib.exe` | `prepare` | WPS working directory per initialization time |
| `make_static.bash` | `init` | One static `mpas_init_atmosphere` run in `paths.static_dir` |
| `make_initatmos.bash` | `init` | One dynamic initialization per required date |
| forecast script | `forecast` | One f024/f048 run directory per request |
| product list | `manifest` | Neutral TSV with da_state and restart products |

The first implementation renders approved CD-CT namelist and streams templates.
It does not invent dynamic-core, physics, or time-step settings.
