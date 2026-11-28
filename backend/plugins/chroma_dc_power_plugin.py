"""Chroma 致茂 62000P 系列可程控直流电源。

手册依据（docs/dc_power/manuals/ + 官网在线手册）：
* Chroma_62000P_Catalogue_CN.pdf（chromaate.com 官网）—— 标准 RS-232/USB，
  选配 GPIB 或以太网；后面板 17 GPIB/Ethernet、18 RS-232、19 RS-485
  （主从串并联用数字信号口）。
* 62000P Operating & Programming Manual 第 5 章 Remote Operation
  （在线全文：easymanua.ls/chroma/62000p-series/manual）—— 命令树
  SOURce:VOLTage <NRf> / SOUR:VOLT?、SOURce:CURRent / SOUR:CURR?、
  CONFigure:OUTPut ON|OFF / CONF:OUTP?、SOUR:VOLT:SLEW、
  SOUR:CURR:SLEW、SOUR:CURR:PROT:HIGH、FETC:VOLT?、FETC:POW?、
  FETC:STAT?、MEAS:VOLT?、PROGram / SYSTem 子系统、*IDN?。

以太网为选配卡且手册未规定统一 socket 端口，默认 5025，可在接口配置修改。
"""
from app.services.plugin_service import BaseProtocolPlugin
from app.services.scpi_power_transport import ScpiPowerTransport


class ChromaDcPowerPlugin(ScpiPowerTransport, BaseProtocolPlugin):
    plugin_name = "Chroma 致茂 62000P 可编程直流电源"
    protocol_name = "chroma_dc_power"
    version = "1.0.0"

    BRAND = "Chroma"
    IDN_EXPECT = ("CHROMA",)
    DEFAULT_BAUDRATE = 9600
    DEFAULT_LAN_PORT = 5025

    COMMAND_MAP = {
        "idn": "*IDN?",
        "reset": "*RST",
        "clear_status": "*CLS",
        "system_error": "SYST:ERR?",
        "set_voltage": "SOUR:VOLT {value}",
        "get_voltage": "SOUR:VOLT?",
        "set_current": "SOUR:CURR {value}",
        "get_current": "SOUR:CURR?",
        "output_on": "CONF:OUTP ON",
        "output_off": "CONF:OUTP OFF",
        "get_output": "CONF:OUTP?",
        "measure_voltage": "MEAS:VOLT?",
        "measure_current": "MEAS:CURR?",
        "measure_power": "FETC:POW?",
        "set_ocp": "SOUR:CURR:PROT:HIGH {value}",
        "set_voltage_slew": "SOUR:VOLT:SLEW {value}",
        "set_current_slew": "SOUR:CURR:SLEW {value}",
        "get_status": "FETC:STAT?",
    }
