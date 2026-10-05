"""
TEMPLATE_NAME: 通信协议插件
TEMPLATE_TYPE: protocol
TEMPLATE_DESCRIPTION: 新增一种自定义通信协议（串口/USB/以太网/总线…），实现连接、发送、接收

{{PLUGIN_NAME}} —— 由 AITestLab 插件编辑器于 {{DATE}} 从「通信协议插件」模板生成。

使用方法：
1. 实现 connect / disconnect / send / receive 四个方法；
2. 在「插件管理」页安装并启用本插件；
3. 创建设备时协议选择「{{PROTOCOL_NAME}}」即可使用。
"""

from app.services.plugin_service import BaseProtocolPlugin


class {{CLASS_NAME}}(BaseProtocolPlugin):
    """{{DESCRIPTION}}"""

    plugin_name = "{{PLUGIN_NAME}}"
    protocol_name = "{{PROTOCOL_NAME}}"
    version = "{{VERSION}}"

    def __init__(self):
        self._connected = False
        self._connection = None

    # ------------------------------------------------------------------ #
    # 必须实现：连接生命周期
    # ------------------------------------------------------------------ #
    async def connect(self, config: dict) -> bool:
        """打开底层传输。config 来自设备连接配置（见 get_config_schema）。"""
        try:
            # 示例：串口连接（按需替换为 socket / usb / 总线 SDK）
            # import serial
            # self._connection = serial.Serial(
            #     port=config.get("port", "/dev/ttyUSB0"),
            #     baudrate=config.get("baudrate", 115200),
            #     timeout=config.get("timeout", 1.0),
            # )
            self._connection = {"config": config}
            self._connected = True
            return True
        except Exception as e:
            self._connected = False
            raise ConnectionError(f"连接 {{PLUGIN_NAME}} 失败: {e}")

    async def disconnect(self) -> bool:
        """关闭底层传输。"""
        # if self._connection:
        #     self._connection.close()
        self._connection = None
        self._connected = False
        return True

    # ------------------------------------------------------------------ #
    # 必须实现：数据收发
    # ------------------------------------------------------------------ #
    async def send(self, data) -> str:
        """下发一条命令并返回设备应答字符串。

        data 可能是：
          * 原始协议字符串，如 "CAN1,SEND,0x850102" —— 直接转发；
          * 字典 {"command": "...", "parameters": [...]} —— 由本方法格式化。
        """
        if not self._connected:
            raise ConnectionError("未连接设备")

        if isinstance(data, dict):
            command = str(data.get("command", ""))
            params = data.get("parameters") or []
            payload = ",".join([command, *[str(p) for p in params]]).rstrip(",")
        else:
            payload = str(data)

        # TODO: 替换为真实收发
        # self._connection.write(payload.encode())
        # return self._connection.readline().decode().strip()
        return f"OK:{payload}"

    async def receive(self) -> str:
        """读取设备主动上报的数据（无异步上报时可返回空串）。"""
        if not self._connected:
            raise ConnectionError("未连接设备")
        return ""

    # ------------------------------------------------------------------ #
    # 可选：设备模板 / 配置 Schema / 命令表
    # ------------------------------------------------------------------ #
    def get_config_schema(self) -> dict:
        """设备连接参数的表单定义（JSON Schema 子集），用于前端自动生成表单。"""
        return {
            "type": "object",
            "properties": {
                "port": {"type": "string", "title": "端口", "default": "/dev/ttyUSB0"},
                "baudrate": {
                    "type": "integer", "title": "波特率", "default": 115200,
                    "enum": [9600, 19200, 38400, 57600, 115200],
                },
                "timeout": {"type": "number", "title": "超时(秒)", "default": 1.0},
            },
            "required": ["port"],
        }

    def get_device_template(self) -> dict:
        """一键创建设备时使用的模板（字段对应 DeviceCreate）。"""
        return {
            "name": "{{PLUGIN_NAME}}",
            "device_type": "generic",
            "protocol": "{{PROTOCOL_NAME}}",
            "connection_type": "custom",
            "config": {"port": "/dev/ttyUSB0", "baudrate": 115200, "timeout": 1.0},
        }

    def get_commands(self) -> list:
        """命令清单，供调试终端自动补全与 AI 生成用例时参考。"""
        return [
            {
                "name": "示例命令",
                "syntax": "{{PROTOCOL_NAME}},SEND,<hex>",
                "description": "发送一帧数据并等待应答",
                "parameters": [{"name": "payload", "type": "hex"}],
            },
        ]

    def get_status(self) -> dict:
        return {
            "name": self.plugin_name,
            "protocol": self.protocol_name,
            "version": self.version,
            "connected": self._connected,
        }
