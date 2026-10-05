"""
Example custom protocol plugin for AITestLab.

This demonstrates how to create a custom communication protocol plugin.
To use:
1. Place this file in the plugins/ directory
2. Install via the plugin management API
"""

from app.services.plugin_service import BaseProtocolPlugin

import os


def _default_port() -> str:
    """Return a sensible default serial device path for the current OS."""
    return "COM3" if os.name == "nt" else "/dev/ttyUSB0"


class ModbusProtocolPlugin(BaseProtocolPlugin):
    """Example Modbus RTU protocol plugin."""

    plugin_name = "Modbus RTU"
    protocol_name = "modbus_rtu"
    version = "1.0.0"

    def __init__(self):
        self._connected = False
        self._connection = None

    async def connect(self, config: dict) -> bool:
        """
        Connect to a Modbus RTU device.
        config should contain: port, baudrate, parity, stopbits, slave_id
        """
        try:
            # In production, use pymodbus or minimalmodbus
            port = config.get("port", _default_port())
            baudrate = config.get("baudrate", 9600)
            self._connected = True
            self._connection = {
                "port": port,
                "baudrate": baudrate,
                "config": config,
            }
            return True
        except Exception as e:
            self._connected = False
            raise ConnectionError(f"Failed to connect Modbus device: {e}")

    async def disconnect(self) -> bool:
        self._connected = False
        self._connection = None
        return True

    async def send(self, data: any) -> any:
        """
        Send Modbus command and get response.
        data should contain: function_code, register_address, count
        """
        if not self._connected:
            raise ConnectionError("Not connected")

        # Mock response for demonstration
        return {
            "function_code": data.get("function_code", 3),
            "data": [0, 0],
            "status": "ok",
        }

    async def receive(self) -> any:
        """Receive data from Modbus device."""
        if not self._connected:
            raise ConnectionError("Not connected")
        return {"status": "ok", "data": []}

    def get_config_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "port": {
                    "type": "string",
                    "title": "Serial Port",
                    "default": _default_port(),
                },
                "baudrate": {
                    "type": "integer",
                    "title": "Baudrate",
                    "default": 9600,
                    "enum": [9600, 19200, 38400, 57600, 115200],
                },
                "parity": {
                    "type": "string",
                    "title": "Parity",
                    "default": "none",
                    "enum": ["none", "even", "odd"],
                },
                "slave_id": {
                    "type": "integer",
                    "title": "Slave ID",
                    "default": 1,
                    "minimum": 1,
                    "maximum": 247,
                },
            },
            "required": ["port", "baudrate", "slave_id"],
        }

    def get_status(self) -> dict:
        return {
            "name": self.plugin_name,
            "protocol": self.protocol_name,
            "version": self.version,
            "connected": self._connected,
        }
