# RIO System Monitor

适用于兼容 USB 圆屏的 Windows 桌面监控程序。电脑采集数据并输出 480×480 RGB565 画面，Qt Quick 提供设置与托盘界面。它不属于 Windows 扩展显示器，程序也不在屏幕芯片中运行。

## 当前版本与目录

当前版本为 **rc0.1.1**，可从 [GitHub Release](https://github.com/Kinkairy/rio-system-monitor/releases/tag/rc0.1.1) 下载完整程序。保留 `rc0.1` 标签作为原有基准。本版继承减少托盘无用绘制、缩小温度环缓存和释放已拆分图集的 CPU/内存优化；结果与验证边界见[性能说明](docs/performance.md)。源码入口支持 `python launch.py --version`，托盘提示显示版本号。

`main` 在该标签之后修正歌词查询：移除不稳定的 QQ 桌面搜索，兼容歌手显示别名；先查播放器自身接口，获取不到再并发查询其他 QQ/网易云/酷狗/LRCLIB 接口，先取得有效同步歌词的先显示。歌名区域缩为居中的 240px，超出后往返滚动，避免遮住侧边仪表。`rc0.1` 标签保留为原有基准。修正与验证记录见[音乐模式说明](docs/music-mode.md#fix-20261023-qq-lyrics-failed-online-lyric-lookup)。

| 位置 | 用途 |
| --- | --- |
| `launch.py`、`src/rio_monitor/` | 唯一桌面入口、采集、绘制、音乐与 USB 通信源码 |
| `assets/ui/` | 公开的 QML 界面源码 |
| `sensors/` | 温度辅助服务源码与构建脚本 |
| `tools/` | 私有素材导入、校验与公开源码检查 |
| `tests/`、`docs/` | 回归测试、功能与验证说明 |
| `assets/` 中其余内容 | 从私有仓库导入的本地素材及构建依赖，Git 忽略，不公开 |
| `build/`、`dist/` | 可重建的临时构建输出，Git 忽略，交付后可清理 |

源码仓库只维护源码、文档和构建配置。2026-10-23 主人明确允许公开发布完整 EXE，因此可在 GitHub Release 中发布含素材的完整程序；素材原文件仍留在私有仓库，不进入公开源码 Git。CI 只检查源码，不上传素材、预览或中间构建产物。清理旧构建时保留当前程序、私有输入、配置和必要构建依赖。

## 自动更新（AUTOUPDATE-20261023）

主人要求加入自动检测和更新，并明确选择通过公开 GitHub 下载完整 EXE。本次从干净源码 `ec0de054989fe81934f887774674e236af8e2048` 连续修正歌词；原有运行文件及 `rc0.1` 恢复标签保留。计划仅为打包 EXE 加入 GitHub Releases 检测：启动后后台查询一次，此后每六小时查询；有更新则流式下载并核对 Release 资产 SHA-256，正常退出后替换当前文件，下次启动使用新版。源码运行、界面截图和测试模式不联网更新。失败保留旧程序，不安装驱动、不修改歌曲/屏幕内容或用户配置。

范围：一个标准库更新模块、现有 Qt 启动/退出接入、版本与说明；不引入更新框架、额外服务或账号凭据。验收需覆盖版本判断、正常下载、下载损坏、退出后替换，以及公开 Release 的匿名检测/下载；真实未来版本升级与用户验收单独记录。AMF 项目查询仍为 `not_found`，以上是现有项目入口中的变更记录，不声称已登记 AMF。

实现与本地验证：后台检测及下载、正常退出后替换均已实现。三项更新检查覆盖公开版本选择、完整/损坏下载、Windows 下等待进程退出后真实替换文件；首次替换检查暴露的 PowerShell 哈希命令兼容问题已改用系统 .NET 哈希并重新通过。完整源码检查 165 项通过，无跳过，Windows 打包启动通过。EXE 内版本为 `rc0.1.1`；既有 `rc0.1` 标签与运行中的文件保留。发布资产名固定为 `RIO-System-Monitor.exe`，GitHub Release 的 SHA-256/大小与本地交付副本核对；完整 EXE 108,656,957 字节，SHA-256 为 `f0bdeb32fbbe1ae4f9b556ef5536433f1ea01090f657755eea96c373d0f0c98b`。

公开发布验收：`rc0.1.1` 标签对应源码 `66d5a50944269b7dd11133b35cdedb4ebabf2c82`，公开 Release 与其 EXE、SHA256SUMS.txt 已读回确认。使用最终 EXE 中的实际更新模块，不带 GitHub 登录凭据，以旧版本 `rc0.1` 检测并完整下载 108,656,957 字节，SHA-256 与本地构建及 Release 一致；以当前版本检测则没有重复更新。下载速度取决于 GitHub 线路，本机首次整包下载用了数分钟。更改下载通道前的小范围探针不影响已验证的正式网页下载路径。退出后替换已在 Windows 独立进程及文件上验证；真实未来版本的整套升级和实体屏使用仍需届时验证。首次使用需手动退出旧版并打开本版，此后才具备自动更新能力。

交付后已用原有受限路径脚本清理 20 个构建/验证缓存文件，共 390,018,848 字节。源码、私有输入、原有恢复基准和运行中的 EXE 保留；源码 Git 不含素材或构建包。

## 功能

- CPU 使用率、可用 CPU 温度、内存和网络速率；通过 Windows DXGI/PDH 选择实际活动显卡，不轮流展示闲置显卡，不显示硬件型号和 GPU 温度。
- 采用 11 的机器人动画代码和 atlas，天气动画与时钟保持独立；温度历史曲线带绿色渐变透明填充，只覆盖已有曲线，缺失数据留空。修复原温度环遮罩右上方两格缺口；只调整天气温度数字与下划线的距离，CPU 温度数字位置不变。
- 设置实时生效并自动保存；旋转预览不越界。每次启动都自动连接并传输实时监控，窗口默认进入托盘；关闭和 Save 保存后收起。托盘菜单固定为退出、设置、登录后启动三项。
- 所有按钮复用 ActionButton，圆箭头和关闭按钮由它派生；确认框复用等宽的 Cancel / OK。选择文件与城市结果也使用相同的高亮、按下和投影样式。EN/CN 是无边框的一体式滑块，轨道带内凹阴影，滑块无字，露出的绿色语言文字生效。开关共用 RioSwitch，悬停高亮并带内侧阴影。安装/卸载或媒体任务进行时，底部中央显示三个加载点。
- 启动先发现系统、已有 LHM/OHM WMI 和 RIO 温度服务。已有其他软件的有效接口直接读取，开关置灰禁用。缺少接口时，手动开启开关并接受 Windows 管理员确认，安装官方签名 PawnIO 2.2.0 与 CPU 只读服务。关闭开关卸载我们安装的组件；预先存在的 PawnIO 保留。普通启动和收起窗口不会安装、卸载或要求提权。[组件与权限说明](docs/temperature-component.md)
- 新用户默认通过公网 IP 定位天气，保留已有手动城市。[隐私说明](PRIVACY.md)
- 音乐欣赏模式采用 11 的 `436cbff` / `53b62d8` / `e0c281f` 代码和私有字体、唱片素材。主设置中直接使用与其他选项相同的开关；开启后播放音乐自动切换到唱片、歌词与真实频谱画面，暂停或停止满 30 秒回到监控。期间恢复播放取消倒计时，关闭开关立即返回。在线歌词默认开启，音乐模式启用后才查询。两种画面使用弹出并轻微回弹的过渡；歌手字号加大，长歌名往返滚动。封面延迟返回或读取失败时每两秒重试，成功后保留至换歌；没有封面时使用默认唱片，有封面时也使用新版 RIO 黄圈。[音乐模式说明](docs/music-mode.md)
- 媒体转换和预览支持图片、动态图和视频，原文件及转换后 GIF 均不超过 3,400,000 字节。文件与城市弹窗共用 280×356 的窗口；顶部选择文件、中间预览、底部写入。打开时显示最后成功写入的本地记录，选择文件后显示新内容；没有记录时显示未知。恢复默认确认后直接执行。默认使用私有提交 `fa2f691` 的彩色动画。资源上传在设备查询后等待一秒，再开始擦写；本机默认动画的 250 个擦除块、250 个写入块和结束命令均已成功应答，用户确认断电重接后自动播放新动画。USB 文件回读未实现；失败后恢复原来的实时输出。[兼容性实测](docs/device-resource-compatibility.md)、[存储与转换说明](docs/screen-storage.md)

## 设备与验证边界

已验证的设备接口为 WinUSB `2A55:9990`，LCD 查询为 480×480。程序只接受兼容单设备和已核验的尺寸。实时监控发生 USB 故障后，等待旧句柄完全关闭，再重新枚举并连接，失败按 1、2、4、5 秒间隔重试，无需退出程序；启动时未插屏也会继续检测。重连后重新查询尺寸并发送最新画面。屏内内容写入期间及成功后的内容播放模式不抢占设备；写入失败恢复实时模式后自动重连，不自动重试擦写。正常退出停止重连。关闭其他占用屏幕的软件。

本地实时 RGB565 输出已经取得设备成功回包；全帧链路约 13 FPS，回包与实际显示分别验证。30 FPS 是绘制和视频转换目标，未声称实体屏达到 30 FPS。资源写入协议具有地址边界、互斥和失败停止测试，实物默认动画上传已通过逐块应答，断电重接播放新动画由用户确认。USB 文件回读、温度组件卸载/重启后的服务启动仍待验证。没有刷固件、APPLOAD 或任意地址写入入口。

## 源码与私有素材

唯一受支持的桌面入口为 `python launch.py`（内部调用 `rio_monitor.qt_app.main`）。旧 Tkinter 设置界面及旧单卡 NVIDIA 采集模块已移除；当前 GPU 数据继续走 `sensors.py` / `windows_gpu.py`。源码截图仍可通过 `python launch.py --snapshot <file.png> --demo` 生成，需先导入私有素材。

公开仓库只包含源码和文档。图像、atlas、字体、图标、动画数据和默认 GIF 保存在私有 `Kinkairy/usb-round-screen`；公开仓库不提供这些素材的许可。原公开仓库已改名私有归档为 `Kinkairy/rio-system-monitor-private-archive`，完整原历史另存于私有仓库的 `archive/rio-system-monitor-assets-a219b700`。旧克隆请勿把含素材的历史重新推送回来。

Windows 本地构建使用 Python 3.12，需要访问私有素材并自行提供本地转换器：

```text
python tools/import_private_assets.py --source "<private-repo>/monitor-assets" --startup-loop "<private-repo>/artwork/startup-loop/RIO-System-Monitor-color-accent-loop.gif" --music-font "<private-repo>/artwork/music-mode/fonts/RIOPixel-Regular.ttf" --music-art "<private-repo>/artwork/music-mode" --ffmpeg "<local-FFmpeg-6.1.1>/ffmpeg.exe"
Build-Windows.cmd
```

导入器校验固定 SHA-256，将素材和 FFmpeg 放进本地忽略的 assets 目录；默认 GIF 必须为 `fa2f691` 版本。当前转换器是 Windows x64 FFmpeg 6.1.1 essentials，SHA-256 `04e1307997530f9cf2fe35cba2ca7e8875ca91da02f89d6c7243df819c94ad00`。构建时从官方发行页下载并验证 LHM/PawnIO，编译温度辅助服务，再打包单 EXE；构建不会安装驱动。

```text
python tools/check_source_only.py
python tools/verify_private_assets.py
set PYTHONPATH=src
python -m unittest discover -s tests -v
```

未导入素材时，依赖图像、字体、默认动画或本地转换器的测试会明确跳过；导入后执行完整测试。公开 CI 仅检查源码边界和不含素材的测试，不读取私有仓库，不上传 EXE、截图、预览或其他构建包。完整 EXE 只通过主人授权的 GitHub Release 发布，素材原文件仍保持私有。

## 配置、安装与许可

配置为 `%LOCALAPPDATA%/RIO-Monitor/settings.json`，JSON 格式。成功写入的预览记录位于同目录的 `screen-content/`，每台已写入设备包含 GIF 与校验 JSON；本地导入的歌词位于 `lyrics/`。字体、默认动画、音乐接口依赖和转换器包含在本地 EXE 中，运行时有临时解包与预览文件。选择安装温度组件后，另有 `%ProgramFiles%/RIO-Monitor/Temperature` 和 `%ProgramData%/RIO-Monitor` 中的服务/数据文件。退出、关闭温度开关和删除程序各自的行为详见组件文档。

原代码采用 MIT 许可，私有素材和第三方依赖不因此改为 MIT。见 [第三方说明](THIRD-PARTY-NOTICES.md) 和 `docs/third-party/ffmpeg/`。主程序开发构建未签名；签名 PawnIO 驱动不代表 GUI 已签名。源代码测试、真实设备通信与用户视觉验收分别记录，不以其中之一代替其他结果。

