"""
TEMPLATE_NAME: 设备驱动插件
TEMPLATE_TYPE: device_driver
TEMPLATE_DESCRIPTION: 为某一型号仪器（电源/示波器/万用表…）提供专用指令集与设备模板

{{PLUGIN_NAME}} —— 由 AITestLab 插件编辑器于 {{DATE}} 从「设备驱动插件」模板生成。

与「通信协议插件」的区别：协议插件关注 *怎么传*，设备驱动插件关注 *传什么*。
本模板在协议之上封装了一层仪器指令集（如 SCPI / 厂家私有 ASCII 协议），
并自带设备模板，可在插件管理页一键创建对应设备。
"""

from app.services.plugin_service import BaseProtocolPlugin


class {{CLASS_NAME}}(BaseProtocolPlugin):
    """{{DESCRIPTION}}"""

    plugin_name = "{{PLUGIN_NAME}}"
    protocol_name = "{{PROTOCOL_NAME}}"
    version = "{{VERSION}}"

    def __init__(self):
        self._connected = False
        self._transport = None
        self._last_response = ""

    # ------------------------------------------------------------------ #
    # 连接生命周期
    # ------------------------------------------------------------------ #
    async def connect(self, config: dict) -> bool:
        try:
            # TODO: 按仪器实际接口建立连接（VISA / 串口 / Socket / USB）
            # import pyvisa
            # rm = pyvisa.ResourceManager()
            # self._transport = rm.open_resource(config["address"])
            # self._transport.timeout = int(config.get("timeout", 5)) * 1000
            self._transport = {"config": config}
            self._connected = True
            # 连接后先做一次识别，确认型号匹配
            idn = await self.send("*IDN?")
            self._last_response = idn
            return True
        except Exception as e:
            self._connected = False
            raise ConnectionError(f"连接 {{PLUGIN_NAME}} 失败: {e}")

    async def disconnect(self) -> bool:
        self._transport = None
        self._connected = False
        return True

    # ------------------------------------------------------------------ #
    # 数据收发
    # ------------------------------------------------------------------ #
    async def send(self, data) -> str:
        """下发一条仪器指令并返回应答。

        带 "?" 的指令视为查询，其余视为设置。
        """
        if not self._connected:
            raise ConnectionError("未连接设备")

        command = data.get("command") if isinstance(data, dict) else data
        command = str(command or "")

        # TODO: 替换为真实收发
        # if "?" in command:
        #     return str(self._transport.query(command)).strip()
        # self._transport.write(command)
        # return "OK"
        self._last_response = f"OK:{command}"
        return self._last_response

    async def receive(self) -> str:
        return self._last_response

    # ------------------------------------------------------------------ #
    # 仪器指令集（示例：按需替换为本型号真实指令）
    # ------------------------------------------------------------------ #
    def get_commands(self) -> list:
        return [
            {"name": "识别", "syntax": "*IDN?",
             "description": "返回 厂商,型号,序列号,固件版本", "parameters": []},
            {"name": "复位", "syntax": "*RST",
             "description": "复位到出厂默认状态", "parameters": []},
            {"name": "自检", "syntax": "*TST?",
             "description": "返回 0 表示自检通过", "parameters": []},
            {"name": "读取测量值", "syntax": "MEAS?",
             "description": "读取当前测量值（ASCII 数值）", "parameters": []},
        ]

    def get_config_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "address": {
                    "type": "string", "title": "仪器地址",
                    "default": "TCPIP0::192.168.1.100::INSTR",
                    "description": "VISA 地址，或 IP / 串口号",
                },
                "timeout": {"type": "number", "title": "超时(秒)", "default": 5},
            },
            "required": ["address"],
        }

    def get_device_template(self) -> dict:
        return {
            "name": "{{PLUGIN_NAME}}",
            "device_type": "generic",
            "protocol": "{{PROTOCOL_NAME}}",
            "connection_type": "visa",
            "config": {"address": "TCPIP0::192.168.1.100::INSTR", "timeout": 5},
        }
