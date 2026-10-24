"""Device interface registry — one source of truth for connection settings.

The UI ("edit device interface") renders itself from :data:`INTERFACE_SPECS`,
so adding a bus only means appending a descriptor here — no frontend change.

Each field descriptor declares where the value lives:

``store="column"``
    A real column on ``devices`` (``serial_port``, ``ip_address``, ``port``,
    ``visa_address``, ``can_channel``). Used directly by the address resolvers
    and by the execution-manager resource keys.

``store="config"``
    Everything else (baud rate, parity, BDF address, slot, ...). Persisted in
    ``devices.config`` as JSON and handed to the communication interface on
    connect.
"""
from typing import Any, Dict, List

# Columns of ``devices`` an interface field may map onto.
ADDRESS_COLUMNS = (
    "serial_port",
    "ip_address",
    "port",
    "visa_address",
    "can_channel",
)

_BAUD_RATES = [9600, 19200, 38400, 57600, 115200, 230400, 460800, 921600]


def _field(
    key: str,
    label: str,
    field_type: str = "string",
    store: str = "config",
    required: bool = False,
    default: Any = None,
    options: Any = None,
    placeholder: str = "",
    help_text: str = "",
) -> Dict[str, Any]:
    spec: Dict[str, Any] = {
        "key": key,
        "label": label,
        "type": field_type,
        "store": store,
        "required": required,
        "default": default,
    }
    if options is not None:
        spec["options"] = options
    if placeholder:
        spec["placeholder"] = placeholder
    if help_text:
        spec["help"] = help_text
    return spec


INTERFACE_SPECS: List[Dict[str, Any]] = [
    {
        "type": "serial",
        "label": "串口 (RS-232 / RS-485)",
        "protocol": "serial",
        "fields": [
            _field(
                "serial_port", "串口号", "string", store="column", required=True,
                placeholder="/dev/ttyUSB0 或 COM3",
                help_text="插上设备后在「设备管理 → 扫描设备」里可以看到可用串口",
            ),
            _field(
                "baudrate", "波特率", "integer", default=115200, options=_BAUD_RATES,
            ),
            _field("data_bits", "数据位", "integer", default=8, options=[5, 6, 7, 8]),
            _field("parity", "校验位", "string", default="N",
                   options=["N", "E", "O", "M", "S"],
                   help_text="N=无校验，E=偶校验，O=奇校验，M=标记，S=空格"),
            _field("stop_bits", "停止位", "number", default=1, options=[1, 1.5, 2]),
            _field("flow_control", "流控", "string", default="none",
                   options=["none", "hardware", "software"]),
            _field("timeout", "读取超时 (秒)", "number", default=2.0),
        ],
    },
    {
        "type": "usb",
        "label": "USB",
        "protocol": "usb",
        "fields": [
            _field(
                "serial_port", "设备路径 / 虚拟串口", "string", store="column",
                placeholder="/dev/ttyACM0 或 COM3",
                help_text="USB-CDC 设备会枚举成串口；原始 USB 设备留空并填下方的 VID/PID",
            ),
            _field("vid", "VID (厂商 ID)", "string", placeholder="0483",
                   help_text="十六进制，用于按厂商/产品识别 USB 设备"),
            _field("pid", "PID (产品 ID)", "string", placeholder="5740"),
            _field("serial_number", "序列号 (可选)", "string", help_text="同型号多台设备时用于区分"),
            _field("timeout", "读取超时 (秒)", "number", default=2.0),
        ],
    },
    {
        "type": "ethernet",
        "label": "以太网",
        "protocol": "ethernet",
        "fields": [
            _field(
                "ip_address", "IP 地址", "string", store="column", required=True,
                placeholder="192.168.0.120",
            ),
            _field("port", "端口号", "integer", store="column", default=5025,
                   placeholder="5025"),
            # The key must stay ``protocol``: that is what EthernetInterface
            # reads from the connect config.
            _field("protocol", "传输协议", "string", default="tcp", options=["tcp", "udp"]),
            _field("connect_timeout", "连接超时 (秒)", "number", default=5.0),
            _field("timeout", "读取超时 (秒)", "number", default=5.0),
            _field(
                "simulate", "模拟模式", "boolean", default=False,
                help_text="没有真实设备时开启：连接必定成功，收发返回模拟数据，用于验证流程",
            ),
        ],
    },
    {
        "type": "pcie",
        "label": "PCIe",
        "protocol": "pcie",
        "simulated": True,
        "note": "当前为模拟模式（尚未接入内核驱动），连接会成功但收发为模拟数据。",
        "fields": [
            _field(
                "bdf", "BDF 地址", "string", required=True, placeholder="0000:01:00.0",
                help_text="总线:设备.功能，可通过 lspci 查看",
            ),
            _field("device_index", "设备序号 (可选)", "integer",
                   help_text="同一驱动下多张卡时的索引号"),
            _field("resource", "资源描述符 (可选)", "string", placeholder="/dev/aitest0"),
            _field("timeout", "读取超时 (秒)", "number", default=2.0),
        ],
    },
    {
        "type": "pxi",
        "label": "PXI / PXIe",
        "protocol": "pxi",
        "simulated": True,
        "note": "当前为模拟模式（尚未接入 PXI 机箱控制器），连接会成功但收发为模拟数据。",
        "fields": [
            _field("chassis", "机箱号", "integer", default=0, placeholder="0"),
            _field("slot", "槽位号", "integer", required=True, placeholder="2"),
            _field(
                "visa_address", "VISA 资源串", "string", store="column",
                placeholder="PXI0::2::INSTR",
                help_text="若通过 NI-VISA 访问，可填写完整资源描述符",
            ),
            _field("timeout", "读取超时 (秒)", "number", default=2.0),
        ],
    },
    {
        "type": "can",
        "label": "CAN",
        "protocol": "can",
        "fields": [
            _field(
                "can_channel", "CAN 通道", "string", store="column", required=True,
                placeholder="PCAN_USBBUS1 或 can0",
            ),
            _field("bitrate", "波特率 (bps)", "integer", default=500000,
                   options=[125000, 250000, 500000, 1000000]),
            _field("fd", "CAN FD", "boolean", default=False),
            _field("timeout", "读取超时 (秒)", "number", default=2.0),
        ],
    },
    {
        "type": "gpib",
        "label": "GPIB",
        "protocol": "gpib",
        "fields": [
            _field(
                "visa_address", "VISA 资源串", "string", store="column", required=True,
                placeholder="GPIB0::1::INSTR",
            ),
            _field("gpib_address", "GPIB 地址 (可选)", "integer", placeholder="1"),
            _field("timeout", "读取超时 (秒)", "number", default=2.0),
        ],
    },
]


