#!/usr/bin/env python3
import json
import shutil
import sys
from pathlib import Path
from repositories import run

repo = Path(__file__).resolve().parents[1]
source = Path(sys.argv[1]).resolve()
root = next(source.glob('build_dir/target-*/root-mediatek'))
reports = repo / 'reports'
result = json.loads((reports / 'compatibility.json').read_text())
sandbox = repo / 'apk-solver-root'
for path in ['lib/apk', 'etc/apk']:
    shutil.copytree(root / path, sandbox / path, dirs_exist_ok=True, symlinks=True)
apk = source / 'staging_dir/host/bin/apk'
args = [source / 'staging_dir/host/bin/fakeroot', apk, '--root', sandbox, '--arch', 'aarch64_cortex-a53', '--no-cache',
        '--keys-dir', root / 'etc/apk/keys',
        '--repositories-file', root / 'etc/apk/repositories.d/distfeeds.list']
log = reports / 'dependency-checks.log'
run(args + ['update'], log)
run(args + ['add', '--simulate', '--no-scripts', 'htop'], log)
if result['official_kmods_enabled']:
    run(args + ['add', '--simulate', '--no-scripts', 'kmod-usb-net-asix'], log)
    result['kmod_dependency_simulation'] = 'passed: official module and its kernel dependency resolve'
else:
    result['kmod_dependency_simulation'] = 'official kmods disabled; same-build target packages supplied'
result['dependency_checks'] = 'passed: signed index refresh and htop install simulation against the image package database'
(reports / 'compatibility.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result, indent=2))
