#!/usr/bin/env bash
# P3TERX template hook: before updating feeds. MIT, see LICENSE.
set -euo pipefail
repo="${GITHUB_WORKSPACE:-$(cd "$(dirname "$0")" && pwd)}"
cp "$repo/locks/feeds.buildinfo" feeds.conf.default
cp -R "$repo/overlay/." .
cat "$repo/locks/xr30-image.mk" >> target/linux/mediatek/image/filogic.mk
patch -p1 < "$repo/locks/ram-only-startup.patch"
