# XR30 eMMC：12 GiB 系统与 ext4 数据分区安装说明

本轮只构建、离线验证和交付。以下为未来获准安装时的人工步骤，不是已执行记录。仅当候选包 STATUS.txt 明确写明“正式安装版构建及离线检查通过，磁盘启动与持久化尚未实机验证”，且本地 SHA256SUMS 全部通过后使用。失败的 diagnostics 不能安装。

## 布局与边界

512 字节逻辑扇区，120,832,000 扇区（61,865,984,000 字节）。最后可用 LBA 为 120831966，末尾保留标准 GPT 备份。若容量、扇区尺寸、前三分区的名称/边界或 GPT 结构不同，停止并重新规划，不能套用下列固定值。

| 分区 | 名称 | 起始 LBA | 结束 LBA | 扇区数 |
|---|---|---:|---:|---:|
| p1 | u-boot-env | 8192 | 9215 | 1024 |
| p2 | factory | 9216 | 13311 | 4096 |
| p3 | fip | 13312 | 17407 | 4096 |
| p4 | production | 18432 | 25184255 | 25165824 |
| p5 | data | 25184256 | 120831966 | 95647711 |

p4 恰为 12 GiB，包括 FIT 固件、SquashFS 和 F2FS overlay；可用量略少。p5 约 45.61 GiB，ext4 标签 XR30_DATA，挂载 /mnt/data。BL2 位于独立 eMMC 硬件启动区域，不能写入或重新配置。p1–p3 的内容、GUID、类型和边界均保持。

旧 kernel/rootfs/production/data 都会丢失，不迁移。旧 Kwrt 不再是可回退槽；恢复依靠保存的启动器、备份和 RAM 救援。CPU 缓存和 USB 供电设备树警告保留。

## 1. 准备和 RAM 救援启动

1. 在电脑验证候选包内 SHA256SUMS（Linux `sha256sum -c SHA256SUMS`；macOS `shasum -a 256 -c SHA256SUMS`），保留候选包、同次模块、已验证旧 RAM 镜像和旧验收记录。
2. 通过现有 U-Boot 的内存启动入口加载本次 `initramfs-recovery.itb`，不能把它当正式固件写入。无需更换 U-Boot。选择链为 `config-1#mt7981b-cmcc-rax3000m-emmc`，第二项为空兼容 overlay，实际硬件仍是 XR30。
3. 进入救援后确认 `ubus call system board` 显示 `cmcc,xr30-emmc`、`initramfs`；`cat /proc/cmdline` 含 `xr30_rescue=1`；`mount` 显示 `/` 为 tmpfs，且无 eMMC/FIT/overlay 挂载，`cat /proc/swaps` 无设备。任一不符停止。
4. 确认 `sfdisk`、`partx`、`blockdev`、`mkfs.ext4` 可执行。救援镜像自带原生工具，无需临时下载包。

## 2. 只读容量、分区和备份核验

确认目标确实为内置 eMMC 后，下面示例才使用 `/dev/mmcblk0`。不要自动选取“第一块磁盘”。

```sh
D=/dev/mmcblk0
blockdev --getss "$D"      # 必须 512
blockdev --getsz "$D"      # 必须 120832000
sfdisk --verify "$D"
sfdisk --dump "$D"
sfdisk --json "$D"
for n in 1 2 3; do
 cat /sys/class/block/mmcblk0p$n/start
 cat /sys/class/block/mmcblk0p$n/size
done
```

前三分区 start/size 必须为 `8192/1024`、`9216/4096`、`13312/4096`，名称依次 u-boot-env/factory/fip。记录 GUID、类型、属性；验证 GPT 校验通过和末尾可用扇区。旧 p4–p7 必须确认是 kernel/rootfs/production/data，没有需要保留的额外分区。

备份到救援 RAM，随后立即复制到电脑，禁止只把备份放在即将删除的数据区。以下只读取磁盘：

```sh
mkdir -p /tmp/xr30-backup
cd /tmp/xr30-backup
sfdisk --dump "$D" > original.sfdisk
sfdisk --json "$D" > original.json
dd if="$D" of=userarea-prefix.bin bs=512 count=8192
dd if="$D" of=gpt-primary.bin bs=512 count=34
dd if="$D" of=gpt-backup.bin bs=512 skip=120831967 count=33
dd if=/dev/mmcblk0boot0 of=boot0.bin bs=1M
dd if=/dev/mmcblk0boot1 of=boot1.bin bs=1M
dd if=/dev/mmcblk0p1 of=u-boot-env.bin bs=512
dd if=/dev/mmcblk0p2 of=factory.bin bs=512
dd if=/dev/mmcblk0p3 of=fip.bin bs=512
sha256sum *.bin original.sfdisk original.json > SHA256SUMS
sha256sum -c SHA256SUMS
```

