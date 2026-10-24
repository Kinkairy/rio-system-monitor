# Third-party notices

- Optional temperature support uses the unmodified LibreHardwareMonitor 0.9.6
  release (MPL-2.0) and signed PawnIO 2.2.0 installer, fetched and verified by
  `sensors/Build-Sensors.ps1`. No driver binary is tracked in this repository.
  See `docs/temperature-component.md` for sources and explicit installation behavior.
- Local video conversion uses a separately supplied FFmpeg 6.1.1 executable.
  The RIO slim variant uses unmodified upstream FFmpeg with decoder-only libaom
  3.8.2 and zlib 1.3.1; their license and patent notices are retained alongside it.
  Full GPLv3 terms and build notices are in `docs/third-party/ffmpeg/`.
  The importer copies these notices into the local binary build. The owner has
  authorized full executable distribution through GitHub Releases; raw converter
  and artwork files are not tracked in the public source tree.

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
- Qt, PySide6 and Shiboken 6.12.0 are copyright The Qt Company Ltd. and
  other contributors. RIO uses the unmodified official Windows x64 dynamic
  libraries under LGPLv3. The full LGPLv3/GPLv3 terms, additional collected
  plugin terms, copyright notices, exact corresponding-source downloads and
  SHA-256 values are in `docs/third-party/qt/`. Software OpenGL (Mesa/LLVM)
  and the Qt image/third-party component notices are retained there too.
  See `docs/distribution-licenses.md` for replacing/rebuilding these libraries.
  Reverse engineering to debug LGPL library modifications is permitted.
- Python, Pillow, psutil and PyInstaller retain their upstream licenses.
  Supplementary release license ZIPs also retain text notices from the exact
  distributed EXE. This focused Qt/PySide/FFmpeg material update is not a
  comprehensive legal audit of every dependency or a signed release.

RIO artwork, fonts, icons and animation source materials are held in a private
repository. Authorized complete executables may be distributed as Release assets;
the original asset files remain outside the public source Git tree. Font paths
above refer to an authorized local import. Binary builds retain original notices.
The public source's MIT license does not grant any rights to private artwork or
relicense third-party materials.


Music mode adds NumPy (BSD-3-Clause), PyAudioWPatch/PyAudio and PortAudio (MIT), and PyWinRT (MIT). The applicable upstream licenses must accompany redistributed binary bundles. Source references: https://numpy.org/doc/stable/license.html ; https://github.com/s0d3s/PyAudioWPatch/blob/master/LICENSE.txt ; https://github.com/pywinrt/pywinrt . LRCLIB is an optional external service, not bundled code. No LX Music source is copied.

The optional same-version NumPy 2.5.4 slim build omits external BLAS/LAPACK.
Original NumPy component licenses are in
docs/third-party/numpy/ and bundled under licenses/numpy/. See its README for
the unmodified source, build inputs and recipe.
