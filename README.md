# CMCC XR30 eMMC — OpenWrt 25.12.5 RAM image

Build an **initramfs recovery FIT only** from official OpenWrt with a small XR30 board adaptation. This is a public fork of [P3TERX/Actions-OpenWrt](https://github.com/P3TERX/Actions-OpenWrt), pinned at `decaa5c260535c302a0d59d53b598bb409fd54dd`; its environment, download, configuration, compilation and artifact workflow has been adapted for the official 25.12.5 source.

**Hardware testing is pending.** A green workflow means compilation and the documented offline checks passed. It does not prove bootability, measured eMMC frequency, Wi-Fi behavior, port mapping on physical hardware, or a working recovery route.

| Setting | Value |
|---|---|
| Source | Official `openwrt/openwrt`, `f0a60eee2fe051741c643ea6118718aae1ef17fb` |
| Board | `cmcc,xr30-emmc`, MT7981B, 512 MiB, MT7531 |
| eMMC | 8-bit, highspeed capability, maximum 52 MHz |
| LAN | `lan1 lan2 lan3`, `192.168.3.1/24`, DHCP server |
| WAN | `eth1`, DHCP client |
| Wi-Fi | Official mt76, 2.4/5 GHz enabled, both SSIDs `XR30`, open authentication, country `CN` |
| Packages | Chinese LuCI with HTTPS, Dropbear, wireless and USB components |
| Repositories | USTC official OpenWrt 25.12.5 paths, signature verification retained |
| Boot | Default FIT `config-1`, complete XR30 DTB, separate gzip initramfs, LZMA kernel |
| Output | `openwrt-25.12.5-mediatek-filogic-cmcc_xr30-emmc-initramfs-recovery.itb` |

The open wireless networks and default OpenWrt account state are intentional for this test image. No device backup, private key, real MAC address, account, or existing Kwrt configuration is included.

## Build and artifacts

Use **Actions → XR30 eMMC RAM image → Run workflow → main**. Only manual dispatch is enabled. There are no scheduled builds, automatic Releases, or history-cleanup actions. The standard `ubuntu-24.04` x64 runner uses at most four make workers, a 330-minute job timeout, a 40 GiB preflight, and download/compiler caches. All Actions are pinned by commit. No router connection exists in the workflow.

Successful runs retain these artifacts for 30 days:

- `xr30-emmc-25.12.5-candidate-*`: RAM image, SHA-256, package manifest, full build/kernel configs, source and feed commits, public signing keys, adaptation comparison, and offline reports.
- `xr30-emmc-same-build-packages-*`: signed target package index and packages from the same build, including kernel modules.
- `xr30-emmc-diagnostics-*`: logs and intermediate reports, also saved on failure. A diagnostic artifact is not a validated boot candidate.

Diagnostics may include an unvalidated intermediate RAM image and an allowlisted public build-state snapshot to diagnose validation failures without losing the compiled evidence. These files carry `NOT-A-CANDIDATE.txt`; they are not a successful delivery. Signing private keys are excluded.

The image contains no sysupgrade payload, GPT, BL2 or FIP installation artifact. Do not submit it to the current Kwrt LuCI firmware-upgrade form. Physical memory-boot testing and any persistent migration are separate work.

## Package compatibility

The official `config.buildinfo` and exact feed commits are committed under `locks/`. Kernel options and `CONFIG_ALL_KMODS=y` are preserved; kernel compatibility identifiers are never forged. The workflow downloads every USTC index with GET, verifies it with the image's trusted keys and official apk tool, compares the real kernel config ABI and an official module's ELF vermagic, and simulates dependency resolution against the image's installed package database.

The official kmods path is enabled only if the comparisons pass. Otherwise it is omitted and the same-build modules are supplied. Ordinary repositories continue to use USTC. There is no automatic mirror fallback or disabled signature check. Repository availability and signed index checks must pass before a candidate is uploaded.

Ordinary package installation still depends on normal ABI/dependency rules. `apk upgrade` is not a board-aware whole-firmware upgrade. This image's configuration is temporary because the root filesystem runs in RAM.

See [adaptation comparison](docs/adaptation.md) and [offline validation scope](docs/validation.md).

## Licensing

The original Actions template and new build/check scripts use the [MIT license](LICENSE). The new DTS retains its upstream `GPL-2.0-or-later OR MIT` SPDX identifier and attribution. OpenWrt, Linux, mt76 and all included packages retain their own upstream licenses. Source and patch provenance are recorded in `locks/sources.json`.
