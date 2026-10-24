# 发行许可与对应源码

RIO 自有程序源码采用 [MIT](../LICENSE)。Qt/PySide、FFmpeg 及其组件保留各自许可证和版权；完整程序附带的美术、字体也不因此变成 MIT。许可材料与程序一起提供，使用者无需安装这些开发依赖。

## 下载和再发行

- [rc0.1.11 Release](https://github.com/Kinkairy/rio-system-monitor/releases/tag/rc0.1.11)：下载程序时同时保留 `RIO-System-Monitor-rc0.1.11-licenses.zip`；内含完整许可正文、第三方声明、实际 EXE 校验值、源码入口及构建说明。
- 同页的 `RIO-FFmpeg-6.1.1-slim-sources.zip` 包含当前精简转换器的 FFmpeg、libaom、zlib 原始源码归档和构建配方。它只对应 rc0.1.11 的精简转换器，不代表 rc0.1.10 的完整 Gyan 构建。
- [Qt/PySide 对应源码与 SHA-256](third-party/qt/SOURCES.json) 提供免费的准确版本上游下载；完整 Qt 源码含库、插件、构建脚本和第三方组件，`pyside-setup` 含 PySide/Shiboken。源码由这些清楚列出的上游服务器提供，不要求登录或访问私有仓库。
- 再发行完整程序时，应同时提供许可附件和这些对应源码入口。以后 `Build-Windows.cmd` 会把材料放进 EXE 的 `licenses/`，并在 `dist/` 生成独立许可 ZIP。已发布的 rc0.1.10/11 EXE 没有重打包；其补充材料放在各自 Release 附件中，程序校验值与原标签保持。

当前版本为 Qt/PySide/Shiboken **6.12.0**（官方未改 Windows x64 动态库）和 FFmpeg **6.1.1**（RIO 自编，GPLv3，外部组件 libaom **3.8.2**、zlib **1.3.1**）。Qt 的 LGPLv3、所引用的 GPLv3、上游其他许可及版权声明见 [Qt 目录](third-party/qt/README.txt)；FFmpeg 的完整配置、来源和构建方法见 [FFmpeg 目录](third-party/ffmpeg/README.txt) 和 [构建脚本](../tools/build_ffmpeg_slim.sh)。所有组件均保留无担保条款。

旧 rc0.1.10 使用 Gyan 的 `6.1.1-essentials_build`，其原始 [README](third-party/ffmpeg/GYAN-6.1.1-README.txt) 保留准确 FFmpeg 源提交、功能和外部库版本；发行来源是 [Gyan 6.1.1](https://github.com/GyanD/codexffmpeg/releases/tag/6.1.1)。这些旧外部库不应被误报为当前三个精简源码归档；本仓没有声称已经重现或持有该旧构建所有外部库的对应源码。

## 修改或替换 Qt/PySide

RIO 不限制为了修改 LGPL 库或调试这些修改而进行的逆向工程。可以替换兼容的动态库，也可以用公开的 MIT 程序源码重新构建。单文件 EXE 每次启动会临时解包，因此不要修改一次性的临时目录；下面的重建方式可保留修改。程序没有签名校验或账号机制来阻止运行自行修改的 Qt 库。

1. 从公开仓库获取当前源码。Windows x64 使用 Python 3.12，新建构建环境并安装 `requirements-build.txt`；为复现现有版本，指定 `PySide6==6.12.0` 和 `pyinstaller==6.22.3`。对应 PySide/Shiboken 源码的 `README.md` 与官方 [Windows 构建说明](https://doc.qt.io/qtforpython-6/building_from_source/windows.html) 说明如何用 MSVC/CMake 构建这些库。保持 Python、Qt 和 Shiboken 的 ABI 兼容。
2. 在自己的源码目录保存以下脚本为 `restore_runtime_assets.py`，然后执行 `python restore_runtime_assets.py <收到的 RIO-System-Monitor.exe>`。只提取已经随收到的程序提供的运行素材和转换器；不需要私有仓库的原图、母版或字体工程，也不把提取结果提交 Git。

```python
from pathlib import Path
import sys
from PyInstaller.archive.readers import CArchiveReader

archive = CArchiveReader(sys.argv[1])
for name in archive.toc:
    relative = name.replace('\\', '/')
    if not relative.startswith('assets/') or '..' in Path(relative).parts:
        continue
    target = Path(relative)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(archive.extract(name))
```

3. 把自己构建的兼容 PySide/Shiboken wheel 安装到该构建环境，或在该环境的 `site-packages/PySide6`、`shiboken6` 中替换对应 DLL、绑定和插件。程序源码及 QML 已公开，直接使用正常源码形式，无需解码已编译的应用代码或提供本程序的专有目标文件。
4. 按主 README 的精简打包说明构建同版 NumPy 组件并设置 `RIO_NUMPY_WHEEL`；FFmpeg 可直接复用收到的 rc0.1.11 中提取的 `assets/media/ffmpeg.exe`，也可按公开配方构建。执行 `Build-Windows.cmd`。已有温度辅助服务构建步骤保持不变，编译不会安装驱动。
5. 运行 `dist/RIO-System-Monitor-Qt.exe --version`，再用 `--snapshot preview.png --demo` 验证本地重建。之后可以正常运行该副本；若原实例仍在运行，程序的单实例规则仍适用。这个本地副本无需上传到官方 Release，也不受官方自动更新签名限制；要保留本地修改，请不要主动安装覆盖它的官方新版。

该方法只复用收到的程序中已有运行素材供本地重建，不公开素材母版，也不扩大美术授权。字体保留其原有 OFL/CC0 等条款。发布含修改库的副本时，应提供所修改库的相应源码、构建修改和许可材料。

## 维护范围

本次只补 Qt/PySide 与 FFmpeg 的发行材料和构建接入，程序版本、采集、绘图、音乐、USB、更新逻辑及资源未变。许可文本不是全面法律审计的保证；尤其旧第三方整合包的来源应以其提供者记录核实。升级依赖时应同步更新实际版本、对应源和声明，不能把这份清单用于未经核对的新组件。
