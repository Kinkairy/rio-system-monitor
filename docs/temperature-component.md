# 温度监控组件

设置中的“温度监控”开关始终可见。程序启动先检查系统 CPU 温度、已有 LibreHardwareMonitor / OpenHardwareMonitor 的 WMI 接口，以及已安装的 RIO 温度服务。没有可用接口时，不会在启动时安装驱动或要求管理员权限。

安装或卸载过程中，设置页底部中央显示三个依次明暗变化的绿色圆点；完成、失败或取消后自动隐藏。界面收起后停止动画，重新打开时继续显示当前状态，安装和卸载状态文字跟随所选语言。

检测到系统或其他软件提供的可用 CPU 温度接口时，直接读取，开关显示灰色并禁用；不安装或卸载对方组件。我们安装的 RIO 服务保留可操作开关。

首次手动开启且确实缺少接口时，Windows 弹出管理员确认，安装官方签名版 PawnIO 2.2.0 和 RIO 温度服务。取消确认会恢复关闭状态。后续普通启动及开机登录启动不再要求管理员权限。按所有者最新要求，关闭温度开关时卸载我们安装的组件，需要一次管理员确认；之后重新开启且缺少接口时需再次安装。收起到托盘和正常退出不触发卸载。取消卸载的管理员确认会恢复原开关和采集状态。

安装时在管理员保护的 State/install.json 中记录 PawnIO 是否由 RIO 新装及其服务路径。卸载只停止并删除路径核验通过的 RIO 服务；仅当可信记录证明 PawnIO 由我们安装且服务路径仍匹配时，调用原版签名安装器的卸载功能。原本已有、记录缺失或路径改变的 PawnIO 均保留。只删除本程序已知活动文件；Recovery 和未知文件保留，不递归删除系统目录。安装/卸载需要重启时仅提示，不自动重启。

主程序始终以普通权限运行。服务自动启动，在系统权限下使用 LibreHardwareMonitor 0.9.6 读取 CPU 温度；不启用主板、风扇、存储或显卡控制。GPU 使用 Windows DXGI/PDH 跟随实际活动显卡，不循环切换，不显示 GPU 温度。支持 Windows x64；本机现有 .NET Framework 用于组件，无另装 .NET Runtime 流程。

## 文件和权限

- 服务名：`RIOHardwareMonitor`。服务、依赖库安装在 `%ProgramFiles%/RIO-Monitor/Temperature/`，普通用户只有读取和运行权限。
- `%ProgramData%/RIO-Monitor/State/sensors.json` 是只读结果，普通用户不能修改。结果超过 5 秒或值无效时，程序显示 `--`。
- `%ProgramData%/RIO-Monitor/Control/enabled.json` 是可写的布尔开关；服务只解析 enabled，不接受命令、文件路径或可执行代码。
- 组件不监听网络端口，不修改驱动签名策略，不使用 PawnIO unrestricted 模式，不让普通用户直接访问底层驱动。
- 修复覆盖的旧组件保存在安装目录的 Recovery 子目录。已有同名服务但路径不属于本项目时，安装会拒绝覆盖。
- 安装器报告需要重启时只提示用户，不自动重启电脑。

## 构建和来源

`sensors/Build-Sensors.ps1` 校验固定 SHA-256 的官方包、PawnIO Authenticode 签名，编译 CPU 只读服务，并生成每个依赖文件的哈希清单。主构建会调用此步骤。主程序包含组件安装材料，启动时不会执行安装。

- LibreHardwareMonitor 0.9.6：[官方源码和许可](https://github.com/LibreHardwareMonitor/LibreHardwareMonitor/tree/v0.9.6)，MPL-2.0；库和依赖使用官方未修改发行文件。
- PawnIO 2.2.0：[官方发行页](https://github.com/namazso/PawnIO.Setup/releases/tag/2.2.0)。安装器按其内置声明保持原样分发。

服务和安装逻辑已编译，发现、无接口、已有接口、取消管理员确认、关闭、重新开启、保存失败和过期值路径有测试。真正的管理员安装、Windows 重启后服务启动和本机 CPU 温度读数，仍需在用户开启开关并接受 Windows 确认后验证。
