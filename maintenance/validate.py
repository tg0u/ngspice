#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
"""Compare the maintained tree with its pinned, unmodified upstream baseline."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import traceback

from build import build_ngspice, configure, run


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = json.loads((ROOT / "maintenance/upstream.json").read_text())


def reference_tree(work):
    commit = MANIFEST["upstream_commit"]
    archive = work / "reference.tar"
    with archive.open("wb") as output:
        subprocess.run(["git", "archive", commit], cwd=ROOT, stdout=output, check=True)
    destination = work / "reference"
    destination.mkdir()
    with tarfile.open(archive) as tar:
        # The archive is a named commit from this repository, not an external upload.
        for member in tar.getmembers():
            target = (destination / member.name).resolve()
            if destination.resolve() not in target.parents and target != destination.resolve():
                raise ValueError(f"Unexpected archive path: {member.name}")
        tar.extractall(destination)
    archive.unlink()
    return destination


def direct_checks(reference, build, output, mode="basic", sanitize=False):
    env = os.environ.copy()
    env["OMP_DYNAMIC"] = "FALSE"
    env["OMP_THREAD_LIMIT"] = "32"
    if sanitize:
        env["CFLAGS"] = "-fsanitize=address,undefined -fno-omit-frame-pointer"
        env["ASAN_OPTIONS"] = "detect_leaks=0:abort_on_error=1"
        env["UBSAN_OPTIONS"] = "halt_on_error=1:print_stacktrace=1"
    else:
        env.pop("CFLAGS", None)
    log = output / "run.log"
    run(["sh", str(ROOT / "maintenance/regression/run.sh"), str(reference),
         str(ROOT), str(build), str(output), mode], ROOT, log, env, timeout=1800)
    records = [json.loads(line) for line in log.read_text().splitlines()
               if line.startswith('{"model_version":')]
    expected = 8448 if mode == "basic" else 9216
    if (len(records) != 4 or {r["model_version"] for r in records} != {45, 46, 47, 48}
            or any(r["checks"] != expected or not r["bit_identical"]
                   or r["active_timestep_reductions"] <= 0 for r in records)):
        raise AssertionError(f"Incomplete direct comparisons: {log}")
    return {"mode": mode, "sanitizers": sanitize, "log": str(log),
            "checks": sum(r["checks"] for r in records), "models": records}


def circuit(version, method, threads):
    lines = [f"AMS maintained BSIM4 {version} {method}",
             f".model nch nmos level=54 version={version} toxe=2.6n toxp=2.6n vth0=0.45 u0=0.04",
             f".model pch pmos level=54 version={version} toxe=2.6n toxp=2.6n vth0=-0.45 u0=0.02",
             "Vdd vdd 0 1.8"]
    for phase in range(8):
        lines.append(f"Vin{phase} in{phase} 0 pulse(0 1.8 {0.2 + phase * 0.01:.3f}n 50p 50p 0.8n 2n)")
    # 2,048 MOS devices cross the eight-thread activation boundary.
    for i in range(1024):
        lines += [f"Mn{i} out{i} in{i % 8} 0 0 nch w=1u l=180n",
                  f"Mp{i} out{i} in{i % 8} vdd vdd pch w=2u l=180n",
                  f"Cl{i} out{i} 0 {10 + i % 7}f"]
    lines += [f".option klu reltol=1e-5 abstol=1e-12 vntol=1e-8 method={method}",
              ".save v(in0) v(out0) i(vdd)", ".control", f"set num_threads={threads}",
              "set numdgt=17", "set wr_singlescale", "set wr_vecnames",
              "tran 20p 2n 0 20p", "wrdata wave.dat v(in0) v(out0) i(vdd)",
              "rusage all", "quit", ".endc", ".end"]
    return "\n".join(lines) + "\n"


def waveform(path):
    data = path.read_bytes()
    rows = [list(map(float, line.split())) for line in data.decode().splitlines()[1:] if line.strip()]
    if len(rows) < 100 or any(len(row) != 4 for row in rows):
        raise AssertionError(f"Incomplete waveform: {path}")
    if any(not math.isfinite(x) for row in rows for x in row):
        raise AssertionError(f"Non-finite waveform: {path}")
    if any(right[0] <= left[0] for left, right in zip(rows, rows[1:])):
        raise AssertionError(f"Non-increasing time: {path}")
    if rows[-1][0] < 2e-9 * (1 - 1e-8):
        raise AssertionError(f"Truncated transient: {path}")
    if max(row[2] for row in rows) - min(row[2] for row in rows) < 0.5:
        raise AssertionError(f"Output did not switch: {path}")
    return data, len(rows)


def transient_checks(baseline, candidate, output, profile):
    results = []
    threads = 8 if profile == "openmp" else 1
    for version in ["4.5.0", "4.6.5", "4.7.0", "4.8.3"]:
        for method in ["trap", "gear"]:
            waves = []
            for name, binary in [("baseline", baseline), ("candidate", candidate)]:
                folder = output / f"{version}-{method}" / name
                folder.mkdir(parents=True)
                (folder / "test.cir").write_text(circuit(version, method, threads))
                env = os.environ.copy()
                env["OMP_DYNAMIC"] = "FALSE"
                env["OMP_THREAD_LIMIT"] = "32"
                run([str(binary), "-n", "-b", "test.cir"], folder, folder / "run.log", env, timeout=300)
                waves.append(waveform(folder / "wave.dat"))
            if waves[0][0] != waves[1][0]:
                raise AssertionError(f"Transient differs: {version}/{method}")
            results.append({"version": version, "method": method, "threads": threads,
                            "rows": waves[0][1], "byte_identical": True,
                            "sha256": hashlib.sha256(waves[0][0]).hexdigest()})
    return results


def upstream_checks(build, label):
    log = build / "logs/upstream-check.log"
    run(["make", "check"], build, log, timeout=1800)
    text = log.read_text(errors="replace")
    passed = len(re.findall(r"^PASS:", text, re.MULTILINE))
    failed = len(re.findall(r"^(?:FAIL|ERROR|XPASS):", text, re.MULTILINE))
    if passed == 0 or failed:
        raise AssertionError(f"Incomplete or failed upstream tests in {label}")
    return {"passed": passed, "failed": failed,
            "legacy_cmc_DIFFER_diagnostics": text.count("DIFFER"), "log": str(log)}


def qa_compare(baseline_build, candidate_build):
    result = {}
    for kind in ["nmos", "pmos"]:
        collections = []
        for build in [baseline_build, candidate_build]:
            folder = build / "tests/bsim4" / kind / "results"
            collections.append({str(p.relative_to(folder)): p.read_bytes()
                                for p in folder.rglob("*") if p.is_file()})
        expected, actual = collections
        if len(expected) != 99 or expected.keys() != actual.keys():
            raise AssertionError(f"Incomplete BSIM4 {kind} QA outputs")
        differences = [name for name in expected if expected[name] != actual[name]]
        if differences:
            raise AssertionError(f"BSIM4 {kind} QA differs: {differences}")
        result[kind] = {"files": len(expected), "byte_identical": True}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, required=True, help="New output directory outside the source tree")
    parser.add_argument("--profile", choices=["openmp", "serial", "sanitizers"], default="openmp")
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument("--extended", action="store_true", help="Also check real 16/32-thread teams")
    args = parser.parse_args()
    work = args.work.resolve()
    if args.jobs < 1 or work == ROOT or ROOT in work.parents:
        parser.error("Use positive --jobs and an output directory outside the source tree")
    work.mkdir(parents=True, exist_ok=False)
    result = {"status": "running", "profile": args.profile, "upstream": MANIFEST,
              "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
              "compiler": subprocess.check_output(["cc", "--version"], text=True).splitlines()[0]}
    summary = work / "result.json"
    try:
        reference = reference_tree(work)
        if args.profile == "sanitizers":
            configure(ROOT, work / "candidate-build", work / "candidate-install", "openmp")
            result["direct"] = direct_checks(reference, work / "candidate-build", work / "direct", sanitize=True)
        else:
            baseline, baseline_info = build_ngspice(reference, work / "baseline-build",
                                                   work / "baseline-install", args.profile, args.jobs)
            candidate, candidate_info = build_ngspice(ROOT, work / "candidate-build",
                                                     work / "candidate-install", args.profile, args.jobs)
            result["builds"] = {"baseline": baseline_info, "candidate": candidate_info}
            result["direct"] = direct_checks(reference, work / "candidate-build", work / "direct")
            if args.extended:
                result["extended"] = direct_checks(reference, work / "candidate-build", work / "extended", "extended")
            result["transients"] = transient_checks(baseline, candidate, work / "transients", args.profile)
            result["upstream_checks"] = {
                "baseline": upstream_checks(work / "baseline-build", "baseline"),
                "candidate": upstream_checks(work / "candidate-build", "candidate")}
            if result["upstream_checks"]["baseline"]["passed"] != result["upstream_checks"]["candidate"]["passed"]:
                raise AssertionError("Different numbers of upstream tests executed")
            if (result["upstream_checks"]["baseline"]["legacy_cmc_DIFFER_diagnostics"]
                    != result["upstream_checks"]["candidate"]["legacy_cmc_DIFFER_diagnostics"]):
                raise AssertionError("Different numbers of legacy CMC diagnostics")
            result["bsim4_qa"] = qa_compare(work / "baseline-build", work / "candidate-build")
        result["status"] = "passed"
    except Exception as exc:
        result["status"] = "failed"
        result["error"] = str(exc)
        traceback.print_exc()
    finally:
        summary.write_text(json.dumps(result, indent=2) + "\n")
        print(f"{result['status']}: {summary}", flush=True)
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
