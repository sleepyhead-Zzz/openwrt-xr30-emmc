#!/usr/bin/env python3
"""Restore authenticated public build evidence; never modify or rebuild the FIT."""
import hashlib
import json
import shutil
import subprocess
import tarfile
from pathlib import Path

repo = Path(__file__).resolve().parents[1]
saved = repo / 'saved/reports'
state = saved / 'build-state'
manifest = json.loads((state / 'manifest.json').read_text())
assert manifest['build_commit'] == '3c80df8e3363fcbf138976285868e5f1f514241a'
assert manifest['run_id'] == '38670311345'
source = repo / 'openwrt'
source.mkdir(exist_ok=True)
for record in manifest['files']:
    path = Path(record['path'])
    assert not path.is_absolute() and '..' not in path.parts
    src = state / path
    assert hashlib.sha256(src.read_bytes()).hexdigest() == record['sha256'], path
    dst = source / path
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
reports = repo / 'reports'
shutil.copytree(saved, reports, dirs_exist_ok=True, ignore=shutil.ignore_patterns('build-state'))
shutil.copytree(repo / 'saved/logs', repo / 'logs-original-build', dirs_exist_ok=True)
target = source / 'bin/targets/mediatek/filogic'
with tarfile.open(state / 'target-packages.tar.gz') as tar:
    assert all(m.isfile() and m.name.startswith('packages/') and '..' not in Path(m.name).parts for m in tar.getmembers())
    tar.extractall(target, filter='data')
image = json.loads((reports / 'image-checks.json').read_text())
assert hashlib.sha256((target / image['image']).read_bytes()).hexdigest() == image['sha256']
assert image['sha256'] == '3900ae0ced5f50561fef79ae4172f8d4a8c94dc31dd1ee815a7e4fd6ba4b31c5'

def metadata_checkout(path, url, commit):
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(['git', 'init', str(path)], check=True)
    subprocess.run(['git', '-C', str(path), 'fetch', '--depth=1', url, commit], check=True)
    # Record the exact source HEAD without replacing the saved build files.
    subprocess.run(['git', '-C', str(path), 'update-ref', 'HEAD', 'FETCH_HEAD'], check=True)

metadata_checkout(source, 'https://github.com/openwrt/openwrt.git', 'f0a60eee2fe051741c643ea6118718aae1ef17fb')
for line in (repo / 'locks/feeds.buildinfo').read_text().splitlines():
    _, name, spec = line.split()
    url, commit = spec.rsplit('^', 1)
    metadata_checkout(source / 'feeds' / name, url, commit)
apk = source / 'staging_dir/host/bin/apk'
apk.chmod(0o755)
(apk.parent / 'fakeroot').symlink_to('/usr/bin/fakeroot')
(reports / 'preserved-build-checks.json').write_text(json.dumps({
    'original_run': '38670311345', 'original_commit': manifest['build_commit'],
    'artifact_id': 11947707398,
    'artifact_sha256': '68856ba507d2077d23c0a1ecef7efc1e32cc370933f7842a93ce5f45a2a9d5a5',
    'verified_build_files': len(manifest['files']),
    'image_sha256': image['sha256'], 'image_changed': False,
}, indent=2) + '\n')
