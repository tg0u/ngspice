Regression reproducer for parallel BSIM4 truncation

The reference and candidate functions are compiled separately. The reference is
the unchanged serial implementation in the baseline source tree, not a second
copy of the new parallel helper. Both use the candidate's common headers and
configuration so their structure layouts agree.

Requirements: an OpenMP-capable C compiler, libm, an original ngspice source tree,
the patched source tree, and a configured build directory for the patched tree.
No PDK, network connection, circuit input file or external simulator is needed.

Run from any directory (use absolute paths):
  sh tests/bsim4/truncation/run.sh BASELINE_SOURCE PATCHED_SOURCE CONFIGURED_BUILD RESULTS basic

The basic harness requests 1/2/4/8 threads and checks 33,792 combinations across
four BSIM4 versions. Set OMP_DYNAMIC=FALSE and allow at least eight OpenMP threads.

To reproduce the higher-thread-count boundary tests:
  sh tests/bsim4/truncation/run.sh BASELINE_SOURCE PATCHED_SOURCE CONFIGURED_BUILD RESULTS extended

The extended harness verifies actual 1/8/16/32-thread team sizes, exercises
4,095/4,096/4,097 and 8,191/8,192/8,193 instances, and checks 36,864 combinations.
Allow at least 32 OpenMP threads. Fewer allocated physical cores can still run
the correctness test with oversubscription, but should not be used for timing.

Both harnesses check incoming timestep limits, all enabled/disabled combinations
of NQS/body/gate charge states, trapezoidal orders 1/2 and Gear orders 1-6, and
multiple linked models. They compare doubles bit-for-bit and exit nonzero on any
mismatch. CFLAGS may add -fsanitize=address,undefined -fno-omit-frame-pointer.

To test the non-OpenMP production path, pass a configured build directory from
--disable-openmp. The harness still links OpenMP to control test threads, while
the production routines compile without USE_OMP and must stay serial.

All outputs go to the chosen RESULTS directory.

For this change, the unpatched pre-master-48 baseline is commit
03a0f71418b2d15419a61570eabfe794a403f5e8. For example, prepare it with:
  git worktree add --detach /absolute/path/ngspice-reference 03a0f71418b2d15419a61570eabfe794a403f5e8

These are explicit developer regression tests because they require a separate
unpatched source tree. They are distributed with the sources but are not part
of the ordinary make check suite. The existing NMOS/PMOS QA remains unchanged.