INTERFACE_TYPES_ORDER = [s["type"] for s in INTERFACE_SPECS]


def get_interface_spec(interface_type: str) -> Dict[str, Any]:
    for spec in INTERFACE_SPECS:
        if spec["type"] == interface_type:
            return spec
    raise KeyError(interface_type)


def default_params(interface_type: str) -> Dict[str, Any]:
    """Return ``{field_key: default}`` for every configured field."""
    spec = get_interface_spec(interface_type)
    return {
        f["key"]: f["default"]
        for f in spec["fields"]
        if f.get("default") is not None
    }


def split_params(interface_type: str, params: Dict[str, Any]):
    """Split submitted params into (column_values, config_values)."""
    spec = get_interface_spec(interface_type)
    columns: Dict[str, Any] = {}
    config: Dict[str, Any] = {}
    for f in spec["fields"]:
        key = f["key"]
        if key not in params:
            continue
        value = params[key]
        if f["store"] == "column":
            columns[key] = value
        else:
            config[key] = value
    return columns, config


def clear_other_columns(interface_type: str) -> Dict[str, str]:
    """Columns belonging to *other* interfaces — set to None when switching."""
    used = {
        f["key"]
        for f in get_interface_spec(interface_type)["fields"]
        if f["store"] == "column"
    }
    return {col: None for col in ADDRESS_COLUMNS if col not in used}


def foreign_config_keys(interface_type: str, keep: set) -> set:
    """Config keys owned by *other* interfaces.

    Switching from serial to Ethernet must not leave ``baudrate`` behind, or the
    next connect would hand serial settings to a TCP socket.
    """
    out = set()
    for spec in INTERFACE_SPECS:
        if spec["type"] == interface_type:
            continue
        out.update(f["key"] for f in spec["fields"] if f["store"] == "config")
    return out - set(keep)
