Qt / Qt for Python redistribution notice
=======================================

RIO rc0.1.11 uses unmodified upstream PySide6, PySide6_Essentials,
PySide6_Addons and shiboken6 6.12.0, with Qt 6.12.0 for Windows x64.
Qt build: shared (dynamic), release, MSVC 2022, Python limited API.
Copyright (C) The Qt Company Ltd. and other contributors; individual source
files and the accompanying third-party notices retain their own copyrights.
Qt is a trademark of The Qt Company Ltd.

The Qt/PySide/Shiboken libraries used by RIO are supplied under the GNU Lesser
General Public License version 3. See LGPL-3.0-only.txt and its incorporated
GPL-3.0-only.txt. GPL-2.0-only.txt and Qt-GPL-exception-1.0.txt retain upstream
alternative/tool terms; they do not change RIO's MIT source license.
THIRD-PARTY-NOTICES.txt preserves notices from the exact upstream source
archives, including FreeType, HarfBuzz, image codecs and Python-derived code.
MESA-LLVM-NOTICES.txt retains official Qt notices for the software OpenGL
fallback and its supporting code. These components come without warranty.

The retained DLLs come from qtbase, qtdeclarative and qtsvg; image plugins also
come from qtimageformats. SOURCES.json gives versioned, free upstream source
downloads and SHA-256 values. The complete Qt source archive additionally
covers optional plugins and the additional Qt modules retained in rc0.1.10.
The pyside-setup source includes PySide and Shiboken. RIO applies no patches
to these upstream libraries and provides no additional license restriction
on modifying or replacing them, or reverse engineering to debug such changes.

The existing bundles also contain an unused Qt Virtual Keyboard input-context
plugin, whose upstream module is GPLv3, not LGPL. Its GPL text is supplied here
and its source is in the complete Qt source download. The QtVirtualKeyboard
library/QML module is not used by RIO. Do not treat every file collected from
PySide6 as LGPL merely because the wheel metadata offers an LGPL option.

See ../../distribution-licenses.md for practical library replacement/rebuilding
instructions, including recovering runtime resources from a received EXE.
No private artwork or font original is needed from a private repository for
that local rebuild. This does not license the artwork as MIT or publish its
editable/high-resolution source. The public source tree contains no images,
fonts, Qt SDK, binary libraries or upstream source archives.

Upstream licensing:
https://doc.qt.io/qtforpython-6/licenses.html
https://www.qt.io/development/open-source-lgpl-obligations
https://doc.qt.io/qt-6/qtvirtualkeyboard-index.html#licenses
https://wiki.qt.io/MesaLlvmpipe

When upgrading Qt/PySide, refresh the versioned sources and license notices
for the actual shipped libraries. Do not silently reuse 6.12.0 source entries
for a different binary release.
