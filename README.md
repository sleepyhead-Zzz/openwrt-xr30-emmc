# XR30 eMMC OpenWrt 25.12.5

Builds a production SquashFS FIT and an independent initramfs rescue FIT for CMCC XR30 eMMC. The intended layout has a 12 GiB `production` partition and an ext4 `XR30_DATA` partition mounted at `/mnt/data`. Installation removes old Kwrt kernel/rootfs; BL2, FIP, factory and environment contents remain unchanged.

The locked official OpenWrt commit is `f0a60eee2fe051741c643ea6118718aae1ef17fb`; feeds, official build configuration and source metadata are in `locks/`. Official mt76, 52 MHz eMMC configuration, 192.168.3.1/24 LAN, DHCP, two open XR30 APs in CN, Chinese LuCI and signed USTC APK repositories are retained. CPU cache and USB supply DT warnings are unchanged.

Both FITs support `config-1#mt7981b-cmcc-rax3000m-emmc` through an empty compatibility overlay on the full XR30 DT. Production binds rootdisk to the GPT name `production`, uses normal FIT/eMMC sysupgrade and initializes persistent F2FS overlay. Rescue has a separate DT and cmdline, no production binding, and guards late overlay initialization and block automount. It includes native sfdisk, partx, blockdev, e2fsprogs and F2FS tools, without automatic partitioning or formatting.

The manual GitHub Actions workflow uses Ubuntu 24.04, at most four build workers, a 330-minute timeout, a 40 GiB free-space preflight and 30-day artifact retention. No router access occurs in CI. All required checks must pass before publishing a candidate: both FITs, DT/overlay identity, load addresses, external data/hash/metadata checks, ARM64 defaults and boot gates, signed indexes and dependency/module ABI verification, sparse virtual GPT and filesystem tests, and official upgrade write-range isolation.

Success means **正式安装版构建及离线检查通过，磁盘启动与持久化尚未实机验证**. See [installation instructions](docs/installation.md) and [validation scope](docs/validation.md). Diagnostics are never installation candidates. The old validated RAM image and its hardware baseline remain historical evidence, not proof of physical boot for these new images.