从电脑下载整个目录，并在电脑再次校验 SHA-256。对原盘重复读取哈希，与备份逐项比较（例如 `sha256sum /dev/mmcblk0boot0 /dev/mmcblk0boot1 /dev/mmcblk0p1 /dev/mmcblk0p2 /dev/mmcblk0p3`）；GPT 两份备份还需检查签名、头和分区表 CRC。若备份不完整、两次读取不一致或无法确认 GPT 有效，停止。硬件启动区只备份，不解除只读保护，不访问 RPMB，不改 eMMC boot 配置。

## 3. 修改 GPT（破坏旧系统的明确步骤）

只有前两节全部确认并已保存电脑端备份后继续。以下使用原生 sfdisk 删除四个旧系统/数据分区，保留 p1–p3 的分区记录。不得使用整盘 wipefs、mklabel 或全新磁盘标签覆盖命令。

```sh
sfdisk --delete "$D" 4 5 6 7
sfdisk --append "$D" <<'PARTITIONS'
start=18432,size=25165824,name="production"
start=25184256,size=95647711,name="data"
PARTITIONS
blockdev --rereadpt "$D"
partx --update "$D"
sfdisk --verify "$D"
sfdisk --dump "$D"
```

任何命令失败立即停止，不接着格式化。比较备份：p1–p3 的 GUID、类型、属性和边界全部不变；再比对内容 SHA-256。检查 `/sys/class/block/mmcblk0p4/{start,size}` 为 18432/25165824、p5 为 25184256/95647711，且内核不再列出旧 p6/p7。仅用户空间 GPT 输出正确还不够；内核未识别新布局时不能格式化。

## 4. 明确格式化数据区

再确认 p5 是新建的 data，且没有挂载或 swap 使用。只对数据区执行一次：

```sh
mkfs.ext4 -L XR30_DATA /dev/mmcblk0p5
block info /dev/mmcblk0p5
```

应显示 TYPE=ext4、LABEL=XR30_DATA。不要格式化 p4 为 ext4/F2FS；正式 FIT 将写入 p4，官方首次启动流程会初始化其内部 F2FS 可写区。系统启动、后续升级和恢复默认设置都不负责格式化 p5。

## 5. 经现有 U-Boot 写入正式 FIT

1. 从救援退出并进入已存在的 U-Boot 恢复/固件上传入口，确认是正式固件写入入口，而非 BL2、FIP、GPT、环境或 RAM 启动入口。
2. 上传并写入本次 `squashfs-sysupgrade.itb`。不要使用当前旧 Kwrt 的 LuCI 或 sysupgrade 脚本。
3. 已核对的启动器实现按 GPT 名称 production 定位目标，并由固件入口选择系统槽 1。不要自行运行 fw_setenv：旧环境布局不匹配官方 RAX3000M 环境工具配置，本镜像不含该工具。
4. 若实际页面/串口流程与该入口不符，或提示其他写入目标，停止；不能把未知入口当成同一个入口。
5. 等待写入校验完成，再按该入口正常启动正式系统。没有备份且刷写中断时不可反复试写 bootloader。

启动器来源固定到 https://github.com/lgs2007m/bl-mt798x/blob/7c65f3ca969265421443fff033356a5218912d4d/uboot-mtk-20220606/board/mediatek/mt7981/bootmenu_emmc.c 。源码审查不替代对实机现有 U-Boot 版本和入口的确认。

## 6. 首次磁盘启动与重启验收

- 访问 192.168.3.1，检查型号 XR30、LAN 三口和 WAN、DHCP、两频 XR30/CN、中文 LuCI。
- `/proc/cmdline` 应含 `root=/dev/fit0`，没有 `xr30_rescue=1` 或 `rdinit=/init`。`mount` 应显示 `/rom` SquashFS、`/overlay` F2FS、`/` overlayfs；`df -h /overlay /mnt/data` 应为约 12 GiB 系统区扣除开销、约 45.6 GiB 数据区扣除开销。
- `block info` 应确认 XR30_DATA 对应 p5，并挂载到 /mnt/data。若缺失，查标签、fstab 和日志，不能“修复”为自动格式化。
- 创建两份内容明确的测试文件，如 `/etc/xr30-persistence-test` 与 `/mnt/data/xr30-data-test`，记录 SHA-256，`sync`，在下一次获准重启后核对文件、哈希、文件系统类型、容量和挂载点。
- 核对 eMMC 请求上限 52 MHz；历史驱动实际报告为 50 MHz，不能把配置上限说成精确实测时钟。

后续仅在此正式系统使用官方 LuCI/sysupgrade 升级入口；元数据严格仅包含 `cmcc,xr30-emmc`。先用 `sysupgrade -T <正式FIT>` 检查，不使用强制型号跳过选项。保留配置与不保留配置两条 eMMC 写入路径都只作用于 production。恢复出厂设置会清理系统 overlay，不应影响 XR30_DATA；该行为仍需后续实机验收，不能把 CI 虚拟盘测试当作已完成实测。
