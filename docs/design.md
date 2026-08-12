# MPASWF design

## Scope

MPASWF is a focused producer for MPAS initialization and forecast products. It
uses CD-CT as the scientific/operational reference but does not execute CD-CT
shell scripts directly.

It owns:

- conditional GFS acquisition;
- WPS `link_grib` and `ungrib`;
- one-time mesh-level static interpolation;
- date-dependent `mpas_init_atmosphere` execution;
- f024/f048 `mpas_atmosphere` execution;
- conservative file validation and a neutral product manifest.

It does not own NMC differences, BFLOW, BUMP, JEDI, Obs2IODA, or scheduler
abstraction beyond a small PBS renderer.

## Configuration layers

The recommended configuration follows the same separation used by
MPAS-BMatrix:

```text
platform YAML
  paths + executables + mesh assets + execution/PBS
          |
          | workflow.configuration
          v
workflow contract YAML
  campaign + GFS/WPS contract + products + templates + validation
```

`load_config()` deep-merges the workflow contract with the platform document.
The platform is the override layer, so nested machine-specific values may be
changed without duplicating the campaign contract. Lists remain atomic and are
never concatenated implicitly.

This is an internal loading detail only. The public CLI still receives exactly
one `--config` argument. Historical self-contained YAML files remain valid.

## Dependency layers

```text
prepare
  GFS -> WPS FILE:*

init
  grid + partition + WPS_GEOG -> static.nc
  FILE:* + static.nc -> init state per date

forecast
  init state -> f024/f048 restart + da_state

manifest
  validated products -> neutral MPAS TSV
```

The static product is a real MPAS output. It is neither an immutable input nor
part of the `prepare` phase because it does not depend on GFS/WPS.

## Idempotence

A stage is reused only when its declared output exists and satisfies the
configured minimum-size validation. A missing static product prevents dynamic
initialization from advancing; a missing initial state prevents forecast
staging; incomplete forecast products prevent manifest generation.

## Terminal observability

Every operation with unbounded completion time emits an immediately visible
status. Interactive sessions render a braille spinner; redirected logs receive
line-oriented run/success/failure records. Progress remains concise while
persistent subprocess logs retain full WPS and MPAS output.
