# 随包驱动：PEAK PCAN-Basic API

本目录解决一个高频现场问题：**装了 PEAK 设备驱动，PeakCAN 设备仍然连不上**。

## 为什么需要

PEAK 在 Windows 上有两个互相独立的组件：

| 组件 | 文件 | 作用 | 本机是否已装 |
|---|---|---|---|
| 设备驱动（内核） | `C:\Windows\System32\drivers\pcan_usb.sys` | 让 Windows 识别 PCAN-USB / PCAN-USB FD 硬件 | 装了才能被设备管理器看到 |
| PCAN-Basic API（用户态） | `PCANBasic.dll` | 应用程序（python-can）调用硬件的编程接口 | **必须单独安装** |

python-can 4.3.1 的 `can/interfaces/pcan/basic.py` 用
`ctypes.util.find_library("PCANBasic")` 解析 DLL，Windows 上只搜索 `PATH`。
只有内核驱动、没有 API DLL 时，连接报 `PCANBasic library not found`。

## 本目录内容

| 文件 | 来源 / 说明 |
|---|---|
| `PCANBasic.dll` | PEAK PCAN-Basic **5.1.0.1194** 官方包 `x64/PCANBasic.dll`，64 位 PE（machine `0x8664`），731 240 字节，SHA256 `2f273d021197e30d7b44fffde8587e5d4b138b41f6a3c1f27d994b53feeb538e`。未做任何修改。 |
| `PEAK_ReadMe.txt` | 官方包内 ReadMe 原文（含官方推荐的手动安装方式）。 |
| `PEAK_EULA.txt` | PEAK 最终用户许可协议全文（2026-11-22 取自 https://www.peak-system.com/quick/eula）。 |
| `README.md` | 本说明。 |

官方包：`https://www.peak-system.com/fileadmin/media/files/PCAN-Basic.zip`
版本页：`https://www.peak-system.com/support/software-information/development-kits/pcan-basic/`

## AITestLab 如何使用

- `aitestlab.spec` 把本目录收进安装包的 `_internal/drivers/`；
- `app/main.py` 启动时把该目录加入 `PATH` 并调用 `os.add_dll_directory()`；
- `plugins/peakcan_plugin.py` 在 `connect()` 前再确认一次 DLL 可解析。

所以 **per-user 安装、不需要管理员权限、不写 System32**。诊断接口
`GET /api/system/drivers` 会返回：设备驱动是否存在、API 是否可解析、随包 DLL 路径。

## 仍然连不上时

1. 打开 `http://127.0.0.1:<port>/api/system/drivers` 看 `pcan` 段：
   - `device_driver_present=false` → 硬件驱动没装，装官方
     **Device Driver Setup**：https://www.peak-system.com/quick/DrvSetup
   - `device_driver_present=true` 且 `api_library` 有值、`ready=true` → API 已就绪，
     问题在通道/波特率/硬件；用插件 `{"action":"diagnose"}` 看候选通道。
2. 常用通道 `PCAN_USBBUS1`，接口选 `pcan`（Windows 不支持 SocketCAN）；
   CAN FD 硬件需勾选 `fd` 并设 `data_bitrate`。
3. 官方完整安装方式见 `PEAK_ReadMe.txt`：把 `x64/PCANBasic.dll` 复制到
   `Windows\System32`（需管理员），或运行 Device Driver Setup（推荐）。

## 许可要点（务必遵守）

依据 `PEAK_EULA.txt`：

- **2.3 / 2.4**：允许随第三方应用向第三方分发，但必须**附上本许可全文**且**免费分发**，
  不得单独收费；
- **2.6**：只可与 **PEAK 原厂硬件或 PEAK OEM 硬件**配合使用，禁止用于第三方硬件；
- **4.2 / 4.3**：不得移除版权信息，且须让用户能直接访问 PEAK 版权声明与本协议
  （本目录即为该用途，随安装包一起分发）；
- **5.1**：免费提供，不含维护与保证。

AITestLab 的 PeakCAN 插件只用于 PEAK PCAN 硬件，符合上述使用条件。
如需用于其它厂商硬件或商用收费分发，请先联系 PEAK-System 获取授权。

> 注：本目录只附 **x64** DLL（AITestLab 是 64 位应用）。ARM64 / x86 目标机请从官方包
> 取对应架构的 `PCANBasic.dll`。
