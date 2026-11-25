# RIO System Monitor

RIO System Monitor 在 Windows 上采集 CPU、GPU、内存、温度与网络状态，通过 USB 显示在兼容的 RIO 监控屏上。播放音乐时可显示专辑封面、频谱与同步歌词。

## 下载与更新

当前公开 Windows 主程序为 **rc0.1.27**。[下载 rc0.1.27](https://github.com/Kinkairy/rio-system-monitor/releases/tag/v0.1.27) · [历史版本](https://github.com/Kinkairy/rio-system-monitor/releases)。本版可从 GitHub 手动下载；程序内更新源指向 Gitee，需待该发行同步后才能通过设置中的「Check updates」获取。

方寸山与风神 Pro 可在「设置 → 扩展」启用。RIO 按模块清单下载并校验对应安装包。[扩展模块发行页](https://github.com/Kinkairy/rio-system-monitor/releases/tag/modules) · [模块更新清单](https://github.com/Kinkairy/rio-system-monitor/releases/download/modules/RIO-Modules.json) · [主程序更新服务](https://gitee.com/kinkairy/rio-system-monitor-updates)

## 使用文档

- [音乐模式、播放器与同步歌词](docs/music-mode.md)
- [温度监控组件](docs/temperature-component.md)
- [屏幕内容与存储](docs/screen-storage.md)
- [设备资源兼容性](docs/device-resource-compatibility.md)
- [恢复说明](docs/recovery.md)

## 项目文件与授权

公开仓库维护项目介绍、使用文档、许可说明、发行入口，以及版本声明和通用监控数据模型这两份基础源码。完整程序源码与扩展实现保存在私有开发项目中。美术原图、分层、字体母版和独立素材包均不对外提供。官方安装包与扩展包包含运行所需的资源。

[基础源码](src/rio_monitor) · [项目许可证](LICENSE) · [隐私说明](PRIVACY.md) · [第三方组件及其许可证](THIRD-PARTY-NOTICES.md) · [发行许可与对应材料](docs/distribution-licenses.md)
