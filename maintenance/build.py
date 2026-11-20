#!/usr/bin/env python3
# SPDX-License-Identifier: BSD-3-Clause
"""Build an isolated ngspice executable and record its provenance."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess


def run(command, cwd, log, env=None, timeout=1800):
    log.parent.mkdir(parents=True, exist_ok=True)
    print(f"Running {command[0]}: {log}", flush=True)
    with log.open("w") as output:
        subprocess.run(command, cwd=cwd, env=env, stdout=output,
                       stderr=subprocess.STDOUT, check=True, timeout=timeout)


def configure(source, build, prefix, profile):
    source, build, prefix = map(lambda p: Path(p).resolve(), (source, build, prefix))
    if source == build or source in build.parents:
        raise ValueError("Use a build directory outside the source tree")
    build.mkdir(parents=True, exist_ok=True)
    if (build / "config.status").exists():
        raise ValueError(f"Build already configured: {build}; choose a fresh directory")
    if not (source / "configure").exists():
        run(["sh", "autogen.sh"], source, build / "logs/autogen.log")
    flags = [f"--prefix={prefix}", "--with-x=no", "--with-readline=no",
             "--enable-klu", "--disable-debug", "--disable-cider",
             "--enable-openmp" if profile == "openmp" else "--disable-openmp"]
    env = os.environ.copy()
    env["CFLAGS"] = "-O2 -g -std=gnu17"
    env.pop("LDFLAGS", None)
    run([str(source / "configure"), *flags], build, build / "logs/configure.log", env)
    return source, build, prefix, flags, env


def build_ngspice(source, build, prefix, profile="openmp", jobs=2):
    source, build, prefix, flags, env = configure(source, build, prefix, profile)
    run(["make", f"-j{jobs}"], build, build / "logs/build.log", env)
    run(["make", "install"], build, build / "logs/install.log", env)
    executable = prefix / "bin/ngspice"
    version = subprocess.check_output([str(executable), "--version"], text=True)
    commit = None
    if (source / ".git").exists():
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source,
                                         text=True).strip()
    info = {"source_commit": commit, "profile": profile, "configure_flags": flags,
            "cflags": env["CFLAGS"], "version": version,
            "compiler": subprocess.check_output(["cc", "--version"], text=True).splitlines()[0],
            "binary_sha256": hashlib.sha256(executable.read_bytes()).hexdigest()}
    info_path = prefix / "share/ngspice-ams/build-info.json"
    info_path.parent.mkdir(parents=True, exist_ok=True)
    info_path.write_text(json.dumps(info, indent=2) + "\n")
    return executable, info


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--build", type=Path, required=True)
    parser.add_argument("--prefix", type=Path, required=True)
    parser.add_argument("--profile", choices=["openmp", "serial"], default="openmp")
    parser.add_argument("--jobs", type=int, default=2)
    args = parser.parse_args()
    if args.jobs < 1:
        parser.error("--jobs must be positive")
    executable, info = build_ngspice(args.source, args.build, args.prefix, args.profile, args.jobs)
    print(json.dumps({"executable": str(executable), **info}, indent=2))
