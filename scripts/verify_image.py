#!/usr/bin/env python3
"""Independently inspect the delivered FIT and the CPIO it actually contains."""
import gzip
import hashlib
import json
import lzma
import re
import struct
import sys
import zlib
import subprocess
import os
import tempfile
from pathlib import Path


def check(condition, message):
    if not condition:
        raise ValueError(message)


class FDT:
    def __init__(self, data):
        self.data = data
        h = struct.unpack_from('>10I', data)
        check(h[0] == 0xd00dfeed and h[1] <= len(data), 'invalid FDT header')
        self.size = h[1]
        strings = data[h[3]:h[3] + h[8]]
        pos, end, stack = h[2], h[2] + h[9], []
        self.nodes = {}
        while pos < end:
            token, = struct.unpack_from('>I', data, pos)
            pos += 4
            if token == 1:
                stop = data.index(0, pos, end)
                stack.append(data[pos:stop].decode())
                self.nodes['/' + '/'.join(stack[1:])] = {}
                pos = (stop + 4) & ~3
            elif token == 2:
                stack.pop()
            elif token == 3:
                length, off = struct.unpack_from('>II', data, pos)
                pos += 8
                name = strings[off:strings.index(0, off)].decode()
                check(pos + length <= end, 'property out of bounds')
                self.nodes['/' + '/'.join(stack[1:])][name] = data[pos:pos + length]
                pos = (pos + length + 3) & ~3
            elif token == 4:
                pass
            elif token == 9:
                break
            else:
                raise ValueError(f'unknown FDT token {token}')

    def text(self, node, prop):
        return self.nodes[node][prop].rstrip(b'\0').decode()

    def cells(self, node, prop):
        data = self.nodes[node][prop]
        return struct.unpack('>' + 'I' * (len(data) // 4), data)


def cpio_read(data):
    result, pos = {}, 0
    while pos + 110 <= len(data):
        check(data[pos:pos + 6] in (b'070701', b'070702'), 'invalid newc archive')
        fields = [int(data[pos + 6 + i * 8:pos + 14 + i * 8], 16) for i in range(13)]
        mode, size, namesize = fields[1], fields[6], fields[11]
        pos += 110
        name = data[pos:pos + namesize - 1].decode()
        pos = (pos + namesize + 3) & ~3
        if name == 'TRAILER!!!':
            return result
        name = name.removeprefix('./')
        check(not name.startswith('/') and '..' not in name.split('/'), 'unsafe CPIO path')
        check(pos + size <= len(data), 'truncated CPIO data')
        result[name] = {'mode': mode, 'data': data[pos:pos + size]}
        pos = (pos + size + 3) & ~3
    raise ValueError('CPIO trailer missing')


def installed_packages(data):
    result = {}
    for record in data.decode().split('\n\n'):
        values = dict(line.split(':', 1) for line in record.splitlines() if ':' in line)
        if 'P' in values:
            result[values['P']] = {k: values[k] for k in ('V', 'A', 'D') if k in values}
    return result


def verify(image, report_dir):
    data = image.read_bytes()
    fit = FDT(data)
    check(fit.text('/configurations', 'default') == 'config-1', 'default FIT config')
    rescue = 'initramfs-recovery' in image.name
    mode = 'rescue' if rescue else 'production'
    config = fit.nodes['/configurations/config-1']
    check(set(config) >= {'kernel', 'fdt', 'ramdisk' if rescue else 'loadables'}, 'FIT references incomplete')
    check(('loadables' not in config) if rescue else ('ramdisk' not in config), 'wrong boot path')
    alias = 'mt7981b-cmcc-rax3000m-emmc'
    ovname = fit.text('/configurations/' + alias, 'fdt')
    blobs, hashes, extents = {}, [], []
    refs = {k: config[k].rstrip(b'\0').decode() for k in ['kernel', 'fdt']}
    refs['ramdisk' if rescue else 'rootfs'] = config['ramdisk' if rescue else 'loadables'].rstrip(b'\0').decode()
    refs['overlay'] = ovname
    types = {'kernel':'kernel', 'fdt':'flat_dt', 'overlay':'flat_dt', 'ramdisk':'ramdisk', 'rootfs':'filesystem'}
    for key, name in refs.items():
        check('\0' not in name, 'unexpected multiple references')
        node = '/images/' + name
        check(fit.text(node, 'type') == types[key], key + ' type')
        check(fit.text(node, 'arch') == 'arm64', key + ' architecture')
        blob = fit.nodes[node].get('data')
        if rescue:
            check(blob is not None, 'rescue must contain inline data')
        else:
            check(blob is None, 'production must use external data')
            size = fit.cells(node, 'data-size')[0]
            offset = (fit.cells(node, 'data-position')[0] if 'data-position' in fit.nodes[node]
                      else ((fit.size + 3) & ~3) + fit.cells(node, 'data-offset')[0])
            check(offset >= fit.size and offset + size <= len(data), 'FIT external data bounds')
            check(offset % 4096 == 0, 'FIT component alignment')
            extents.append({'component':key, 'offset':offset, 'size':size})
            blob = data[offset:offset+size]
        children = [p for p in fit.nodes if p.startswith(node + '/hash')]
        check(len(children) >= 2, key + ' hashes missing')
        for child in children:
            algo = fit.text(child, 'algo')
            digest = (struct.pack('>I', zlib.crc32(blob)) if algo == 'crc32' else hashlib.new(algo, blob).digest())
            check(digest == fit.nodes[child]['value'], key + ' hash mismatch')
            hashes.append({'component':key, 'algorithm':algo, 'digest':digest.hex()})
        blobs[key] = blob
    for left,right in zip(sorted(extents,key=lambda e:e['offset']), sorted(extents,key=lambda e:e['offset'])[1:]):
        check(left['offset']+left['size'] <= right['offset'], 'overlapping external data')
    overlay = FDT(blobs['overlay'])
    check(overlay.text('/fragment@0','target-path') == '/', 'overlay target')
    check(overlay.nodes['/fragment@0/__overlay__'] == {}, 'compat overlay must not change hardware')
    check(set(overlay.nodes) == {'/', '/fragment@0', '/fragment@0/__overlay__'}, 'unexpected overlay nodes')
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        (tmp/'base.dtb').write_bytes(blobs['fdt'])
        (tmp/'compat.dtbo').write_bytes(blobs['overlay'])
        subprocess.run(['fdtoverlay','-i',str(tmp/'base.dtb'),'-o',str(tmp/'applied.dtb'),str(tmp/'compat.dtbo')],check=True)
        check(FDT((tmp/'applied.dtb').read_bytes()).nodes == FDT(blobs['fdt']).nodes, 'overlay changed hardware DT')

    kernel_node = '/images/' + config['kernel'].rstrip(b'\0').decode()
    fdt_node = '/images/' + config['fdt'].rstrip(b'\0').decode()
    check(fit.text(kernel_node, 'compression') == ('lzma' if rescue else 'gzip'), 'kernel compression')
    check(fit.cells(kernel_node, 'load') == (0x44000000,), 'kernel load address')
    check(fit.cells(kernel_node, 'entry') == (0x44000000,), 'kernel entry address')
    check(fit.cells(fdt_node, 'load') == (0x43f00000,), 'DTB load address')
    kernel = lzma.decompress(blobs['kernel'], format=lzma.FORMAT_ALONE) if rescue else gzip.decompress(blobs['kernel'])
    check(kernel[56:60] == b'ARM\x64', 'ARM64 Linux Image header')
    kernel_size = struct.unpack_from('<Q', kernel, 16)[0] or len(kernel)
    check(0x44000000 + kernel_size <= 0x46000000, 'kernel overlaps the community U-Boot FIT upload address')
    check(len(blobs['fdt']) < 0x100000, 'DTB overlaps kernel load region')
    check(len(data) < 64 * 1024**2, 'FIT exceeds conservative RAM upload size')

    dt = FDT(blobs['fdt'])
    check(dt.text('/', 'compatible').split('\0')[0] == 'cmcc,xr30-emmc', 'board identity')
    check(dt.cells('/memory@40000000', 'reg') == (0, 0x40000000, 0, 0x20000000), '512 MiB RAM')
    if rescue:
        check(dt.text('/chosen','bootargs-override') == 'console=ttyS0,115200n8 rdinit=/init fstools_ignore_partname=1 xr30_rescue=1', 'rescue bootargs')
        check('rootdisk' not in dt.nodes['/chosen'], 'rescue rootdisk forbidden')
        check(all('production' not in p for p in dt.nodes), 'rescue production binding forbidden')
    else:
        check(dt.text('/chosen','bootargs-override') == 'console=ttyS0,115200n8 root=/dev/fit0 rootwait fstools_overlay_fstype=f2fs', 'production bootargs')
        prod = next(p for p,v in dt.nodes.items() if v.get('partname') == b'production\0')
        check(dt.cells('/chosen','rootdisk') == dt.cells(prod,'phandle'), 'production rootdisk binding')
    mmc = next(p for p, v in dt.nodes.items() if v.get('bus-width') == struct.pack('>I', 8))
    check(dt.cells(mmc, 'max-frequency') == (52000000,), 'eMMC 52 MHz')
    check('cap-mmc-highspeed' in dt.nodes[mmc], 'eMMC highspeed')
    check(dt.text(mmc, 'status') == 'okay', 'eMMC enabled')
    factory = next(p for p in dt.nodes if p.endswith('/block-partition-factory'))
    check(dt.text(factory, 'partname') == 'factory', 'factory GPT label')
    cells = {}
    for name, reg in [('eeprom@0', (0, 0x1000)), ('macaddr@24', (0x24, 6)), ('macaddr@2a', (0x2a, 6))]:
        p = factory + '/nvmem-layout/' + name
        check(dt.cells(p, 'reg') == reg, name + ' offset/length')
        cells[name] = dt.cells(p, 'phandle')[0]
    for suffix, cell in [('/mac@0', 'macaddr@2a'), ('/mac@1', 'macaddr@24')]:
        p = next(p for p in dt.nodes if p.endswith(suffix))
        check(dt.cells(p, 'nvmem-cells') == (cells[cell], 0), suffix + ' MAC source')
    wifi = next(p for p, v in dt.nodes.items() if v.get('nvmem-cell-names') == b'eeprom\0')
    check(dt.cells(wifi, 'nvmem-cells') == (cells['eeprom@0'],), 'wireless EEPROM source')
    switch = next(p for p, v in dt.nodes.items() if v.get('compatible') == b'mediatek,mt7531\0')
    for port, label in [(0, 'lan3'), (1, 'lan2'), (2, 'lan1')]:
        check(dt.text(f'{switch}/ports/port@{port}', 'label') == label, 'LAN port map')
    for name, gpio in [('led-0', 34), ('led-2', 35)]:
        check(dt.cells('/gpio-leds/' + name, 'gpios')[1:] == (gpio, 1), 'XR30 LED pin')
    for name, gpio in [('button-reset', 1), ('button-mesh', 0)]:
        check(dt.cells('/gpio-keys/' + name, 'gpios')[1:] == (gpio, 1), 'button pin')

    archive = b''
    if rescue:
        archive = gzip.decompress(blobs['ramdisk'])
        check(len(archive) * 2 + kernel_size + 64 * 1024**2 < 512 * 1024**2, 'RAM budget')
        files = cpio_read(archive)
    else:
        check(blobs['rootfs'][:4] == b'hsqs', 'SquashFS magic')
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            sq = tmp/'root.squashfs'; sq.write_bytes(blobs['rootfs'])
            subprocess.run(['sudo','unsquashfs','-d',str(tmp/'root'),str(sq)],check=True,stdout=subprocess.DEVNULL)
            subprocess.run(['sudo','chown','-hR',f'{os.getuid()}:{os.getgid()}',str(tmp/'root')],check=True)
            files = {str(p.relative_to(tmp/'root')):{'data':p.read_bytes()} for p in (tmp/'root').rglob('*') if p.is_file() and not p.is_symlink()}
        fwtool = next(Path('openwrt/staging_dir/host/bin').glob('fwtool'))
        meta = report_dir/'production-metadata.json'
        subprocess.run([str(fwtool),'-i',str(meta),str(image)],check=True)
        metadata = json.loads(meta.read_text())
        check(metadata['supported_devices'] == ['cmcc,xr30-emmc'], 'strict sysupgrade board identity')
        root_extent = next(e for e in extents if e['component']=='rootfs')
        check(root_extent['size'] % 4096 == 0, 'FIT filesystem mapping page size')
        overlay_offset = root_extent['offset'] + root_extent['size']
        check(overlay_offset < 128*1024**2, 'unexpected firmware size')
        (report_dir/'fit-layout.json').write_text(json.dumps({'extents':extents,'overlay_offset':overlay_offset},indent=2)+'\n')
    read = lambda p: files[p]['data'].decode()
    if rescue:
        check('export INITRAMFS=1' in read('init') and 'switch_root' in read('init'), '/init RAM path')
        check('mount -t tmpfs tmpfs' in read('init'), 'RAM root storage')
    check('[ "$INITRAMFS" = "1" ] || boot_hook_add preinit_main do_mount_root' in read('lib/preinit/80_mount_root'), 'disk-overlay preinit guard')
    check('xr30_is_rescue || mount_root done' in read('etc/init.d/done'), 'conditional late overlay initialization')
    for guard in ['etc/init.d/fstab','etc/hotplug.d/block/10-mount']:
        check('xr30_is_rescue' in read(guard), 'missing rescue automount protection')
    check('XR30_DATA' in read('etc/config/fstab') and '/mnt/data' in read('etc/config/fstab'), 'data mount defaults')
    check(not any(word in read('etc/config/fstab') for word in ['mkfs','format']), 'data formatting forbidden')
    defaults = read('etc/board.d/99-xr30')
    check('192.168.3.1' in defaults and 'lan1 lan2 lan3' in defaults, 'board LAN defaults')
    for band in ('2g', '5g'):
        check(f'ucidef_set_wireless "{band}" "XR30" "none"' in defaults, band + ' defaults')
    check('ucidef_set_country "CN"' in defaults, 'CN defaults')
    packages = installed_packages(files['lib/apk/db/installed']['data'])
    for name in ['xr30-emmc-support', 'luci', 'luci-i18n-base-zh-cn', 'dropbear', 'wpad-basic-mbedtls', 'kmod-mt7915e', 'kmod-mt7981-firmware', 'kmod-usb3', 'kmod-usb-storage']:
        check(name in packages, 'missing package: ' + name)
    check(packages['xr30-emmc-support']['V'] == '2.0.0-r1', 'board support must include the network JSON normalization fix')
    for name in ['uboot-envtools', 'blockd']:
        check(name not in packages, 'unexpected disk/environment helper: ' + name)
    for name in ['block-mount','fitblk','sfdisk','partx-utils','blockdev','lsblk','e2fsprogs','mkf2fs','f2fsck','kmod-fs-ext4','kmod-fs-f2fs']:
        check(name in packages, 'missing storage/rescue tool: '+name)
    check('etc/fw_env.config' not in files, 'U-Boot environment config forbidden')
    check(not any(p.startswith(('etc/dropbear/dropbear_', 'root/.ssh/')) for p in files), 'private key/config in image')
    for p in ['etc/config/network', 'etc/config/wireless']:
        check(p not in files or not files[p]['data'], 'unexpected pre-existing configuration: ' + p)
    repos = []
    for p in files:
        if p.startswith('etc/apk/repositories.d/'):
            repos += [l.strip() for l in read(p).splitlines() if l.strip() and not l.startswith('#')]
    check(repos and all(u.startswith('https://mirrors.ustc.edu.cn/openwrt/releases/25.12.5/') for u in repos), 'USTC repository paths')
    compatibility = json.loads((report_dir / 'compatibility.json').read_text())
    check(compatibility['indexes_verified'], 'index signatures not verified')
    check(any('/kmods/' in u for u in repos) == compatibility['official_kmods_enabled'], 'kmod repository gating')
    expected_kernel = compatibility['built_kernel_package']
    check(packages['kernel']['V'] == expected_kernel, 'installed kernel package ABI')
    for name, info in packages.items():
        if name.startswith('kmod-'):
            check('kernel=' + expected_kernel in info.get('D', ''), name + ' kernel dependency')
    module_magics = sorted(set(re.findall(rb'vermagic=([^\0]+)', b'\0'.join(v['data'] for p, v in files.items() if p.endswith('.ko')))))
    check(module_magics, 'no module vermagic found')
    check(all(v.decode() == compatibility['built_module_vermagic'] for v in module_magics), 'installed module vermagic')
    (report_dir / (mode+'-packages.json')).write_text(json.dumps(packages, indent=2) + '\n')
    (report_dir / (mode+'-packages.manifest')).write_text(''.join(f'{k} - {v["V"]}\n' for k, v in sorted(packages.items())))
    (report_dir / (mode+'-xr30.dtb')).write_bytes(blobs['fdt'])
    if rescue:
        (report_dir / 'initrd.cpio.gz').write_bytes(blobs['ramdisk'])
    result = {'status': 'offline structure checks passed; hardware not tested',
              'image': image.name, 'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data),
              'kernel_uncompressed_bytes': len(kernel), 'initramfs_uncompressed_bytes': len(archive),
              'mode':mode, 'fit_default': 'config-1', 'uboot_selection':'config-1#'+alias, 'compatibility_overlay_unchanged':True, 'hashes': hashes, 'repositories': repos,
              'package_count': len(packages), 'kernel_package': expected_kernel,
              'module_vermagic': [v.decode() for v in module_magics],
              'runtime_frequency_and_hardware': 'not tested'}
    (report_dir / (mode+'-image-checks.json')).write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    verify(Path(sys.argv[1]), Path(sys.argv[2]))
