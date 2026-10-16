#!/usr/bin/env python3
"""Execute the image's boot gates in an isolated ARM64 chroot, in both modes."""
import json, subprocess, sys
from pathlib import Path
repo=Path(__file__).resolve().parents[1]
source=Path(sys.argv[1]).resolve(); root=Path(sys.argv[2]).resolve()
(root/'proc').mkdir(exist_ok=True)
(root/'tmp/sysinfo').mkdir(parents=True,exist_ok=True)
(root/'tmp/sysinfo/board_name').write_text('cmcc,xr30-emmc\n')
def run(script):
 r=subprocess.run(['sudo','chroot',str(root),'/bin/sh'],input=script,text=True,capture_output=True)
 assert r.returncode==0,(r.stdout,r.stderr)
 return r.stdout
assert 'export INITRAMFS=1' in (root/'init').read_text()
assert not (root/'usr/sbin/fw_setenv').exists()
fstools=next(source.glob('build_dir/target-*/fstools-*'))
assert 'v->size = (uint64_t)volsize << 9' in (fstools/'libfstools/fit.c').read_text()
assert 'BLKGETSIZE64' in (fstools/'libfstools/common.c').read_text()
results=[]
for rescue in [True,False]:
 (root/'proc/cmdline').write_text('console=ttyS0,115200n8 '+('rdinit=/init xr30_rescue=1' if rescue else 'root=/dev/fit0 rootwait fstools_overlay_fstype=f2fs')+'\n')
 done=(root/'etc/init.d/done').read_text().replace('. /etc/diag.sh',':')
 output=run('mount_root() { echo called-mount-root "$@"; }; set_state() { :; }; sync() { :; };\n'+done+'\nboot\n')
 assert ('called-mount-root done' in output) != rescue,output
 fstab=(root/'etc/init.d/fstab').read_text().replace('/sbin/block','block_spy')
 output=run('block_spy() { echo called-block "$@"; };\n'+fstab+'\nboot\n')
 assert ('called-block mount' in output) != rescue,output
 hotplug=(root/'etc/hotplug.d/block/10-mount').read_text().replace('/sbin/block','block_spy')
 output=run('block_spy() { echo called-block "$@"; }; ACTION=add;\n'+hotplug)
 assert ('called-block hotplug' in output) != rescue,output
 results.append({'mode':'rescue' if rescue else 'production','late_overlay_called':not rescue,'automount_called':not rescue})
run('board_name() { echo cmcc,xr30-emmc; }; fw_setenv() { exit 77; }; mtd() { exit 77; }; dd() { exit 77; };\n. /etc/init.d/bootcount\nboot\n')
platform=(root/'lib/upgrade/platform.sh').read_text()
for name in ['platform_do_upgrade','platform_check_image','platform_copy_config']:
 output=run('board_name() { echo cmcc,xr30-emmc; }; fit_do_upgrade() { echo FIT-UPGRADE; }; fit_check_image() { echo FIT-CHECK; }; emmc_copy_config() { echo EMMC-COPY; }; CI_METHOD=emmc;\n'+platform+'\n'+name+' /test.itb\n')
 assert {'platform_do_upgrade':'FIT-UPGRADE','platform_check_image':'FIT-CHECK','platform_copy_config':'EMMC-COPY'}[name] in output,output
fstab=(root/'etc/config/fstab').read_text()
for value in ["option label 'XR30_DATA'","option target '/mnt/data'","option fstype 'ext4'","option auto_mount '0'","option anon_mount '0'"]:
 assert value in fstab,value
report={'status':'passed','boot_gate_executions':results,'upgrade_dispatch':'official FIT/eMMC for cmcc,xr30-emmc','fstools_64bit_conversion':True,'data_formatting':'no custom formatting hook; label-based block-mount only','hardware_tested':False,'limits':'Chroot execution and source inspection, not full kernel boot.'}
(repo/'reports/startup-checks.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
