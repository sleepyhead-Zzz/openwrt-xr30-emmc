# SPDX-License-Identifier: MIT
include $(TOPDIR)/rules.mk

PKG_NAME:=xr30-emmc-support
PKG_VERSION:=2.0.0
PKG_RELEASE:=1
PKG_LICENSE:=MIT

include $(INCLUDE_DIR)/package.mk

define Package/xr30-emmc-support
  SECTION:=base
  CATEGORY:=Base system
  TITLE:=CMCC XR30 eMMC production and rescue defaults
  DEPENDS:=@TARGET_mediatek_filogic +base-files +wifi-scripts
endef

define Build/Compile
endef

define Package/xr30-emmc-support/install
	$(INSTALL_DIR) $(1)/lib/functions $(1)/etc/config $(1)/mnt/data
	$(INSTALL_DATA) ./files/xr30.sh $(1)/lib/functions/xr30.sh
	$(INSTALL_CONF) ./files/fstab $(1)/etc/config/fstab
	$(INSTALL_DIR) $(1)/etc/board.d
	$(INSTALL_BIN) ./files/99-xr30 $(1)/etc/board.d/99-xr30
endef

$(eval $(call BuildPackage,xr30-emmc-support))
