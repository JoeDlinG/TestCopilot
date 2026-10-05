"""
TEMPLATE_NAME: 数据解析插件
TEMPLATE_TYPE: data_parser
TEMPLATE_DESCRIPTION: 自定义报文解析规则，把设备原始应答切成有业务含义的字段

{{PLUGIN_NAME}} —— 由 AITestLab 插件编辑器于 {{DATE}} 从「数据解析插件」模板生成。

典型用途：
  * 厂家私有二进制帧（含帧头 / 长度 / 校验 / 多字段）；
  * 一条应答里同时包含多个测量量，需要按位/按字节切分；
  * 需要把原始值做标定换算（如 ADC 码 → 电压）。

解析结果可直接被测试步骤的「结果解析」与判定规则使用。
"""

from app.services.plugin_service import BaseProtocolPlugin


class {{CLASS_NAME}}(BaseProtocolPlugin):
    """{{DESCRIPTION}}"""

    plugin_name = "{{PLUGIN_NAME}}"
    protocol_name = "{{PROTOCOL_NAME}}"
    version = "{{VERSION}}"

    #: 解析字段定义：name / data_type / start / length / unit / 判定条件
    PARSE_SPECS = [
        {
            "name": "示例字段",
            "data_type": "dec",      # hex / bin / bool / dec / string
            "start": 0,              # 起始偏移
            "length": 2,             # 长度
            "unit": "byte",          # byte / bit
            "hex_field": "all",      # 取第几个 0x 字段：all / first / last / 序号
            "conditions": {"min": 0, "max": 100},
        },
    ]

    def __init__(self):
        self._connected = False
        self._buffer = b""

    # ------------------------------------------------------------------ #
    # 连接生命周期（解析插件仍需实现协议接口才能作为设备后端）
    # ------------------------------------------------------------------ #
    async def connect(self, config: dict) -> bool:
        self._connected = True
        return True

    async def disconnect(self) -> bool:
        self._connected = False
        return True

    async def send(self, data) -> str:
        raw = data.get("command") if isinstance(data, dict) else data
        # TODO: 真实收发后调用 self.parse(str(resp)) 得到字段字典
        return str(raw or "")

    async def receive(self) -> str:
        return ""

    # ------------------------------------------------------------------ #
    # 解析逻辑
    # ------------------------------------------------------------------ #
    @staticmethod
    def _to_bytes(raw) -> bytes:
        """把设备应答（hex 文本 / bytes / str）统一转成字节。"""
        if isinstance(raw, (bytes, bytearray)):
            return bytes(raw)
        import re as _re
        s = str(raw or "").strip()
        groups = _re.findall(r"(?i)\b0x([0-9a-f]+)\b", s)
        if groups:
            joined = "".join(groups)
            if len(joined) % 2 == 0:
                return bytes.fromhex(joined)
        compact = _re.sub(r"[,\s_]+", "", s).lower().replace("0x", "")
        if compact and _re.fullmatch(r"[0-9a-f]+", compact) and len(compact) % 2 == 0:
            return bytes.fromhex(compact)
        return s.encode("utf-8", errors="replace")

    def parse(self, raw) -> dict:
        """按 PARSE_SPECS 把一条应答解析成 {字段名: 值}。"""
        data = self._to_bytes(raw)
        out: dict = {"_raw": str(raw), "_len": len(data)}
        for spec in self.PARSE_SPECS:
            name = spec.get("name", "?")
            start = int(spec.get("start", 0))
            length = int(spec.get("length", 1))
            dtype = spec.get("data_type", "string")
            try:
                if spec.get("unit") == "bit":
                    bits = "".join(f"{b:08b}" for b in data)
                    value: object = int(bits[start:start + length], 2)
                else:
                    chunk = data[start:start + length]
                    if dtype == "hex":
                        value = "0x" + chunk.hex().upper()
                    elif dtype == "bin":
                        value = "".join(f"{b:08b}" for b in chunk)
                    elif dtype == "bool":
                        value = any(chunk)
                    elif dtype == "dec":
                        value = int.from_bytes(chunk, "big")
                    else:
                        value = chunk.decode("utf-8", errors="replace").rstrip("\x00")
            except Exception as e:  # 越界等异常不应中断整条用例
                out[name] = None
                out[f"{name}_error"] = str(e)
                continue
            out[name] = value
        return out

    # ------------------------------------------------------------------ #
    # 与平台对接
    # ------------------------------------------------------------------ #
    def get_commands(self) -> list:
        return [{"name": "解析一条应答", "syntax": "parse(<raw>)",
                 "description": "返回字段字典", "parameters": [{"name": "raw", "type": "string"}]}]

    def get_device_template(self) -> dict:
        return {
            "name": "{{PLUGIN_NAME}}",
            "device_type": "generic",
            "protocol": "{{PROTOCOL_NAME}}",
            "connection_type": "custom",
            "config": {},
        }
