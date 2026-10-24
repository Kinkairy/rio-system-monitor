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

对应版本的第三方源码与发行许可随发行版提供。使用收到的单文件程序替换兼容 DLL 的方法见[当前发行许可文档](https://github.com/Kinkairy/rio-system-monitor/blob/main/docs/distribution-licenses.md)。
