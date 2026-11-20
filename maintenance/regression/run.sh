#!/bin/sh
# Usage: sh run.sh BASELINE_SOURCE CANDIDATE_SOURCE CONFIGURED_BUILD OUTPUT [basic|extended]
set -eu
if [ "$#" -lt 4 ] || [ "$#" -gt 5 ]; then
    echo "usage: sh run.sh BASELINE_SOURCE CANDIDATE_SOURCE CONFIGURED_BUILD OUTPUT [basic|extended]" >&2
    exit 2
fi
baseline=$(cd "$1" && pwd)
candidate=$(cd "$2" && pwd)
build=$(cd "$3" && pwd)
mkdir -p "$4"
output=$(cd "$4" && pwd)
runner_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
mode=${5:-basic}
case "$mode" in
  basic) harness="$runner_dir/truncation_test.c" ;;
  extended) harness="$runner_dir/truncation_high_threads.c" ;;
  *) echo "invalid test mode: $mode" >&2; exit 2 ;;
esac
compiler=${CC:-cc}
for version in 45 46 47 48; do
    case "$version" in
      45) part=bsim4v5; stem=b4v5; prefix=BSIM4v5 ;;
      46) part=bsim4v6; stem=b4v6; prefix=BSIM4v6 ;;
      47) part=bsim4v7; stem=b4v7; prefix=BSIM4v7 ;;
      48) part=bsim4; stem=b4; prefix=BSIM4 ;;
    esac
    # Common candidate headers/configuration ensure identical struct layouts.
    # The renamed reference function is compiled from the original source tree.
    "$compiler" -O2 -g -fopenmp ${CFLAGS:-} \
        -I"$build/src/include" -I"$candidate/src/include" \
        -I"$candidate/src/spicelib/devices/$part" \
        -D"${prefix}trunc=baseline_${prefix}trunc" \
        -c "$baseline/src/spicelib/devices/$part/${stem}trunc.c" \
        -o "$output/baseline-$version.o"
    "$compiler" -O2 -g -fopenmp ${CFLAGS:-} \
        -I"$build/src/include" -I"$candidate/src/include" \
        -I"$candidate/src/spicelib/devices/$part" \
        -c "$candidate/src/spicelib/devices/$part/${stem}trunc.c" \
        -o "$output/candidate-$version.o"
    "$compiler" -O2 -g -fopenmp ${CFLAGS:-} \
        -I"$build/src/include" -I"$candidate/src/include" \
        -I"$candidate/src/spicelib/devices/$part" -DMODEL_VERSION="$version" \
        "$harness" "$candidate/src/spicelib/analysis/cktterr.c" \
        "$output/baseline-$version.o" "$output/candidate-$version.o" \
        -lm -o "$output/truncation-$version"
    "$output/truncation-$version"
done
