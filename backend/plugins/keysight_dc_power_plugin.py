"""Keysight 是德科技 可编程直流电源（E36300 / N5700 系列）。

手册依据（docs/dc_power/manuals/ + Keysight 官网支持页）：
* Keysight_E36300_UsersGuide_EN.pdf（keysight.com 官方 PDF，221 页）——
  「Using sockets」章节明确「Keysight instruments have standardized on using
  port 5025 for SCPI socket services」；远程接口配置 / LAN / SCPI 可编程。
* Keysight Series N5700 User's Guide（官网支持页）—— 第 5 章 Language
  Reference：Common / Measure / Output / Source / Status / System 命令汇总，
  即 [SOURce:]VOLTage、CURRent、OUTPut[:STATe]、MEASure、SYSTem:ERRor?。

E36300 为三输出机型，设定电压/电流前需先 `INST:SEL OUT1|OUT2|OUT3`
（select_channel）；N5700 单输出可忽略。E36300 无原生 RS-232，串口路径供
USB/RS-232 适配器或 N5700 等带串口机型使用，LAN 为推荐接口。
"""
from app.services.plugin_service import BaseProtocolPlugin
from app.services.scpi_power_transport import ScpiPowerTransport


class KeysightDcPowerPlugin(ScpiPowerTransport, BaseProtocolPlugin):
    plugin_name = "Keysight 是德科技可编程直流电源"
    protocol_name = "keysight_dc_power"
    version = "1.0.0"

    BRAND = "Keysight"
    IDN_EXPECT = ("KEYSIGHT", "AGILENT", "HP")
    DEFAULT_BAUDRATE = 9600
    DEFAULT_LAN_PORT = 5025
    SUPPORTS_CHANNELS = True

    COMMAND_MAP = {
        "idn": "*IDN?",
        "reset": "*RST",
        "clear_status": "*CLS",
        "system_error": "SYST:ERR?",
        "select_channel": "INST:SEL {channel}",
        "set_voltage": "VOLT {value}",
        "get_voltage": "VOLT?",
        "set_current": "CURR {value}",
        "get_current": "CURR?",
        "output_on": "OUTP ON",
        "output_off": "OUTP OFF",
        "get_output": "OUTP?",
        "measure_voltage": "MEAS:VOLT?",
        "measure_current": "MEAS:CURR?",
        "set_ovp": "VOLT:PROT {value}",
        "set_ocp": "CURR:PROT {value}",
        "get_status": "STAT:QUES:COND?",
    }
