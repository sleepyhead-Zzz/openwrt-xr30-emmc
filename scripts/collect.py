#!/usr/bin/env python3
"""Publish only allowlisted public artifacts, never build signing private keys."""
import hashlib
import json
import os
import shutil
import subprocess
import tarfile
from pathlib import Path

repo = Path(__file__).resolve().parents[1]
source = repo / 'openwrt'
reports = repo / 'reports'
dest = repo / 'artifacts/candidate'
dest.mkdir(parents=True, exist_ok=True)
target = source / 'bin/targets/mediatek/filogic'
images = list(target.glob('*cmcc_xr30-emmc-*.itb'))
assert len(images) == 2
for name in ['rescue-image-checks.json', 'production-image-checks.json', 'defaults-checks.json', 'startup-checks.json', 'disk-checks.json', 'compatibility.json']:
    assert (reports / name).is_file(), name
compat = json.loads((reports / 'compatibility.json').read_text())
assert compat['indexes_verified'] and compat['dependency_checks'].startswith('passed')
for image in images:
    shutil.copy2(image, dest / image.name)
for name in ['startup-checks.json','disk-checks.json','defaults-checks.json']:
    assert json.loads((reports/name).read_text())['status'] == 'passed', name
shutil.copytree(repo / 'locks', dest / 'locks', dirs_exist_ok=True)
shutil.copytree(repo / 'docs', dest / 'docs', dirs_exist_ok=True)
shutil.copy2(repo/'scripts/verify_backup.py',dest/'verify_backup.py')
for p in reports.iterdir():
    if p.is_file() and p.suffix in ('.json', '.log', '.uci', '.manifest', '.dtb', '.txt'):
        shutil.copy2(p, dest / p.name)
shutil.copy2(source / '.config', dest / 'build.config')
linux = next(source.glob('build_dir/target-*/linux-mediatek_filogic/linux-6.12.94'))
shutil.copy2(linux / '.config.set', dest / 'kernel.config.set')
shutil.copy2(linux / '.config', dest / 'kernel.config.image')
shutil.copy2(linux / '.vermagic', dest / 'kernel.config-abi')
root = next(source.glob('build_dir/target-*/root-mediatek'))
shutil.copytree(root / 'etc/apk/keys', dest / 'apk-public-keys', dirs_exist_ok=True)
provenance = {'build_repository': 'https://github.com/' + os.environ['GITHUB_REPOSITORY'],
    'build_commit': os.environ['GITHUB_SHA'],
    'run': f'https://github.com/{os.environ["GITHUB_REPOSITORY"]}/actions/runs/{os.environ["GITHUB_RUN_ID"]}',
    'openwrt_commit': subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip(),
    'feeds': {p.name: subprocess.check_output(['git', '-C', str(p), 'rev-parse', 'HEAD'], text=True).strip()
              for p in (source / 'feeds').iterdir() if p.is_dir() and (p / '.git').exists()}}
(dest / 'provenance.json').write_text(json.dumps(provenance, indent=2) + '\n')
status = ('正式安装版构建及离线检查通过，磁盘启动与持久化尚未实机验证。\n'
          '正式 FIT：SquashFS + F2FS，production 系统分区为 12 GiB。\n'
          '救援 FIT：独立 initramfs，不自动挂载或格式化已有磁盘。\n'
          '数据区：ext4，XR30_DATA，/mnt/data；须在未来安装阶段显式格式化。\n'
          '官方 kmod 仓库：' + ('已通过 ABI、模块 vermagic 和依赖检查并启用。\n' if compat['official_kmods_enabled'] else '不匹配，已禁用；附同次构建模块。\n'))
(dest / 'STATUS.txt').write_text(status)
# The full target package index remains consistent with the supplied package files.
modules = repo / 'artifacts/same-build-packages'
modules.mkdir(parents=True, exist_ok=True)
with tarfile.open(modules / 'same-build-target-packages.tar.gz', 'w:gz') as tar:
    for p in sorted((target / 'packages').iterdir()):
        if p.is_file() and (p.suffix in ('.apk', '.adb') or p.name.endswith('.adb.sig')):
            tar.add(p, arcname='packages/' + p.name)
    for p in (root / 'etc/apk/keys').iterdir():
        if p.is_file():
            tar.add(p, arcname='public-keys/' + p.name)
for directory in [dest, modules]:
    lines = []
    for p in sorted(directory.rglob('*')):
        if p.is_file() and p.name != 'SHA256SUMS':
            lines.append(hashlib.sha256(p.read_bytes()).hexdigest() + '  ' + str(p.relative_to(directory)))
    (directory / 'SHA256SUMS').write_text('\n'.join(lines) + '\n')
print(status + provenance['run'])
