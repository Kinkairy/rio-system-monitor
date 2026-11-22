# 发行许可与对应源码

RIO 自有程序源码采用 [MIT](../LICENSE)。Qt/PySide、FFmpeg 及其组件保留各自许可证和版权；完整程序附带的美术、字体也不因此变成 MIT。许可材料与程序一起提供，使用者无需安装这些开发依赖。

## 下载和再发行

- [rc0.1.12 Release](https://github.com/Kinkairy/rio-system-monitor/releases/tag/rc0.1.12)：下载程序时同时保留 `RIO-System-Monitor-rc0.1.12-licenses.zip`；内含完整许可正文、第三方声明、实际 EXE 校验值、源码入口及构建说明。
- 同页的 `RIO-FFmpeg-6.1.1-slim-sources.zip` 包含当前精简转换器的 FFmpeg、libaom、zlib 原始源码归档和构建配方。它对应 rc0.1.11/rc0.1.12 沿用的同一精简转换器，不代表 rc0.1.10 的完整 Gyan 构建。
- [Qt/PySide 对应源码与 SHA-256](third-party/qt/SOURCES.json) 提供免费的准确版本上游下载；完整 Qt 源码含库、插件、构建脚本和第三方组件，`pyside-setup` 含 PySide/Shiboken。源码由这些清楚列出的上游服务器提供，不要求登录或访问私有仓库。
- 再发行完整程序时，应同时提供许可附件和这些对应源码入口。发行构建会将材料放进 EXE 的 `licenses/`，同时提供独立许可 ZIP。已发布的 rc0.1.10/11 EXE 没有重打包；其补充材料放在各自 Release 附件中，程序校验值与原标签保持。

当前版本为 Qt/PySide/Shiboken **6.12.0**（官方未改 Windows x64 动态库）和 FFmpeg **6.1.1**（RIO 自编，GPLv3，外部组件 libaom **3.8.2**、zlib **1.3.1**）。Qt 的 LGPLv3、所引用的 GPLv3、上游其他许可及版权声明见 [Qt 目录](third-party/qt/README.txt)；FFmpeg 的完整配置、来源和构建方法见 [FFmpeg 目录](third-party/ffmpeg/README.txt) 及对应发行页的 FFmpeg 源码附件。所有组件均保留无担保条款。

旧 rc0.1.10 使用 Gyan 的 `6.1.1-essentials_build`，其原始 [README](third-party/ffmpeg/GYAN-6.1.1-README.txt) 保留准确 FFmpeg 源提交、功能和外部库版本；发行来源是 [Gyan 6.1.1](https://github.com/GyanD/codexffmpeg/releases/tag/6.1.1)。这些旧外部库不应被误报为当前三个精简源码归档；本仓没有声称已经重现或持有该旧构建所有外部库的对应源码。

## 在本地替换 Qt 动态库

RIO 允许使用兼容的修改版 Qt、调试这些修改，以及为此所需的逆向工程。Windows 单文件版可以直接从已获取的 EXE 重新装入动态库。下面的方法用原发行程序作为应用部分，接受由用户提供的同名兼容 DLL，保留原始 EXE。

使用 Python 3.12 安装 PyInstaller 6.22.3。将以下通用脚本保存为 `replace_qt_dll.py`，在本机运行 `python replace_qt_dll.py RIO-System-Monitor.exe Qt6Core.dll RIO-local.exe`。目标文件名应为新文件；替换同一套 Qt 的其他库时，可以上一步输出作为下一步输入。库必须匹配发行版的 Qt/PySide ABI、Windows x64 架构和对应的插件版本。[Qt/PySide 对应源码](third-party/qt/SOURCES.json) · [PySide Windows 构建说明](https://doc.qt.io/qtforpython-6/building_from_source/windows.html)

```python
from pathlib import Path
import struct
import sys
import zlib
from PyInstaller.archive.readers import CArchiveReader
from PyInstaller.archive.writers import CArchiveWriter

exe, library, output = map(Path, sys.argv[1:])
source = exe.read_bytes()
archive = CArchiveReader(str(exe))
name = 'PySide6\\' + library.name
old = archive.toc[name]
start = archive._start_offset
magic, _, old_toc, _, pyver, pylib = struct.unpack_from(
    archive._COOKIE_FORMAT, source, len(source) - archive._COOKIE_LENGTH)
assert magic == archive._COOKIE_MAGIC_PATTERN
replacement = library.read_bytes()
block = zlib.compress(replacement) if old[3] else replacement
rows = [(0, 0, 0, 0, 'o', opt) for opt in archive.options]
for key, values in archive.toc.items():
    entry = (old_toc, len(block), len(replacement), old[3], old[4]) if key == name else values
    rows.append((*entry, key))
toc = CArchiveWriter._serialize_toc(rows)
new_toc = old_toc + len(block)
length = new_toc + len(toc) + archive._COOKIE_LENGTH
cookie = struct.pack(archive._COOKIE_FORMAT, magic, length, new_toc, len(toc), pyver, pylib)
with output.open('xb') as stream:
    stream.write(source[:start + old_toc])
    stream.write(block)
    stream.write(toc)
    stream.write(cookie)
assert CArchiveReader(str(output)).extract(name) == replacement
```

运行 `RIO-local.exe --version` 核对生成的本地副本。修改过的文件拥有新的散列值，原发行文件的签名与校验值只适用于原文件。再发行修改后的第三方库时，请随附相应许可和所需的对应材料。
