#!/usr/bin/env python3
"""Audit the initramfs mount path and execute board-gated bootcount with spies."""
import json
import subprocess
import sys
from pathlib import Path

repo = Path(__file__).resolve().parents[1]
source = Path(sys.argv[1]).resolve()
root = Path(sys.argv[2]).resolve()
fstools = next(source.glob('build_dir/target-*/fstools-*'))
rootdisk = (fstools / 'libfstools/rootdisk.c').read_text()
assert 'get_rootdev("/")' in rootdisk and 'get_rootdev("/rom")' in rootdisk
assert 'if (!rootdev)\n\t\treturn NULL;' in rootdisk
assert 'strcmp(name, "rootfs_data")' in rootdisk
init = (root / 'init').read_text()
assert 'mount -t tmpfs tmpfs' in init and 'export INITRAMFS=1' in init
assert not (root / 'etc/config/fstab').exists()
assert not (root / 'sbin/block').exists()
assert not (root / 'usr/sbin/fw_setenv').exists()
rc_local = (root / 'etc/rc.local').read_text()
assert all(not line.strip() or line.lstrip().startswith('#') or line.strip() == 'exit 0' for line in rc_local.splitlines())
# Execute only the official bootcount function, replacing write commands with traps.
spy = '''board_name() { echo cmcc,xr30-emmc; }
fw_setenv() { echo unexpected-fw_setenv; exit 77; }
mtd() { echo unexpected-mtd; exit 77; }
dd() { echo unexpected-dd; exit 77; }
. /etc/init.d/bootcount
boot
'''
res = subprocess.run(['sudo', 'chroot', str(root), '/bin/sh'], input=spy, text=True, capture_output=True)
assert res.returncode == 0 and 'unexpected-' not in res.stdout + res.stderr, res.stdout + res.stderr
# Execute the late boot function with disk writers trapped and LED setup stubbed.
done = (root / 'etc/init.d/done').read_text().replace('. /etc/diag.sh', ':')
assert 'cmcc,xr30-emmc) ;;' in done
late_spy = '''board_name() { echo cmcc,xr30-emmc; }
mount_root() { echo unexpected-mount_root; exit 77; }
set_state() { :; }
sync() { :; }
'''
res = subprocess.run(['sudo', 'chroot', str(root), '/bin/sh'],
                     input=late_spy + done + '\nboot\n', text=True, capture_output=True)
assert res.returncode == 0 and 'unexpected-' not in res.stdout + res.stderr, res.stdout + res.stderr
report = {
    'status': 'passed static boot-path audit and board-gated bootcount execution',
    'root': 'initramfs /init copies the root to tmpfs and exports INITRAMFS=1',
    'preinit': '70_initramfs_test uses the RAM branch; 80_mount_root is not registered',
    'late_mount_root_done': 'explicit XR30 board gate skips mount_root done; executed with a failing mount_root spy',
    'block_automount': 'block-mount/blockd absent; no fstab',
    'uboot_environment': 'uboot-envtools and fw_env.config absent; XR30 does not match bootcount write cases',
    'dt_storage': 'eMMC factory nvmem only; no NAND/UBI or chosen rootdisk/production binding',
    'limits': 'No bootloader or full-system execution; no claim about user-issued writes or physical boot success',
    'hardware_tested': False,
}
(repo / 'reports/startup-checks.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, indent=2))
