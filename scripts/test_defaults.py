#!/usr/bin/env python3
"""Run the image's real board/network/wireless generators in an ARM64 chroot.

Only radio enumeration and sysfs MACs are fixtures. This is not a hardware test.
No init system is started and no host /dev or /sys is mounted into the chroot.
"""
import json
import re
import shlex
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def main():
    root = Path(sys.argv[1]).resolve()
    reports = REPO / 'reports'
    def cmd(*args, input=None):
        result = subprocess.run(['sudo', 'chroot', str(root), *args], input=input,
                                text=True, capture_output=True)
        with (reports / 'defaults-test.log').open('a') as log:
            log.write('$ chroot ' + ' '.join(args) + '\n' + result.stdout + result.stderr + '\n')
        if result.returncode:
            raise RuntimeError(f'chroot command failed ({result.returncode}): {args}')
        return result.stdout.strip()
    def get(key):
        return cmd('/sbin/uci', '-q', 'get', key)
    (root / 'tmp/sysinfo').mkdir(parents=True, exist_ok=True)
    (root / 'tmp/sysinfo/board_name').write_text('cmcc,xr30-emmc\n')
    (root / 'tmp/sysinfo/model').write_text('CMCC XR30 (eMMC version)\n')
    for p in ['etc/board.json', 'etc/config/network', 'etc/config/system', 'etc/config/wireless']:
        (root / p).unlink(missing_ok=True)
    cmd('/bin/board_detect')
    cmd('/bin/config_generate')
    assert get('network.lan.ipaddr') == '192.168.3.1/24'
    assert get('network.lan.proto') == 'static'
    assert get('network.lan.device') == 'br-lan'
    assert get('network.@device[0].ports') == 'lan1 lan2 lan3'
    assert get('network.wan.device') == 'eth1'
    assert get('network.wan.proto') == 'dhcp'
    assert get('dhcp.lan.interface') == 'lan'
    assert int(get('dhcp.lan.limit')) > 0
    ignore = subprocess.run(['sudo', 'chroot', str(root), '/sbin/uci', '-q', 'get', 'dhcp.lan.ignore'], capture_output=True, text=True)
    assert ignore.stdout.strip() in ('', '0')
    assert (root / 'etc/init.d/dnsmasq').exists()
    (reports / 'generated-network.uci').write_text(cmd('/sbin/uci', 'export', 'network') + '\n')
    (reports / 'generated-dhcp.uci').write_text(cmd('/sbin/uci', 'export', 'dhcp') + '\n')
    board = json.loads((root / 'etc/board.json').read_text())
    (reports / 'generated-board.json').write_text(json.dumps(board, indent=2) + '\n')
    results = []
    for order in [('2G', '5G'), ('5G', '2G')]:
        fixture = json.loads(json.dumps(board))
        for index, band in enumerate(order):
            phy = f'phy{index}'
            fixture['wlan'][phy] = {'path': f'platform/18000000.wifi+{index}',
                'info': {'bands': {band: {'max_width': 40 if band == '2G' else 160,
                                        'he': True, 'ht': True}}, 'radios': []}}
            path = root / f'sys/class/ieee80211/{phy}'
            path.mkdir(parents=True, exist_ok=True)
            (path / 'macaddress').write_text(f'02:00:00:00:00:0{index}\n')
        (root / 'etc/board.json').write_text(json.dumps(fixture))
        (root / 'etc/config/wireless').write_text('')
        generated = cmd('/usr/bin/ucode', '/lib/wifi/mac80211.uc')
        cmd('/sbin/uci', '-q', 'batch', input=generated + '\n')
        settings = cmd('/sbin/uci', '-q', 'show', 'wireless')
        devices = re.findall(r'^wireless\.(\w+)=wifi-device$', settings, re.M)
        interfaces = re.findall(r'^wireless\.(\w+)=wifi-iface$', settings, re.M)
        assert len(devices) == 2 and len(interfaces) == 2
        assert {get(f'wireless.{name}.band') for name in devices} == {'2g', '5g'}
        for name in devices:
            assert get(f'wireless.{name}.country') == 'CN'
        for name in interfaces:
            for key, value in {'ssid': 'XR30', 'encryption': 'none', 'network': 'lan', 'mode': 'ap', 'disabled': '0'}.items():
                assert get(f'wireless.{name}.{key}') == value
            assert get(f'wireless.{name}.device') in devices
        label = '-'.join(order)
        (reports / f'generated-wireless-{label}.uci').write_text(cmd('/sbin/uci', 'export', 'wireless') + '\n')
        results.append({'radio_enumeration_order': order, 'enabled_APs': 2, 'SSIDs': ['XR30', 'XR30'], 'country': 'CN', 'encryption': 'none'})
    (reports / 'defaults-checks.json').write_text(json.dumps({
        'status': 'passed', 'method': 'real image executables under qemu-user, mocked radio enumeration',
        'lan': '192.168.3.1/24', 'ports': ['lan1', 'lan2', 'lan3'], 'wan': 'eth1 DHCP',
        'dhcp_enabled': True, 'wireless_cases': results, 'hardware_tested': False}, indent=2) + '\n')
    print('Network, DHCP, and both wireless enumeration orders passed')


if __name__ == '__main__':
    main()
