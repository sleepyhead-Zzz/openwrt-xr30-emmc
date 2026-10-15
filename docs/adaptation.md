# XR30 eMMC adaptation comparison

This table documents source-level choices. Physical hardware facts were previously observed in a separate read-only inspection; raw dumps and private identifiers are deliberately absent from this public repository. That inspection is not a boot test of this image.

| Area | Community/reference implementation | This build |
|---|---|---|
| Base SoC | Kwrt's historical XR30 DTSI includes an older `mt7981.dtsi` | Use official 25.12.5 `mt7981b.dtsi`; no old SoC, kernel, mt76, regdb or vendor patches |
| Identity/RAM | `cmcc,xr30-emmc`, 512 MiB starting at `0x40000000` | Same identity and RAM, explicit memory device type |
| Switch | MT7531 at MDIO `0x1f`; reset GPIO39, IRQ GPIO38; 2.5G CPU link | Same mapping; unrelated RAX3000M AN8855 variant omitted |
| LAN/WAN | LAN ports 0/1/2 labeled lan3/lan2/lan1, CPU port 6 → GMAC0; GMAC1 internal PHY | Same DTS mapping; independent support package selects lan1/lan2/lan3 and eth1 |
| MAC | factory offsets `0x2a` for GMAC0 and `0x24` for GMAC1 | Same offsets, six bytes each; use current official `mac-base` phandle argument `0` |
| Wireless calibration | factory offset `0`, length `0x1000`; nvmem eeprom | Same label/offset; official mt7915e/mt7981 firmware and mt76 |
| eMMC | XR30 8-bit, `cap-mmc-highspeed`, 52 MHz; RAX3000M official overlay uses 26 MHz | XR30 values, current official MMC binding and pinctrl; no SD/SDIO |
| LEDs | Red active-low GPIO35, white active-low GPIO34 | Modern function/color bindings; red boot/failsafe/upgrade, white running |
| Buttons | Reset active-low GPIO1; mesh active-low GPIO0 / BTN_9 / EV_SW | Same |
| USB/watchdog/UART | SoC nodes enabled | Same official node implementation |
| Disk layout | Kwrt uses kernel/rootfs; official RAX3000M uses production/FIT | No persistent root selector, no chosen/rootdisk and no production binding; factory nvmem only |
| Boot arguments | Kwrt `root=PARTLABEL=rootfs rootwait`; official RAX `root=/dev/fit0 rootwait` | Override with `console=ttyS0,115200n8 rdinit=/init fstools_ignore_partname=1` |
| Late startup | Official done service calls `mount_root done`; fstools can discover existing GPT/FIT volumes | One base-files hunk skips that call for the RAM-only XR30 target; no kernel/fstools patch |
| Image | Community sysupgrade-tar; official recovery FIT can contain separate initrd | Recovery FIT only, no disk images or bootloader artifacts; default config-1 directly references full XR30 DTB |
| Addresses | Official RAX recovery kernel `0x44000000`, DTB `0x43f00000`; community U-Boot upload `0x46000000` | Same kernel/DTB addresses; offline gate ensures uncompressed kernel ends before upload address |
| U-Boot selection | `boot_from_mem()` uses an existing bootconf, otherwise FIT default; memory-upload handler skips `write_firmware_failsafe()` | No U-Boot build/config/environment change. Default config-1 is complete. Actual entry and current environment remain future-test prerequisites |
| U-Boot environment | Inspected legacy environment is one 512 KiB region named u-boot-env; official RAX tools assume different naming/redundancy | Exclude uboot-envtools and fw_env.config; no attempt to reuse mismatched environment configuration |
| Defaults | Official unknown-board fallback includes lan4; wireless uses board JSON defaults | `xr30-emmc-support` replaces and normalizes the empty network object before calling official ucidef functions, avoiding duplicate JSON keys; no radio0 band assumption |
| Software repos | Kwrt has custom repos and modified compatibility controls | Official packages via USTC, normal signature/dependency checks; unmodified ABI calculation |

## Pinned primary references

- [Official RAX3000M DTS](https://github.com/openwrt/openwrt/blob/f0a60eee2fe051741c643ea6118718aae1ef17fb/target/linux/mediatek/dts/mt7981b-cmcc-rax3000m.dts)
- [Official eMMC overlay](https://github.com/openwrt/openwrt/blob/f0a60eee2fe051741c643ea6118718aae1ef17fb/target/linux/mediatek/dts/mt7981b-cmcc-rax3000m-emmc.dtso)
- [Official image recipe](https://github.com/openwrt/openwrt/blob/f0a60eee2fe051741c643ea6118718aae1ef17fb/target/linux/mediatek/image/filogic.mk)
- [Kwrt XR30 eMMC DTS](https://github.com/kiddin9/Kwrt/blob/4ab643693238cf72a360720081b224cbb442b1c1/devices/mediatek_filogic/diy/target/linux/mediatek/dts/mt7981b-cmcc-xr30-emmc.dts)
- [Kwrt XR30 common DTSI](https://github.com/kiddin9/Kwrt/blob/4ab643693238cf72a360720081b224cbb442b1c1/devices/mediatek_filogic/diy/target/linux/mediatek/dts/mt7981b-cmcc-xr30.dtsi)
- [Community image/target patch](https://github.com/kiddin9/Kwrt/blob/4ab643693238cf72a360720081b224cbb442b1c1/devices/mediatek_filogic/patches/08-cmcc_rax3000m.patch)
- [Community eMMC notes](https://github.com/lgs2007m/Actions-OpenWrt/blob/d214de7d367665a8bc3b9d314e12de44df33b2af/Tutorial/RAX3000M-eMMC_XR30-eMMC.md)
- [U-Boot memory upload](https://github.com/lgs2007m/bl-mt798x/blob/7c65f3ca969265421443fff033356a5218912d4d/uboot-mtk-20220606/failsafe/failsafe.c)
- [U-Boot memory boot helper](https://github.com/lgs2007m/bl-mt798x/blob/7c65f3ca969265421443fff033356a5218912d4d/uboot-mtk-20220606/board/mediatek/common/boot_helper.c)
- [U-Boot XR30 eMMC config](https://github.com/lgs2007m/bl-mt798x/blob/7c65f3ca969265421443fff033356a5218912d4d/uboot-mtk-20220606/configs/mt7981_cmcc_xr30-emmc_defconfig)
- [USTC mirror instructions](https://mirrors.ustc.edu.cn/help/openwrt.html)
