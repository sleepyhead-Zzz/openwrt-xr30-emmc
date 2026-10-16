# SPDX-License-Identifier: MIT
xr30_is_rescue() {
 [ "$(cat /tmp/sysinfo/board_name 2>/dev/null)" = "cmcc,xr30-emmc" ] || return 1
 grep -qw 'xr30_rescue=1' /proc/cmdline
}
