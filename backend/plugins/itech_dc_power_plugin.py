"""ITECH / 艾德克斯 可编程直流电源（IT6800 / IT6860A / IT6500 系列）。

手册依据（docs/dc_power/manuals/）：
* ITECH_IT6800_SCPI_CN.pdf  —— SCPI 命令表：OUTPut[:STATe] <bool>、
  [SOURce:]VOLTage/CURRent <NRf>、MEASure:VOLTage?/CURRent?/POWer?、
  SYSTem:ERRor?、*IDN?（应答首段固定 "ITECH"）。
* ITECH_IT6860A_UserManual_CN.pdf —— 6.1 RS232 接口：8N1，波特率
  4800/9600/19200/38400/57600/115200，COMM=RS232 + CMD=SCPI。
* ITECH_IT6800_UserManual_CN.pdf —— 第四章远端操作，默认 9600，DB9 经
  IT-E131 转 RS232；IT6100 官网产品页确认标准 SCPI 通讯协议。

LAN 为 IT6500 等机型的选配接口，端口未在手册中统一规定，因此默认取
SCPI raw socket 常用的 5025，可在设备接口配置里按实测修改。
"""
from app.services.plugin_service import BaseProtocolPlugin
from app.services.scpi_power_transport import ScpiPowerTransport


class ItechDcPowerPlugin(ScpiPowerTransport, BaseProtocolPlugin):
    plugin_name = "ITECH 艾德克斯可编程直流电源"
    protocol_name = "itech_dc_power"
    version = "1.0.0"

    BRAND = "ITECH"
    IDN_EXPECT = ("ITECH", "IT")
    DEFAULT_BAUDRATE = 9600
    DEFAULT_LAN_PORT = 5025

    COMMAND_MAP = {
        "idn": "*IDN?",
        "reset": "*RST",
        "clear_status": "*CLS",
        "system_error": "SYST:ERR?",
        "set_voltage": "VOLT {value}",
        "get_voltage": "VOLT?",
        "set_current": "CURR {value}",
        "get_current": "CURR?",
        "output_on": "OUTP ON",
        "output_off": "OUTP OFF",
        "get_output": "OUTP?",
        "measure_voltage": "MEAS:VOLT?",
        "measure_current": "MEAS:CURR?",
        "measure_power": "MEAS:POW?",
        "set_ovp": "VOLT:PROT {value}",
        "set_ocp": "CURR:PROT {value}",
        "get_status": "STAT:OPER:COND?",
    }
