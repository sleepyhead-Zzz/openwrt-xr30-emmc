#!/usr/bin/env python3
"""Destructive test restricted to a newly-created sparse file and owned loop devices.
Never accepts a device path. Run with sudo on the disposable Linux CI runner.
"""
import hashlib,json,os,shutil,stat,subprocess,sys,tempfile,time
from pathlib import Path
repo=Path(__file__).resolve().parents[1]
root=(repo/'test-root').resolve()
image=next((repo/'openwrt/bin/targets/mediatek/filogic').glob('*cmcc_xr30-emmc-squashfs-sysupgrade.itb'))
layout=json.loads((repo/'reports/fit-layout.json').read_text())
offset=layout['overlay_offset']; sectors=120832000
assert os.geteuid()==0 and sys.platform=='linux'
# Supply only normal pseudo-devices, never bind-mount the host /dev tree.
for name,minor in [('null',3),('zero',5),('random',8),('urandom',9)]:
 p=root/'dev'/name
 if p.exists():
  st=p.lstat(); assert stat.S_ISCHR(st.st_mode) and st.st_rdev==os.makedev(1,minor)
 else:
  os.mknod(p,stat.S_IFCHR|0o666,os.makedev(1,minor))
for name in ['mounts','swaps','partitions']:
 (root/'proc'/name).write_text('')
assert 0<offset<128*1024**2 and offset%4096==0
loops=[]; mounts=[]; result={}
def run(*cmd,input=None):
 p=subprocess.run(list(map(str,cmd)),input=input,text=True,capture_output=True)
 if p.returncode: raise RuntimeError(f'{cmd}: {p.stdout}\n{p.stderr}')
 return p.stdout.strip()
def arm(script): return run('chroot',root,'/bin/sh','-ec',script)
def expose(dev,name):
 p=root/'dev'/name; st=os.stat(dev)
 p.unlink(missing_ok=True); os.mknod(p,0o600|0o60000,st.st_rdev)
 return '/dev/'+name
def digest(dev,offset=0,count=None):
 h=hashlib.sha256()
 with open(dev,'rb') as f:
  f.seek(offset)
  while count is None or count:
   b=f.read(4*1024**2 if count is None else min(count,4*1024**2))
   if not b: break
   h.update(b)
   if count is not None: count-=len(b)
 return h.hexdigest()
def mount(dev,target,typ=None,opts=None):
 target.mkdir(parents=True,exist_ok=True)
 cmd=['mount']+(['-t',typ] if typ else [])+(['-o',opts] if opts else [])+[dev,target]
 run(*cmd);mounts.append(target)
