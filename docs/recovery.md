# RIO System Monitor recovery

## Current desktop recovery baseline

**rc0.1.27 is the sole current Windows desktop rollback baseline.** Earlier
desktop releases remain available for historical reference; they are not
current rollback targets.

Exit RIO and replace the executable with `RIO-System-Monitor.exe` from the
[v0.1.27 GitHub release](https://github.com/Kinkairy/rio-system-monitor/releases/tag/v0.1.27).
Verify that it is 81,975,241 bytes and has SHA-256
`93e6ca3aa5e5a9ad91afbdcdb0020def3e9280f03e259aec7d96faafaaf38b43`.
Start RIO again and keep `%LOCALAPPDATA%/RIO-Monitor` to retain settings and
local data. This desktop rollback does not change Android or screen firmware.

The main program checks [Gitee](https://gitee.com/kinkairy/rio-system-monitor-updates)
for in-app updates; use the exact GitHub release link above for this rollback.
Extension modules use GitHub.

The host negotiates the display protocol when a compatible USB screen connects. The program detects a supported factory eM133-V3 and prompts for the physical actions required to enter its upgrade mode. The released updater verifies the device and package, backs up and checks the 588 KiB protected area, verifies the animation data by readback, and activates the player. Updating the desktop program on a working screen requires no device write.

Device backups and original artwork are held separately. Earlier desktop and screen recovery instructions remain available in the corresponding revision of this document.
