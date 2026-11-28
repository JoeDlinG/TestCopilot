"""TDK-Lambda GENESYS+ 可编程直流电源（G+/GH/GSP/GSPL 系列）。

手册依据（docs/dc_power/manuals/，均为 TDK 官网 PDF）：
* TDK_GenesysPlus_UserManual.pdf —— 首页即声明内置 LAN / USB / RS-232 /
  RS-485；1.9.4 明确串口默认 115200、SCPI 语言；第 4 章为串口/LAN 接口。
* TDK_Genesys_LAN_Interface_Manual.pdf —— 2.2 LAN 规格「TCP Sockets Send
  SCPI commands to port 8003」（UDP 8005）；11.2/11.3 命令示例
  VOLT n.nn / VOLT?、CURR、OUTP:STAT 1|ON / OUTP:STAT?、MEAS:VOLT?、
  MEAS:CURR?、VOLT:PROT:LEV、SOUR:MOD?、*IDN?；第 12 章 RS-485 多机。

RS-485 多机（multi-drop）由带 LAN 的主电源经 J3 链路转发，从站地址在
前面板设置；本插件按点对点 SCPI 方式工作，多机时由主电源负责寻址。
"""
from app.services.plugin_service import BaseProtocolPlugin
from app.services.scpi_power_transport import ScpiPowerTransport


class TdkLambdaDcPowerPlugin(ScpiPowerTransport, BaseProtocolPlugin):
    plugin_name = "TDK-Lambda GENESYS+ 可编程直流电源"
    protocol_name = "tdk_lambda_dc_power"
    version = "1.0.0"

    BRAND = "TDK-Lambda"
    IDN_EXPECT = ("TDK-LAMBDA", "TDK", "LAMBDA")
    DEFAULT_BAUDRATE = 115200
    DEFAULT_LAN_PORT = 8003

    COMMAND_MAP = {
        "idn": "*IDN?",
        "reset": "*RST",
        "clear_status": "*CLS",
        "system_error": "SYST:ERR?",
        "set_voltage": "VOLT {value}",
        "get_voltage": "VOLT?",
        "set_current": "CURR {value}",
        "get_current": "CURR?",
        "output_on": "OUTP:STAT ON",
        "output_off": "OUTP:STAT OFF",
        "get_output": "OUTP:STAT?",
        "measure_voltage": "MEAS:VOLT?",
        "measure_current": "MEAS:CURR?",
        "set_ovp": "VOLT:PROT:LEV {value}",
        "get_status": "SOUR:MOD?",
    }
