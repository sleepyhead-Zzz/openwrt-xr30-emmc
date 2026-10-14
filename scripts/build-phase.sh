#!/usr/bin/env bash
set -euo pipefail
repo="$(cd "$(dirname "$0")/.." && pwd)"
phase="$1"
shift
mkdir -p "$repo/logs"
cd "$repo/openwrt"
# Bound both normal compilation and diagnostics to the requested concurrency.
if ! make -j4 "$@" 2>&1 | tee "$repo/logs/$phase.log"; then
  make -j1 V=s "$@" 2>&1 | tee "$repo/logs/$phase-retry.log"
fi
