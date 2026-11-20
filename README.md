# AMS maintained ngspice

This fork maintains our ngspice changes independently of upstream review.
The default `ams` branch starts from **ngspice 47**, official commit
`a80f6e3e95d51534905b1f23410a951802666656`. The authoritative upstream remains
[the SourceForge repository](https://sourceforge.net/p/ngspice/ngspice/).
GitHub records the fork through the SourceForge mirror linked by the ngspice
download page; source updates are fetched directly from SourceForge.

Our first change parallelizes BSIM4 transient timestep-limit checks for
versions 4.5, 4.6.5, 4.7 and 4.8.3. It reuses the existing OpenMP instance
arrays, calculates a local limit per thread, and reduces the minimum.
It requires at least 256 instances per requested thread; smaller workloads
and builds without OpenMP retain the serial path. Device equations and
integration tolerances are unchanged. Matrix factorization remains unchanged.
The upstream submission is [patch #142](https://sourceforge.net/p/ngspice/patches/142/).

## Build

On Ubuntu 22.04, install `build-essential autoconf automake libtool bison flex
python3 perl`. Use explicit build and install directories outside the source
checkout:

```sh
python3 maintenance/build.py --build /data/ngspice-build \
  --prefix /data/ngspice-install --profile openmp --jobs 16
/data/ngspice-install/bin/ngspice --version
```

The installed `share/ngspice-ams/build-info.json` records the source commit,
compiler, flags and binary hash. The executable keeps upstream's version
string; identify this fork by its Git tag/commit and that build record.
The initial downstream release identifier is `ams-47.1`.

## Validate

```sh
python3 maintenance/validate.py --work /data/ngspice-check-openmp \
  --profile openmp --jobs 16 --extended
python3 maintenance/validate.py --work /data/ngspice-check-serial \
  --profile serial --jobs 16
python3 maintenance/validate.py --work /data/ngspice-check-sanitizers \
  --profile sanitizers
```

Each command requires a new output directory. The pinned original source is
extracted from Git history, so use a full clone. There are no PDK downloads,
external model files or private container images required by these tests.

Validation covers:

- 33,792 direct comparisons against independently compiled original serial
  routines, across all four model versions, charge-state options, integration
  orders and workload boundaries;
- optional 36,864 additional comparisons using actual 1/8/16/32-thread teams;
- eight complete transient pairs per executable profile, including supply
  current, with finite and switching outputs and byte-identical saved arrays;
- upstream `make check` for both builds and all 198 BSIM4 NMOS/PMOS QA output
  files compared directly between them;
- ASan/UBSan checks of the direct regression harness (leak detection disabled).

The sanitizer profile checks the truncation routines and their harness;
it does not claim a sanitizer-clean full simulator. Legacy CMC `DIFFER`
messages against old reference data are recorded separately from differences
introduced by our changes. A process exit status alone is insufficient.

GitHub Actions runs OpenMP, non-OpenMP and sanitizer profiles on pushes and
pull requests to `ams`. Logs and `result.json` are retained as CI artifacts.
The extended thread checks are also available through manual workflow dispatch.
Oversubscribed CI runs test correctness, not speedup.

## Maintenance

`maintenance/upstream.json` pins the baseline and lists our patches.
Run `sh maintenance/sync-upstream.sh` to fetch official stable/development
refs and inspect pending changes. It does not change the checked-out branch.

Develop fixes on topic branches, include a reproducer, and run the profiles
above before adopting them on `ams`. Update the baseline manifest only as
part of a reviewed upstream integration, then repeat the paired comparisons.
Keep downstream fixes as separate commits and remove redundant patches when
upstream adopts them. Tag validated snapshots instead of making consumers
follow a moving branch. Upstream acceptance is not a prerequisite for using
a validated downstream snapshot.

The original project documentation is in [README](README) and the original
licenses and attribution remain in [COPYING](COPYING).
