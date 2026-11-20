#!/bin/sh
# SPDX-License-Identifier: BSD-3-Clause
# Fetch official refs and show pending changes without altering the work tree.
set -eu
cd "$(dirname "$0")/.."
git fetch --no-tags https://git.code.sf.net/p/ngspice/ngspice \
    refs/heads/master:refs/remotes/upstream/master \
    refs/heads/pre-master-48:refs/remotes/upstream/pre-master-48
baseline=$(python3 -c 'import json; print(json.load(open("maintenance/upstream.json"))["upstream_commit"])')
git log --oneline "$baseline..refs/remotes/upstream/master"
git log -10 --oneline refs/remotes/upstream/pre-master-48
