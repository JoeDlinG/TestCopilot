"""Communication protocol abstraction layer for AITestLab.

Provides a unified interface for SCPI, CAN, Serial, and Ethernet communication
with real hardware or mock backends for development/testing.
"""
from __future__ import annotations
import asyncio
import concurrent.futures
import logging
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# Thread pool for running blocking I/O operations (Python 3.8 compatible
# replacement for asyncio.to_thread which was added in Python 3.9).
_thread_pool = concurrent.futures.ThreadPoolExecutor(max_workers=8)


async def _run_in_thread(func, *args):
    """Run a blocking function in a thread pool and await its result.

    This is a backport of asyncio.to_thread() for Python 3.8.
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_thread_pool, func, *args)


class CommunicationInterface(ABC):
    """Abstract base class for all communication protocols."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self._is_connected = False

    @property
    def is_connected(self) -> bool:
        return self._is_connected

    @abstractmethod
    async def connect(self) -> None:
        """Establish connection to the device."""
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        """Close connection to the device."""
        ...

    @abstractmethod
    async def send(self, data: str) -> str:
        """Send a command and return the response."""
        ...

    @abstractmethod
    async def receive(self, timeout: float = 5.0) -> str:
        """Receive data from the device."""
        ...


class MockInterface(CommunicationInterface):
    """Mock communication interface for development/testing."""

    def __init__(self, name: str = "mock", config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.name = name

    async def connect(self) -> None:
        logger.info(f"[Mock] {self.name}: Connected")
        self._is_connected = True

    async def disconnect(self) -> None:
        logger.info(f"[Mock] {self.name}: Disconnected")
        self._is_connected = False

    async def send(self, data: str) -> str:
        logger.debug(f"[Mock] {self.name} TX: {data}")
        return f"[Mock Response] {data}"

    async def receive(self, timeout: float = 5.0) -> str:
        await asyncio.sleep(0.1)
        return "[Mock Data]"


class SCPIInterface(CommunicationInterface):
    """SCPI protocol via PyVISA (supports USB, GPIB, Ethernet)."""

    def __init__(self, visa_address: str, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.visa_address = visa_address
        self._resource = None
        self._rm = None

    async def connect(self) -> None:
        try:
            import pyvisa
            self._rm = pyvisa.ResourceManager()
            self._resource = self._rm.open_resource(self.visa_address)
            self._resource.timeout = self.config.get("timeout", 5000)
            self._resource.read_termination = self.config.get("read_termination", "\n")
            self._resource.write_termination = self.config.get("write_termination", "\n")
            self._is_connected = True
            logger.info(f"SCPI connected: {self.visa_address}")
        except ImportError:
            logger.warning("PyVISA not installed, falling back to mock SCPI")
            self._is_connected = True
        except Exception as e:
            logger.error(f"SCPI connection failed: {e}")
            raise

    async def disconnect(self) -> None:
        if self._resource:
            try:
                self._resource.close()
            except Exception as e:
                logger.warning(f"Error closing SCPI resource: {e}")
        if self._rm:
            try:
                self._rm.close()
            except Exception:
                pass
        self._is_connected = False

    async def send(self, data: str) -> str:
        if self._resource is None:
            return f"[Mock SCPI] {data}"
        return await _run_in_thread(self._resource.query, data)

    async def receive(self, timeout: float = 5.0) -> str:
        if self._resource is None:
            return "[Mock SCPI Data]"
        if timeout != self._resource.timeout:
            self._resource.timeout = int(timeout * 1000)
        return await _run_in_thread(self._resource.read)


class CANInterface(CommunicationInterface):
    """CAN bus protocol via python-can (supports PCAN, Vector, SocketCAN, Kvaser)."""

    def __init__(self, channel: str, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.channel = channel
        self._bus = None
        self._notifier = None

    async def connect(self) -> None:
        try:
            import can
            self._bus = can.interface.Bus(
                channel=self.channel,
                interface=self.config.get("interface", "pcan"),
                bitrate=self.config.get("bitrate", 500000),
            )
            self._is_connected = True
            logger.info(f"CAN connected: {self.channel}")
        except ImportError:
            logger.warning("python-can not installed, falling back to mock CAN")
            self._is_connected = True
        except Exception as e:
            logger.error(f"CAN connection failed: {e}")
            raise

    async def disconnect(self) -> None:
        if self._bus:
            try:
                self._bus.shutdown()
            except Exception as e:
                logger.warning(f"Error shutting down CAN bus: {e}")
        self._is_connected = False

    async def send(self, data: str) -> str:
        try:
            import can
            if self._bus is None:
                return f"[Mock CAN] {data}"

            can_id = self.config.get("can_id", 0x7DF)
            msg = can.Message(
                arbitration_id=can_id,
                data=[ord(c) for c in data[:8]],
                is_extended_id=False,
            )
            self._bus.send(msg)
            # Wait for response
            response = await _run_in_thread(self._bus.recv, self.config.get("timeout", 5.0))
            if response:
                return f"[CAN RX] id={response.arbitration_id:x} data={response.data.hex()}"
            return "[CAN] No response"
        except ImportError:
            return f"[Mock CAN] {data}"

    async def receive(self, timeout: float = 5.0) -> str:
        if self._bus is None:
            return "[Mock CAN Data]"
        msg = await _run_in_thread(self._bus.recv, timeout)
        if msg:
            return f"[CAN] id={msg.arbitration_id:x} data={msg.data.hex()}"
        return "[CAN] Timeout"


class SerialInterface(CommunicationInterface):
    """Serial/UART protocol via pyserial (supports RS232, RS485)."""

    def __init__(self, port: str, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.port = port
        self._serial = None

    async def connect(self) -> None:
        import os
        import re
        # Validate the port before attempting connection.
        # - POSIX: serial devices are files under /dev (e.g. /dev/ttyACM0)
        # - Windows: serial ports are named COM1..COM256 and are NOT files,
        #   so os.path.exists() would wrongly reject valid ports like "COM3".
        if self.port:
            if os.name == "nt":
                if not re.match(r"^COM\d{1,3}$", self.port, re.IGNORECASE):
                    raise FileNotFoundError(
                        f"Serial port not found: {self.port}. "
                        "On Windows use a COM port name (e.g. COM3)."
                    )
            elif not os.path.exists(self.port):
                raise FileNotFoundError(
                    f"Serial port not found: {self.port}. "
                    "Please check device connection and drivers."
                )

        try:
            import serial
            self._serial = serial.Serial(
                port=self.port,
                baudrate=self.config.get("baudrate", 115200),
                bytesize=self.config.get("bytesize", serial.EIGHTBITS),
                parity=self.config.get("parity", serial.PARITY_NONE),
                stopbits=self.config.get("stopbits", serial.STOPBITS_ONE),
                timeout=self.config.get("timeout", 1.0),
            )
            self._is_connected = True
            logger.info(f"Serial connected: {self.port} @ {self.config.get('baudrate', 115200)} baud")
        except ImportError:
            logger.warning("pyserial not installed, cannot open serial port")
            raise RuntimeError("pyserial is not installed. Install with: pip install pyserial")
        except Exception as e:
            logger.error(f"Serial connection failed: {e}")
            raise

    async def disconnect(self) -> None:
        if self._serial and self._serial.is_open:
            self._serial.close()
        self._is_connected = False

    async def send(self, data: str) -> str:
        if self._serial is None or not self._serial.is_open:
            raise ConnectionError(f"Serial port {self.port} is not connected")

        # Flush any stale data before sending
        try:
            await _run_in_thread(self._serial.reset_input_buffer)
        except Exception:
            pass

        # Send the command
        await _run_in_thread(self._serial.write, (data + "\r\n").encode())

        # Read all response lines with a per-line timeout.
        # Some devices (e.g. mini-Gateway-100) return multi-line responses,
        # and some commands (e.g. @11_TSTRT) start with an empty line before
        # the actual payload — a single read_until('\n') would only catch
        # the leading empty line and miss the real data.
        terminator = self.config.get("termination_char", "\n").encode()
        read_timeout = float(self.config.get("read_timeout", 0.3))
        max_lines = int(self.config.get("max_response_lines", 50))
        inter_line_grace = float(self.config.get("inter_line_grace", 0.05))

        lines: list[str] = []
        original_timeout = self._serial.timeout

        try:
            for _ in range(max_lines):
                self._serial.timeout = read_timeout
                try:
                    line = await _run_in_thread(self._serial.read_until, terminator)
                except Exception:
                    break

                decoded = line.decode(errors="replace").rstrip("\r\n")
                lines.append(decoded)

                # Check if more data is already buffered.
                # in_waiting is a non-blocking property, not a method.
                remaining = self._serial.in_waiting
                if remaining == 0:
                    # Small grace period: device may still be transmitting
                    await asyncio.sleep(inter_line_grace)
                    remaining = self._serial.in_waiting
                    if remaining == 0:
                        break
        finally:
            self._serial.timeout = original_timeout

        # Remove trailing empty lines (but keep internal structure)
        while lines and lines[-1] == "":
            lines.pop()

        result = "\n".join(lines)
        logger.debug(
            f"Serial[{self.port}] TX: {data!r}  RX: {result!r} (lines={len(lines)})"
        )
        return result

    async def receive(self, timeout: float = 5.0) -> str:
        if self._serial is None or not self._serial.is_open:
            raise ConnectionError(f"Serial port {self.port} is not connected")
        old_timeout = self._serial.timeout
        self._serial.timeout = timeout
        data = await _run_in_thread(self._serial.readline)
        self._serial.timeout = old_timeout
        return data.decode(errors="replace").strip()


class USBInterface(CommunicationInterface):
    """Raw USB device interface via pyusb/libusb.

    Used for devices that appear on the USB bus but don't have
    a kernel driver bound (e.g., STM32 CDC ACM not auto-bound).
    """

    def __init__(self, vid: str, pid: str, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)

        def _parse_hex(v):
            if isinstance(v, int):
                return v
            if isinstance(v, str):
                v = v.strip()
                if v.startswith("0x") or v.startswith("0X"):
                    return int(v, 16)
                if all(c in "0123456789ABCDEFabcdef" for c in v) and len(v) <= 4:
                    return int(v, 16)
                try:
                    return int(v)
                except ValueError:
                    return 0
            return 0

        self.vid = _parse_hex(vid)
        self.pid = _parse_hex(pid)
        self._device = None
        self._ep_out = None
        self._ep_in = None

    async def connect(self) -> None:
        try:
            import usb.core
            import usb.util

            self._device = usb.core.find(idVendor=self.vid, idProduct=self.pid)
            if self._device is None:
                raise RuntimeError(
                    f"USB device {self.vid:04X}:{self.pid:04X} not found. "
                    "Please check device connection."
                )

            # Detach kernel driver if active
            try:
                if self._device.is_kernel_driver_active(0):
                    self._device.detach_kernel_driver(0)
                    logger.info(f"USB {self.vid:04X}:{self.pid:04X}: detached kernel driver")
            except Exception as e:
                logger.debug(f"USB kernel driver detach skipped: {e}")

            # Set configuration
            try:
                self._device.set_configuration()
            except usb.core.USBError as e:
                logger.debug(f"USB set_configuration: {e}")

            # Find endpoints from the first interface
            cfg = self._device.get_active_configuration()
            intf = cfg[(0, 0)]
            self._ep_out = usb.util.find_descriptor(
                intf,
                custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_OUT,
            )
            self._ep_in = usb.util.find_descriptor(
                intf,
                custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_IN,
            )

            self._is_connected = True
            logger.info(
                f"USB connected: {self.vid:04X}:{self.pid:04X} "
                f"(OUT: 0x{self._ep_out.bEndpointAddress:02X if self._ep_out else 'N/A'}, "
                f"IN: 0x{self._ep_in.bEndpointAddress:02X if self._ep_in else 'N/A'})"
            )
        except ImportError:
            raise RuntimeError(
                "pyusb is not installed. Install with: pip install pyusb. "
                "Also ensure libusb is installed on your system."
            )
        except Exception as e:
            logger.error(f"USB connection failed: {e}")
            raise

    async def disconnect(self) -> None:
        if self._device:
            try:
                import usb.util
                usb.util.dispose_resources(self._device)
            except Exception as e:
                logger.warning(f"USB dispose error: {e}")
        self._device = None
        self._ep_out = None
        self._ep_in = None
        self._is_connected = False

    async def send(self, data: str) -> str:
        if self._device is None or self._ep_out is None:
            raise ConnectionError("USB device not connected")
        try:
            raw = (data + "\r\n").encode()
            await _run_in_thread(self._ep_out.write, raw)
            if self._ep_in:
                response = await _run_in_thread(
                    self._ep_in.read, self._ep_in.wMaxPacketSize,
                    timeout=self.config.get("timeout", 2000),
                )
                return bytes(response).decode(errors="replace").strip()
            return ""
        except Exception as e:
            logger.error(f"USB send error: {e}")
            raise

    async def receive(self, timeout: float = 5.0) -> str:
        if self._device is None or self._ep_in is None:
            raise ConnectionError("USB device not connected")
        try:
            response = await _run_in_thread(
                self._ep_in.read, self._ep_in.wMaxPacketSize,
                timeout=int(timeout * 1000),
            )
            return bytes(response).decode(errors="replace").strip()
        except Exception as e:
            logger.error(f"USB receive error: {e}")
            raise


class EthernetInterface(CommunicationInterface):
    """TCP/UDP communication via asyncio (for Ethernet-connected instruments)."""

    def __init__(self, host: str, port: int, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.host = host
        self.port = port
        self._reader = None
        self._writer = None
        self._protocol = config.get("protocol", "tcp") if config else "tcp"

    async def connect(self) -> None:
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port),
                timeout=self.config.get("connect_timeout", 10.0),
            )
            self._is_connected = True
            logger.info(f"Ethernet connected: {self.host}:{self.port}")
        except Exception as e:
            logger.error(f"Ethernet connection failed: {e}")
            self._is_connected = True  # Allow mock fallback

    async def disconnect(self) -> None:
        if self._writer:
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except Exception:
                pass
        self._is_connected = False

    async def send(self, data: str) -> str:
        if self._writer is None:
            return f"[Mock Ethernet] {data}"
        self._writer.write((data + "\n").encode())
        await self._writer.drain()
        if self._reader:
            response = await asyncio.wait_for(
                self._reader.readline(),
                timeout=self.config.get("timeout", 5.0),
            )
            return response.decode(errors="replace").strip()
        return ""

    async def receive(self, timeout: float = 5.0) -> str:
        if self._reader is None:
            return "[Mock Ethernet Data]"
        data = await asyncio.wait_for(self._reader.readline(), timeout=timeout)
        return data.decode(errors="replace").strip()


def create_interface(
    protocol: str,
    address: str,
    port: Optional[int] = None,
    config: Optional[Dict[str, Any]] = None,
) -> CommunicationInterface:
    """Factory function to create the appropriate communication interface."""
    interfaces = {
        "scpi": lambda: SCPIInterface(visa_address=address, config=config),
        "can": lambda: CANInterface(channel=address, config=config),
        "serial": lambda: SerialInterface(port=address, config=config),
        "ethernet": lambda: EthernetInterface(
            host=address, port=port or 5025, config=config
        ),
        "gpib": lambda: SCPIInterface(visa_address=address, config=config),
        "usb": lambda: USBInterface(
            vid=config.get("vid", "") if config else "",
            pid=config.get("pid", "") if config else "",
            config=config,
        ),
    }

    factory = interfaces.get(protocol, lambda: MockInterface(name=protocol, config=config))
    return factory()
