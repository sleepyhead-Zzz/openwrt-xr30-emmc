#!/usr/bin/env python3
"""Retain public build outputs for diagnosis; never promote them to a candidate."""
import hashlib
import json
import os
import shutil
import tarfile
from pathlib import Path

repo = Path(__file__).resolve().parents[1]
source = repo / 'openwrt'
if not source.is_dir():
    raise SystemExit(0)
dest = repo / 'reports/build-state'
dest.mkdir(parents=True, exist_ok=True)
patterns = [
    '.config', 'staging_dir/host/bin/apk',
    'build_dir/target-*/linux-mediatek_filogic/linux-6.12.94/.config',
    'build_dir/target-*/linux-mediatek_filogic/linux-6.12.94/.config.set',
    'build_dir/target-*/linux-mediatek_filogic/linux-6.12.94/.vermagic',
    'build_dir/target-*/linux-mediatek_filogic/linux-6.12.94/Module.symvers',
    'build_dir/target-*/linux-mediatek_filogic/linux-6.12.94/drivers/net/usb/asix.ko',
    'build_dir/target-*/root-mediatek/lib/apk/db/installed',
    'build_dir/target-*/root-mediatek/etc/apk/world',
    'build_dir/target-*/root-mediatek/etc/apk/repositories.d/*',
    'build_dir/target-*/root-mediatek/etc/apk/keys/*',
    'build_dir/target-*/fstools-*/libfstools/rootdisk.c',
    'build_dir/target-*/fstools-*/libfstools/partname.c',
    'build_dir/target-*/fstools-*/libfstools/fit.c',
    'bin/targets/mediatek/filogic/*cmcc_xr30-emmc-initramfs-recovery.itb',
]
manifest = []
for pattern in patterns:
    for p in source.glob(pattern):
        if not p.is_file():
            continue
        relative = p.relative_to(source)
        data = p.read_bytes()
        if '/keys/' in str(relative):
            assert b'PRIVATE KEY' not in data, 'private key in public-key directory'
        target = dest / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, target)
        manifest.append({'path': str(relative), 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()})
packages = source / 'bin/targets/mediatek/filogic/packages'
if packages.is_dir():
    with tarfile.open(dest / 'target-packages.tar.gz', 'w:gz') as tar:
        for p in sorted(packages.iterdir()):
            if p.is_file() and p.suffix in ('.apk', '.adb'):
                tar.add(p, arcname='packages/' + p.name)
(dest / 'manifest.json').write_text(json.dumps({
    'status': 'DIAGNOSTICS ONLY — NOT A VALIDATED BOOT CANDIDATE',
    'build_commit': os.environ.get('GITHUB_SHA'), 'run_id': os.environ.get('GITHUB_RUN_ID'),
    'files': manifest,
}, indent=2) + '\n')
(dest / 'NOT-A-CANDIDATE.txt').write_text(
    '诊断文件，不是已通过验收的试启动候选。不得因这里存在 ITB 而认为构建或验收成功。\n'
    '只有独立 candidate 产物及其完整验收结果才能表明离线检查通过；仍未实机验证。\n')
print(f'Retained {len(manifest)} public diagnostic files; no signing private keys included')
