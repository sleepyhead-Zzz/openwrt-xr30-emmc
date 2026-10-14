
# XR30 eMMC: RAM boot only. No persistent image or bootloader artifacts.
define Device/cmcc_xr30-emmc
  DEVICE_VENDOR := CMCC
  DEVICE_MODEL := XR30
  DEVICE_VARIANT := eMMC RAM boot
  DEVICE_DTS := mt7981b-cmcc-xr30-emmc
  DEVICE_DTS_DIR := ../dts
  DEVICE_DTC_FLAGS := --pad 4096
  DEVICE_DTS_LOADADDR := 0x43f00000
  DEVICE_DTS_CONFIG := config-1
  KERNEL_LOADADDR := 0x44000000
  KERNEL := kernel-bin | lzma
  KERNEL_INITRAMFS := kernel-bin | lzma | \
	fit lzma $$(KDIR)/image-$$(firstword $$(DEVICE_DTS)).dtb with-initrd | pad-to 64k
  KERNEL_INITRAMFS_SUFFIX := -recovery.itb
  DEVICE_PACKAGES := xr30-emmc-support kmod-mt7915e kmod-mt7981-firmware \
	mt7981-wo-firmware kmod-usb3 kmod-usb-storage -uboot-envtools -fitblk
  SUPPORTED_DEVICES := cmcc,xr30-emmc
  FILESYSTEMS :=
  IMAGES :=
  ARTIFACTS :=
endef
TARGET_DEVICES += cmcc_xr30-emmc
