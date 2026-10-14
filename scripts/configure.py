#!/usr/bin/env python3
"""Preserve official kernel inputs, replace target selection and image options."""
import hashlib
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def options(text):
    result = {}
    for line in text.splitlines():
        m = re.match(r'(CONFIG_[^= ]+)=|# (CONFIG_[^ ]+) is not set', line)
        if m:
            result[m[1] or m[2]] = line
    return result


def main():
    source = Path(sys.argv[1])
    overrides = options((REPO / '.config').read_text())
    if '--check' in sys.argv:
        actual = options((source / '.config').read_text())
        required = ['TARGET_mediatek_filogic_DEVICE_cmcc_xr30-emmc',
                    'ALL_KMODS', 'TARGET_ROOTFS_INITRAMFS',
                    'TARGET_ROOTFS_INITRAMFS_SEPARATE', 'TARGET_INITRAMFS_COMPRESSION_GZIP',
                    'PACKAGE_xr30-emmc-support', 'PACKAGE_luci-i18n-base-zh-cn',
                    'PACKAGE_kmod-mt7915e', 'PACKAGE_dropbear']
        for key in required:
            assert actual.get('CONFIG_' + key) == f'CONFIG_{key}=y', key
        for key in ['IB', 'SDK', 'MAKE_TOOLCHAIN', 'TARGET_ROOTFS_SQUASHFS',
                    'TARGET_ROOTFS_EROFS', 'PACKAGE_block-mount', 'PACKAGE_uboot-envtools']:
            assert actual.get('CONFIG_' + key) != f'CONFIG_{key}=y', key
        for key, value in options((REPO / 'locks/config.buildinfo').read_text()).items():
            if key.startswith('CONFIG_KERNEL_'):
                assert actual.get(key) == value, (key, value, actual.get(key))
        print('Configuration checks passed: one XR30 target, official kernel options, RAM image only')
        return

    locks = json.loads((REPO / 'locks/sources.json').read_text())
    for name, info in locks['official_metadata'].items():
        assert hashlib.sha256((REPO / 'locks' / name).read_bytes()).hexdigest() == info['sha256']
    official = options((REPO / 'locks/config.buildinfo').read_text())
    result = {k: v for k, v in official.items() if not k.startswith('CONFIG_TARGET_DEVICE')}
    result.update(overrides)
    (source / '.config').write_text('\n'.join(result.values()) + '\n')


if __name__ == '__main__':
    main()