def unmount(target): run('umount',target);mounts.remove(target)
with tempfile.TemporaryDirectory(prefix='xr30-disk-ci-') as td:
 td=Path(td);disk=td/'sparse.img'
 with disk.open('wb') as f:f.truncate(sectors*512)
 try:
  loop=run('losetup','--find','--show','--partscan',disk);loops.append(loop)
  assert loop.startswith('/dev/loop') and Path(run('losetup','-n','-O','BACK-FILE',loop)).resolve()==disk.resolve()
  target=expose(loop,'xr30-test-disk')
  # Initial seven-partition table; all changes stay in this CI-owned loop file.
  initial='label: gpt\nunit: sectors\n\nstart=8192,size=1024,name="u-boot-env"\nstart=9216,size=4096,name="factory"\nstart=13312,size=4096,name="fip"\nstart=17408,size=65536,name="kernel"\nstart=82944,size=2097152,name="rootfs"\nstart=2180096,size=2097152,name="production"\nstart=4277248,size=114457567,name="data"\n'
  (root/'tmp/initial.sfdisk').write_text(initial)
  arm(f'sfdisk {target} < /tmp/initial.sfdisk')
  before=json.loads(run('sfdisk','--json',loop))['partitiontable']['partitions']
  markers={}
  for n in range(1,4):
   dev=f'{loop}p{n}'
   with open(dev,'r+b') as f:f.write((f'XR30-PRESERVE-{n}\n'*100).encode())
   markers[dev]=digest(dev)
  arm(f'sfdisk --delete {target} 4 5 6 7')
  (root/'tmp/final.sfdisk').write_text('start=18432,size=25165824,name="production"\nstart=25184256,size=95647711,name="data"\n')
  arm(f'sfdisk --append {target} < /tmp/final.sfdisk\nblockdev --rereadpt {target}')
  run('udevadm','settle')
  parts=json.loads(run('sfdisk','--json',loop))['partitiontable']['partitions']
  for a,b in zip(before[:3],parts[:3]): assert a==b,(a,b)
  assert len(parts)==5
  assert [(p['start'],p['size']) for p in parts]==[(8192,1024),(9216,4096),(13312,4096),(18432,25165824),(25184256,95647711)]
  run('sgdisk','--verify',loop)
  prod=expose(loop+'p4','xr30-test-production');data=expose(loop+'p5','xr30-test-data')
  assert int(run('blockdev','--getsize64',loop+'p4'))==12*1024**3
  arm(f'mkfs.ext4 -F -L XR30_DATA {data}')
  assert run('blkid','-s','LABEL','-o','value',loop+'p5')=='XR30_DATA'
  mount(loop+'p5',td/'data','ext4')
  (td/'data/keep.txt').write_text('XR30 data must survive sysupgrade and remount\n')
  unmount(td/'data')
  # Hash the entire data partition before/after actual official upgrade writes.
  data_hash=digest(loop+'p5')
  gpt=(digest(disk,0,34*512),digest(disk,(sectors-33)*512,33*512))
  shutil.copy2(image,root/'tmp/production.itb')
  arm('fwtool -i /dev/null -T /tmp/production.itb > /tmp/stripped.itb')
  raw_image=root/'tmp/stripped.itb'; raw_bytes=raw_image.stat().st_size; raw_hash=digest(raw_image)
  for board,expected in [('cmcc,xr30-emmc',0),('cmcc,rax3000m',1)]:
   (root/'tmp/sysinfo/board_name').write_text(board+'\n')
   code=arm('. /lib/functions.sh; . /lib/upgrade/fwtool.sh; v() { :; }; REQUIRE_IMAGE_METADATA=1; if fwtool_check_image /tmp/production.itb; then echo 0; else echo 1; fi')
   assert int(code)==expected,(board,code)
  (root/'tmp/sysinfo/board_name').write_text('cmcc,xr30-emmc\n')
  upgrade=f'''. /lib/upgrade/emmc.sh
get_image() {{ cat "$1"; }}
EMMC_KERN_DEV={prod}
UPGRADE_BACKUP=
# Upstream returns 1 when its final optional zeroing condition is false.
# Validate written blocks and bytes below; do not treat that as a flash failure.
upgrade_rc=0
emmc_upgrade_fit /tmp/production.itb || upgrade_rc=$?
test "$upgrade_rc" -eq 0 || {{ test "$upgrade_rc" -eq 1 && [ -n "$UPGRADE_BACKUP" ]; }}
test "$EMMC_KERNEL_BLOCKS" -gt 0
echo "$EMMC_KERNEL_BLOCKS" > /tmp/test-blocks
'''
  arm(upgrade)
  blocks=int((root/'tmp/test-blocks').read_text())
  assert blocks==(raw_bytes+511)//512
  assert digest(loop+'p4',0,raw_bytes)==raw_hash
  assert offset<=blocks*512<=offset+1024*1024
  fitrw=run('losetup','--find','--show','--offset',18432*512+offset,'--sizelimit',12*1024**3-offset,disk);loops.append(fitrw)
  rw=expose(fitrw,'xr30-test-fitrw')
  # Use the native ARM64 formatter shipped in the image.
  arm(f'mkfs.f2fs -f -l rootfs_data {rw}')
  mount(fitrw,td/'overlay','f2fs')
  stat=os.statvfs(td/'overlay'); capacity=stat.f_blocks*stat.f_frsize
  assert capacity>11*1024**3,capacity
  # Exercise file offsets beyond 4 GiB without allocating gigabytes of test data.
  with (td/'overlay/large-offset').open('wb') as f:
   f.seek(5*1024**3);f.write(b'XR30-64BIT-PERSISTENCE')
  (td/'overlay/upper').mkdir();(td/'overlay/work').mkdir()
  rootextent=next(e for e in layout['extents'] if e['component']=='rootfs')
  fit0=run('losetup','--find','--show','--read-only','--offset',18432*512+rootextent['offset'],'--sizelimit',rootextent['size'],disk);loops.append(fit0)
  mount(fit0,td/'rom','squashfs')
  mount('overlay',td/'merged','overlay',f'lowerdir={td}/rom,upperdir={td}/overlay/upper,workdir={td}/overlay/work')
  (td/'merged/etc/xr30-persist-test').write_text('persistent merged root\n')
  unmount(td/'merged');unmount(td/'rom');unmount(td/'overlay')
  mount(fitrw,td/'overlay','f2fs')
  with (td/'overlay/large-offset').open('rb') as f:
   f.seek(5*1024**3);assert f.read()==b'XR30-64BIT-PERSISTENCE'
  assert (td/'overlay/upper/etc/xr30-persist-test').read_text()=='persistent merged root\n'
  unmount(td/'overlay')
  # A second official upgrade including config-copy may destroy only production.
  (root/'tmp/config-backup').write_bytes(b'XR30-UPGRADE-CONFIG-MARKER\n')
  arm(upgrade.replace('UPGRADE_BACKUP=','UPGRADE_BACKUP=/tmp/config-backup')+'\nemmc_copy_config\n')
  with open(loop+'p4','rb') as f:
   f.seek(blocks*512);assert f.read(27)==b'XR30-UPGRADE-CONFIG-MARKER\n'
  assert digest(loop+'p4',0,raw_bytes)==raw_hash
  assert all(digest(dev)==value for dev,value in markers.items())
  assert digest(loop+'p5')==data_hash
  assert gpt==(digest(disk,0,34*512),digest(disk,(sectors-33)*512,33*512))
  mount(loop+'p5',td/'data','ext4','ro')
  assert (td/'data/keep.txt').read_text()=='XR30 data must survive sysupgrade and remount\n'
  unmount(td/'data')
  result={'status':'passed','disk_sectors':sectors,'sector_bytes':512,'partition_table':parts,'production_bytes':12*1024**3,'fitrw_bytes':12*1024**3-offset,'f2fs_capacity_bytes':capacity,'beyond_4GiB_file_io':True,'merged_root_persistence':True,'data_label':'XR30_DATA','data_full_partition_sha256_before_and_after':data_hash,'written_fit_payload_sha256':raw_hash,'upgrade_method':'image ARM64 emmc_upgrade_fit and emmc_copy_config against CI loop partition','preserved':['primary GPT','backup GPT','p1 contents and identity','p2 contents and identity','p3 contents and identity','entire p5 contents'],'limits':'Loop mappings reproduce FIT extents; this is not execution of the XR30 kernel fitblk driver or physical disk boot.'}
 finally:
  for m in mounts[::-1]: subprocess.run(['umount',str(m)],check=False)
  for l in loops[::-1]: subprocess.run(['losetup','-d',l],check=False)
(repo/'reports/disk-checks.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
