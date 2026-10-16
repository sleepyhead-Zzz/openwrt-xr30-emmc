# XR30: full hardware DT, production FIT and independent RAM rescue FIT.
define Device/cmcc_xr30-emmc
  DEVICE_VENDOR := CMCC
  DEVICE_MODEL := XR30
  DEVICE_VARIANT := eMMC
  DEVICE_DTS := mt7981b-cmcc-xr30-emmc mt7981b-cmcc-xr30-emmc-rescue
  DEVICE_DTS_OVERLAY := mt7981b-cmcc-xr30-uboot-compat
  DEVICE_DTS_DIR := ../dts
  DEVICE_DTC_FLAGS := --pad 4096
  DEVICE_DTS_LOADADDR := 0x43f00000
  DEVICE_DTS_CONFIG := config-1
  KERNEL_LOADADDR := 0x44000000
  KERNEL := kernel-bin | gzip
  KERNEL_INITRAMFS := kernel-bin | lzma | \
	fit lzma $$(KDIR)/image-mt7981b-cmcc-xr30-emmc-rescue.dtb with-initrd | pad-to 64k
  KERNEL_INITRAMFS_SUFFIX := -recovery.itb
  DEVICE_PACKAGES := xr30-emmc-support kmod-mt7915e kmod-mt7981-firmware \
	mt7981-wo-firmware kmod-usb3 kmod-usb-storage -uboot-envtools \
	fitblk block-mount e2fsprogs f2fsck mkf2fs kmod-fs-ext4 kmod-fs-f2fs \
	sfdisk partx-utils blockdev lsblk
  SUPPORTED_DEVICES := cmcc,xr30-emmc
  FILESYSTEMS := squashfs
  IMAGES := sysupgrade.itb
  IMAGE/sysupgrade.itb := append-kernel | \
	fit gzip $$(KDIR)/image-mt7981b-cmcc-xr30-emmc.dtb external-static-with-rootfs | \
	pad-rootfs | append-metadata
  ARTIFACTS :=
endef
TARGET_DEVICES += cmcc_xr30-emmc
