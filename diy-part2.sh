#!/usr/bin/env bash
# P3TERX template hook: after installing feeds. MIT, see LICENSE.
set -euo pipefail
repo="${GITHUB_WORKSPACE:-$(cd "$(dirname "$0")" && pwd)}"
python3 "$repo/scripts/configure.py" "$PWD"
make defconfig
mkdir -p "$repo/reports"
cp .config "$repo/reports/build.config"
./scripts/diffconfig.sh > "$repo/reports/build-diffconfig.txt"
python3 "$repo/scripts/configure.py" "$PWD" --check
