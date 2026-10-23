# Third-party notices

- Optional temperature support uses the unmodified LibreHardwareMonitor 0.9.6
  release (MPL-2.0) and signed PawnIO 2.2.0 installer, fetched and verified by
  `sensors/Build-Sensors.ps1`. No driver binary is tracked in this repository.
  See `docs/temperature-component.md` for sources and explicit installation behavior.
- Local video conversion uses a separately supplied FFmpeg 6.1.1 executable.
  Full GPLv3 terms and build notices are in `docs/third-party/ffmpeg/`.
  The importer copies these notices into a private binary build; no FFmpeg binary
  or private artwork is distributed by this public repository.

- Born2bSporty FS: Copyright Haley Wakamatsu (UkiyoMoji Fonts) 2022-2026.
  Author page explicitly grants SIL OFL 1.1:
  https://2gd4.me/tidbit/shavian-fonts.html . The author's linked download is
  https://2gd4.me/tidbit/shavian-fonts/born2bsporty-fs.otf . Its SHA-256 is
  70a2365829348f9002a5ed188329ac2aef8ce08838554a1f1947bba3715062c3,
  byte-identical to assets/fonts/Born2bSporty.otf. The file retains the conflicting
  FontStruct Non-Commercial name-table string; it has not been altered. The
  explicit author-page OFL grant is recorded here rather than concealing it.
- Noto Sans CJK JP (assets/clock.otf): see assets/FONT-LICENSE.txt.
- Pixel Operator HB: see assets/fonts/PixelOperator-LICENSE.txt (CC0).
- Python, Pillow, psutil, PySide6/Qt and PyInstaller retain upstream licenses.
  Binary redistribution must include applicable dependency notices and satisfy
  Qt/PySide LGPL obligations. This source-preparation snapshot is not a completed
  binary license/compliance audit or a signed release.

RIO artwork, fonts, icons and animation materials are held in a private repository
and are not distributed here. Font paths above refer to an authorized local asset
import. A private binary build must retain the original notices with the material.
The public source's MIT license does not grant any rights to private artwork or
relicense third-party materials.


Music mode adds NumPy (BSD-3-Clause), PyAudioWPatch/PyAudio and PortAudio (MIT), and PyWinRT (MIT). The applicable upstream licenses must accompany redistributed binary bundles. Source references: https://numpy.org/doc/stable/license.html ; https://github.com/s0d3s/PyAudioWPatch/blob/master/LICENSE.txt ; https://github.com/pywinrt/pywinrt . LRCLIB is an optional external service, not bundled code. No LX Music source is copied.
