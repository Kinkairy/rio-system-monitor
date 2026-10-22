# RIO System Monitor

An experimental Windows desktop monitor for a compatible USB round display.
Qt Quick settings and tray UI; a Pillow-rendered 480 x 480 dashboard with
CPU/RAM readings, optional NVIDIA GPU readings, animated weather and clock.

## Status

Development preview, not a hardware-certified release. Windows CPU temperature
collection is not implemented; unavailable values are shown as missing.
USB output needs compatible hardware and an existing WinUSB interface. Startup
checks for a single compatible interface; hot-plug reconnect is not implemented.
No drivers or firmware are installed or changed. Close other screen software
before use. USB hardware output has not yet been validated by the maintainer.

## Build and test

This public repository contains source code and documentation only. Images,
animation atlases, animation registration data, fonts and icons are kept in the
private `Kinkairy/usb-round-screen` repository under `monitor-assets/`.
Those materials are not licensed or distributed by this public repository.

For an authorized local build, clone the private repository separately and run:

```text
python tools/import_private_assets.py --source <absolute-path-to-private-monitor-assets>
```

The importer verifies the private manifest before copying material into the
ignored local `assets/` directory. Qt Quick `.qml` files remain public source.
Use Python 3.12 on Windows, then run `Build-Windows.cmd` to create a local EXE.
Missing private material produces a clear build error. Dependencies come from PyPI.

Tests: set `PYTHONPATH=src`, then `python -m unittest discover -s tests -v`.
Without private material, tests requiring art/fonts are explicitly skipped;
after import, run the same command for the complete suite.
Entry point: launch.py -> rio_monitor.qt_app. Older Tk modules are legacy only.
Public CI checks the source boundary and source tests. It does not fetch private
material or upload executable files, screenshots, previews or other build artifacts.
Do not attach builds containing private assets to public releases or CI artifacts.

The maintainer-approved material migration rewrote the original three-commit
public history. The original history is preserved only on the private repository's
`archive/rio-system-monitor-assets-a219b700` branch. Existing clones must not push
the old history back into this public repository; obtain a fresh clone instead.

## Settings and exit

Default language is English; EN/CN switches language. Close hides to the tray.
Use the tray Exit item to stop the app. Start at login is opt-in and writes only
the current user's Windows Run entry. Disable it before moving/removing the EXE.
Settings are stored under %LOCALAPPDATA%/RIO-Monitor/settings.json.
After exit and disabling autostart, remove the EXE and optional settings folder
to uninstall. No system service is installed.

## Privacy and licenses

See PRIVACY.md and THIRD-PARTY-NOTICES.md. Original code is MIT licensed.
No third-party reference application or private repository history is included.

## Code signing policy

No signing service has approved this project yet. Current development builds
are unsigned. Do not treat this repository as evidence of a valid signature.
Any future signed release must be built from reviewed source and approved by
maintainer Kinkairy. Signing integration and release approval remain pending.
