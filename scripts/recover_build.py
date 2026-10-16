#!/usr/bin/env python3
"""Recover authenticated, unchanged build6 images for corrected offline validation."""
import gzip,hashlib,json,os,shutil,subprocess,tarfile,zipfile
from pathlib import Path
from verify_image import FDT,cpio_read
repo=Path(__file__).resolve().parents[1]
meta=json.loads((repo/'source-artifact.json').read_text())
assert str(meta['workflow_run']['id'])==os.environ['XR30_SOURCE_BUILD_RUN_ID']
assert meta['workflow_run']['head_sha']==os.environ['XR30_SOURCE_BUILD_COMMIT']
assert meta['name']=='xr30-emmc-diagnostics-6-1' and not meta['expired']
digest=hashlib.sha256((repo/'source-artifact.zip').read_bytes()).hexdigest()
assert meta['digest']=='sha256:'+digest,'GitHub artifact digest mismatch'
with zipfile.ZipFile(repo/'source-artifact.zip') as z:
 for info in z.infolist():
  p=Path(info.filename)
  assert not p.is_absolute() and '..' not in p.parts
  assert (info.external_attr>>16)&0o170000 != 0o120000,'archive symlink forbidden'
 z.extractall(repo/'saved')
saved=repo/'saved/reports'; state=saved/'build-state'
manifest=json.loads((state/'manifest.json').read_text())
assert manifest['build_commit']==os.environ['XR30_SOURCE_BUILD_COMMIT']
assert manifest['run_id']==os.environ['XR30_SOURCE_BUILD_RUN_ID']
source=repo/'openwrt';source.mkdir()
for rec in manifest['files']:
 p=Path(rec['path']);assert not p.is_absolute() and '..' not in p.parts
 original=state/p
 assert hashlib.sha256(original.read_bytes()).hexdigest()==rec['sha256'],p
 dest=source/p;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(original,dest)
shutil.copytree(saved,repo/'reports',dirs_exist_ok=True,ignore=shutil.ignore_patterns('build-state'))
shutil.copytree(repo/'saved/logs',repo/'logs-original-build',dirs_exist_ok=True)
target=source/'bin/targets/mediatek/filogic'
assert len(list(target.glob('*cmcc_xr30-emmc-*.itb')))==2,'Both original images required'
with tarfile.open(state/'target-packages.tar.gz') as t:
 assert all(m.isfile() and m.name.startswith('packages/') and '..' not in Path(m.name).parts for m in t.getmembers())
 t.extractall(target,filter='data')
# Decode only the authenticated original inline initrd, then rerun all FIT checks.
rescue=next(target.glob('*cmcc_xr30-emmc-initramfs-recovery.itb'))
fit=FDT(rescue.read_bytes()); name=fit.text('/configurations/config-1','ramdisk')
initrd=fit.nodes['/images/'+name]['data']; cpio_read(gzip.decompress(initrd))
(repo/'reports/initrd.cpio.gz').write_bytes(initrd)
root=repo/'test-root';root.mkdir()
subprocess.run(['sudo','bash','-c','gzip -dc "$1" | (cd "$2" && cpio -id --make-directories --no-absolute-filenames)','--',str(repo/'reports/initrd.cpio.gz'),str(root)],check=True)
subprocess.run(['sudo','chown','-hR',f'{os.getuid()}:{os.getgid()}',str(root)],check=True)
shutil.copy2('/usr/bin/qemu-aarch64-static',root/'usr/bin/qemu-aarch64-static')
(root/'dev').mkdir(exist_ok=True)
subprocess.run(['sudo','mknod','-m','666',str(root/'dev/null'),'c','1','3'],check=True)
actual_root=next(source.glob('build_dir/target-*/root-mediatek'))
shutil.copytree(root,actual_root,dirs_exist_ok=True,symlinks=True,ignore=shutil.ignore_patterns('dev'))
def metadata_checkout(path,url,commit):
 path.mkdir(parents=True,exist_ok=True)
 subprocess.run(['git','init',str(path)],check=True)
 subprocess.run(['git','-C',str(path),'fetch','--depth=1',url,commit],check=True)
 subprocess.run(['git','-C',str(path),'update-ref','HEAD','FETCH_HEAD'],check=True)
metadata_checkout(source,'https://github.com/openwrt/openwrt.git','f0a60eee2fe051741c643ea6118718aae1ef17fb')
for line in (repo/'locks/feeds.buildinfo').read_text().splitlines():
 _,name,spec=line.split();url,commit=spec.rsplit('^',1)
 metadata_checkout(source/'feeds'/name,url,commit)
fstools=next(source.glob('build_dir/target-*/fstools-*'))
audit_source=repo/'fstools-audit'
metadata_checkout(audit_source,'https://git.openwrt.org/project/fstools.git','16718b6e3c0fc7db7be6ae5848db0eae88ac8a8b')
(fstools/'libfstools/common.c').write_bytes(subprocess.check_output(['git','-C',str(audit_source),'show','HEAD:libfstools/common.c']))
host=source/'staging_dir/host/bin';(host/'apk').chmod(0o755)
(host/'fakeroot').symlink_to('/usr/bin/fakeroot')
# Use the actual image's fwtool under ARM64 emulation; no rebuilding or editing ITBs.
(host/'fwtool').write_text('#!/bin/sh\nexec /usr/bin/qemu-aarch64-static -L "'+str(root)+'" "'+str(root/'usr/bin/fwtool')+'" "$@"\n')
(host/'fwtool').chmod(0o755)
(repo/'reports/preserved-build-checks.json').write_text(json.dumps({'status':'passed','original_run':os.environ['XR30_SOURCE_BUILD_RUN_ID'],'original_commit':manifest['build_commit'],'artifact_id':meta['id'],'artifact_sha256':digest,'verified_build_files':len(manifest['files']),'images':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in target.glob('*cmcc_xr30-emmc-*.itb')},'image_changed':False},indent=2)+'\n')
print('Authenticated and recovered unchanged original images and build evidence')
