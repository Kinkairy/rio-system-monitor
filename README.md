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

Use Python 3.12 on Windows. Run Build-Windows.cmd to produce the single-file
windowed executable in dist/. Dependencies are downloaded from PyPI.
Tests: set PYTHONPATH=src, then python -m unittest discover -s tests -v.
Entry point: launch.py -> rio_monitor.qt_app. Older Tk modules are legacy only.
The workflow captures actual packaged Qt windows and checks tray/window lifecycle.

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
