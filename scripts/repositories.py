#!/usr/bin/env python3
"""Download USTC indexes, verify official signatures, and gate official kmods."""
import concurrent.futures
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BASE = 'https://mirrors.ustc.edu.cn/openwrt/releases/25.12.5/'
KMOD = 'targets/mediatek/filogic/kmods/6.12.94-1-5a6c1f71be683ae9980b15d3ce73e24d/packages.adb'
PATHS = ['targets/mediatek/filogic/packages/packages.adb'] + [
    f'packages/aarch64_cortex-a53/{name}/packages.adb'
    for name in ['base', 'luci', 'packages', 'routing', 'telephony', 'video']
] + [KMOD]


def run(args, log):
    p = subprocess.run([str(a) for a in args], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    with log.open('a') as f:
        f.write('$ ' + ' '.join(str(a) for a in args) + '\n' + p.stdout + '\n')
    if p.returncode:
        print(p.stdout, file=sys.stderr)
        raise RuntimeError(f'{args[0]} failed ({p.returncode}); see {log}')
    return p.stdout


def download_indexes(reports):
    dest = reports / 'indexes'
    dest.mkdir(parents=True, exist_ok=True)
    def fetch(item):
        i, path = item
        url = BASE + path
        request = urllib.request.Request(url, headers={'User-Agent': 'XR30-OpenWrt-build-validation/1.0'})
        with urllib.request.urlopen(request, timeout=120) as response:
            # Never accept a silent redirect to a different mirror.
            assert response.url.startswith(BASE), response.url
            data = response.read()
            assert response.status == 200 and len(data) > 100, url
        name = f'{i:02d}.adb'
        (dest / name).write_bytes(data)
        return {'url': url, 'file': name, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
    records = []
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            for result in pool.map(fetch, enumerate(PATHS)):
                records.append(result)
    finally:
        (reports / 'index-downloads.json').write_text(json.dumps(records, indent=2) + '\n')
    return records


def vermagic(data):
    m = re.search(rb'vermagic=([^\0]+)', data)
    if not m:
        raise ValueError('ELF module vermagic not found')
    return m[1].decode()


def main():
    reports = REPO / 'reports'
    reports.mkdir(exist_ok=True)
    if sys.argv[1] == 'download':
        print(json.dumps(download_indexes(reports), indent=2))
        return
    source = Path(sys.argv[2]).resolve()
    root = next(source.glob('build_dir/target-*/root-mediatek'))
    apk = source / 'staging_dir/host/bin/apk'
    keys = root / 'etc/apk/keys'
    assert apk.is_file() and any(keys.iterdir()), 'apk host tool / signing keys missing'
    log = reports / 'apk-validation.log'
    records = json.loads((reports / 'index-downloads.json').read_text())
    assert len(records) == len(PATHS)
    for record in records:
        run([apk, '--keys-dir', keys, 'verify', reports / 'indexes' / record['file']], log)
        record['signature_verified'] = True
    (reports / 'index-downloads.json').write_text(json.dumps(records, indent=2) + '\n')

    linux = next(source.glob('build_dir/target-*/linux-mediatek_filogic/linux-6.12.94'))
    config_abi = (linux / '.vermagic').read_text().strip()
    expected = json.loads((REPO / 'locks/sources.json').read_text())['official_kernel']
    kernel_package = f'{expected["version"]}~{config_abi}-r{expected["release"]}'
    module = next(linux.rglob('asix.ko'))
    built_magic = vermagic(module.read_bytes())
    (reports / 'kernel-abi-observed.json').write_text(json.dumps({
        'built_config_abi': config_abi, 'official_config_abi': expected['config_abi'],
        'built_kernel_package': kernel_package, 'built_module_vermagic': built_magic,
    }, indent=2) + '\n')
    official_repos = reports / 'official-all-repositories.list'
    official_repos.write_text('\n'.join(BASE + p for p in PATHS) + '\n')
    sandbox = REPO / 'apk-sandbox'
    sandbox.mkdir(exist_ok=True)
    # fetch opens the repository database with NO_STATE and does not need an
    # installed-package database. --initdb belongs to apk add, not apk fetch.
    common = [apk, '--root', sandbox, '--arch', 'aarch64_cortex-a53',
              '--keys-dir', keys, '--repositories-file', official_repos, '--no-cache']
    fetched = reports / 'official-module'
    fetched.mkdir(exist_ok=True)
    run(common + ['fetch', '--output', fetched, 'kmod-usb-net-asix'], log)
    package = next(fetched.glob('kmod-usb-net-asix-*.apk'))
    run([apk, '--keys-dir', keys, 'verify', package], log)
    extracted = fetched / 'extracted'
    extracted.mkdir(exist_ok=True)
    run([apk, '--keys-dir', keys, 'extract', '--destination', extracted, package], log)
    official_magic = vermagic(next(extracted.rglob('asix.ko')).read_bytes())
    match = config_abi == expected['config_abi'] and built_magic == official_magic
    active = [p for p in PATHS if p != KMOD or match]
    output = source / 'files/etc/apk/repositories.d/distfeeds.list'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text('# USTC paths; signed indexes verified during this build.\n' +
                      '\n'.join(BASE + p for p in active) + '\n' +
                      ('' if match else '# Official kmods disabled: kernel ABI/vermagic mismatch; use same-build modules.\n'))
    result = {'indexes_verified': True, 'built_config_abi': config_abi,
              'official_config_abi': expected['config_abi'], 'built_kernel_package': kernel_package,
              'built_module_vermagic': built_magic, 'official_module_vermagic': official_magic,
              'official_module_sha256': hashlib.sha256(package.read_bytes()).hexdigest(),
              'official_kmods_enabled': match, 'kernel_or_module_checks_bypassed': False,
              'dependency_checks': 'pending final image rootfs'}
    (reports / 'compatibility.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
