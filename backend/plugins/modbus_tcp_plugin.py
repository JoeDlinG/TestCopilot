"""Modbus TCP protocol plugin — PLC / robot / industrial instruments.

This is a *real* Modbus TCP master implementation built on ``pymodbus``
(BSD-3-Clause, pure Python, no native dependencies — safe to bundle into the
closed-source distribution).

It follows the "protocol-first" design: **one driver serves every device that
speaks Modbus TCP** — PLCs, robot controllers (IO / register collaboration),
power meters, temperature controllers and remote IO modules. There is no
per-brand plugin and no point-table: addresses are written as bare numbers
directly in the test step.

Command syntax (a test step ``action``)::

    FC03:40001:2                       # read 2 holding registers from 40001
    FC03:0:2                           # same, 0-based protocol address
    FC06:40010:1                       # write single register
    FC01:00001:8                       # read 8 coils
    FC16:40020:1,2,3                   # write multiple registers
    {"fc": 3, "addr": 100, "count": 2, "dtype": "float32"}

Address references are auto-normalised (``40001 -> 0``, ``30001 -> 0``,
``10001 -> 0``, ``00001 -> 0``) so a device manual can be transcribed verbatim.

Error semantics (important for test authoring):
  * Device answers with a Modbus exception (e.g. illegal address) -> the call
    **returns** ``"ERROR: ..."``. The connection stays healthy so the step can
    be asserted on (negative test cases work).
  * No answer at all / socket dead -> raises ``ConnectionError``. The device
    service marks the device disconnected, which is the correct reaction to a
    broken link.
"""

from __future__ import annotations

import asyncio
import json
import logging
import struct
from typing import Any, Dict, List, Optional, Sequence

from app.services.plugin_service import BaseProtocolPlugin

logger = logging.getLogger(__name__)

try:  # pymodbus is optional at import time so the plugin stays discoverable
    from pymodbus.client import AsyncModbusTcpClient
    from pymodbus.exceptions import ModbusIOException

    _PYMODBUS_IMPORT_ERROR: Optional[str] = None
except Exception as _exc:  # pragma: no cover - environment dependent
    AsyncModbusTcpClient = None  # type: ignore[assignment]
    ModbusIOException = None  # type: ignore[assignment]
    _PYMODBUS_IMPORT_ERROR = str(_exc)


# --------------------------------------------------------------------------- #
# Protocol constants
# --------------------------------------------------------------------------- #

#: Function code -> human readable primitive name.
FC_NAMES = {
    1: "read_coils",
    2: "read_discrete_inputs",
    3: "read_holding_registers",
    4: "read_input_registers",
    5: "write_single_coil",
    6: "write_single_register",
    15: "write_multiple_coils",
    16: "write_multiple_registers",
}

READ_FCS = (1, 2, 3, 4)
WRITE_SINGLE_FCS = (5, 6)
WRITE_MULTI_FCS = (15, 16)

#: Modbus exception codes -> text.
MODBUS_EXCEPTIONS = {
    1: "ILLEGAL_FUNCTION",
    2: "ILLEGAL_DATA_ADDRESS",
    3: "ILLEGAL_DATA_VALUE",
    4: "SLAVE_DEVICE_FAILURE",
    5: "ACKNOWLEDGE",
    6: "SLAVE_DEVICE_BUSY",
    7: "NEGATIVE_ACKNOWLEDGE",
    8: "MEMORY_PARITY_ERROR",
    10: "GATEWAY_PATH_UNAVAILABLE",
    11: "GATEWAY_TARGET_FAILED_TO_RESPOND",
}

#: dtype -> number of 16-bit registers required (``None`` = variable / raw).
DTYPE_REGISTERS: Dict[str, Optional[int]] = {
    "uint16": 1,
    "int16": 1,
    "bool": 1,
    "uint32": 2,
    "int32": 2,
    "float32": 2,
    "uint64": 4,
    "int64": 4,
    "float64": 4,
    "string": None,
    "raw": None,
}

DTYPES = tuple(DTYPE_REGISTERS.keys())


# --------------------------------------------------------------------------- #
# Data type encode / decode
# --------------------------------------------------------------------------- #

def _swap_bytes(word: int) -> int:
    """Swap the two bytes inside one 16-bit register."""
    return ((word & 0xFF) << 8) | ((word >> 8) & 0xFF)


def _words_to_bytes(words: Sequence[int], byte_order: str, word_order: str) -> bytes:
    """Reassemble a byte string from 16-bit registers.

    ``byte_order`` orders the two bytes *inside* a register, ``word_order``
    orders the registers themselves. Modbus wire order is big/big.
    """
    seq = list(words)
    if word_order == "little":
        seq = seq[::-1]
    if byte_order == "little":
        seq = [_swap_bytes(w & 0xFFFF) for w in seq]
    return b"".join(w.to_bytes(2, "big") for w in seq)


def _bytes_to_words(raw: bytes, byte_order: str, word_order: str) -> List[int]:
    """Inverse of :func:`_words_to_bytes`."""
    if len(raw) % 2:
        raw = raw + b"\x00"
    words = [int.from_bytes(raw[i:i + 2], "big") for i in range(0, len(raw), 2)]
    if byte_order == "little":
        words = [_swap_bytes(w) for w in words]
    if word_order == "little":
        words = words[::-1]
    return words


def decode_registers(
    regs: Sequence[int],
    dtype: str = "raw",
    byte_order: str = "big",
    word_order: str = "big",
) -> Any:
    """Decode raw 16-bit registers into a Python value."""
    regs = [int(r) & 0xFFFF for r in regs]
    if not regs:
        return None

    if dtype in ("raw", "", None):
        return regs
    if dtype == "uint16":
        return regs[0]
    if dtype == "int16":
        return regs[0] - 0x10000 if regs[0] & 0x8000 else regs[0]
    if dtype == "bool":
        return bool(regs[0])

    need = DTYPE_REGISTERS.get(dtype)
    if need is None:  # string
        return _words_to_bytes(regs, byte_order, word_order).decode(
            "ascii", errors="replace"
        ).rstrip("\x00")
    if len(regs) < need:
        raise ValueError(
            f"dtype '{dtype}' 需要 {need} 个寄存器，实际只有 {len(regs)} 个"
        )

    raw = _words_to_bytes(regs[:need], byte_order, word_order)
    if dtype == "uint32":
        return int.from_bytes(raw, "big")
    if dtype == "int32":
        return int.from_bytes(raw, "big", signed=True)
    if dtype == "uint64":
        return int.from_bytes(raw, "big")
    if dtype == "int64":
        return int.from_bytes(raw, "big", signed=True)
    if dtype == "float32":
        return struct.unpack(">f", raw)[0]
    if dtype == "float64":
        return struct.unpack(">d", raw)[0]
    raise ValueError(f"不支持的数据类型: {dtype}")


def encode_value(
    value: Any,
    dtype: str = "uint16",
    byte_order: str = "big",
    word_order: str = "big",
) -> List[int]:
    """Encode a Python value into the 16-bit registers to write."""
    if dtype in ("raw", "", None):
        if isinstance(value, (list, tuple)):
            return [int(v) & 0xFFFF for v in value]
        return [int(value) & 0xFFFF]
    if dtype == "bool":
        truthy = value if isinstance(value, bool) else str(value).strip() not in (
            "", "0", "false", "False", "no", "off",
        )
        return [1 if truthy else 0]
    if dtype == "uint16":
        return [int(value) & 0xFFFF]
    if dtype == "int16":
        return [int(value) & 0xFFFF]
    if dtype == "uint32":
        raw = int(value).to_bytes(4, "big")
    elif dtype == "int32":
        raw = int(value).to_bytes(4, "big", signed=True)
    elif dtype == "uint64":
        raw = int(value).to_bytes(8, "big")
    elif dtype == "int64":
        raw = int(value).to_bytes(8, "big", signed=True)
    elif dtype == "float32":
        raw = struct.pack(">f", float(value))
    elif dtype == "float64":
        raw = struct.pack(">d", float(value))
    elif dtype == "string":
        text = str(value)
        raw = text.encode("ascii", errors="replace")
    else:
        raise ValueError(f"不支持的数据类型: {dtype}")
    return _bytes_to_words(raw, byte_order, word_order)


# --------------------------------------------------------------------------- #
# Address + command parsing
# --------------------------------------------------------------------------- #

def normalize_address(fc: int, addr: int) -> int:
    """Convert a ``4xxxx`` / ``3xxxx`` / ``1xxxx`` / ``0xxxx`` reference to a
    0-based protocol address. Plain numbers pass through unchanged."""
    a = int(addr)
    if a >= 40001 and fc in (3, 6, 16):
        return a - 40001
    if a >= 30001 and fc == 4:
        return a - 30001
    if a >= 10001 and fc == 2:
        return a - 10001
    if a >= 1 and fc in (1, 5, 15):
        return a - 1
    return a


def _to_int(text: Any) -> int:
    """Tolerant integer parse.

    ``int("00001", 0)`` raises (leading zeros are invalid with base 0), but
    ``00001`` is exactly how coil addresses are written in device manuals.
    Fall back to base 10 for that case, while still honouring ``0x``/``0b``.
    """
    s = str(text).strip()
    try:
        return int(s, 0)
    except (TypeError, ValueError):
        pass
    try:
        return int(s, 10)
    except (TypeError, ValueError):
        raise ValueError(f"必须是数字: {text!r}") from None


def _parse_bool_token(tok: str) -> bool:
    t = str(tok).strip().lower()
    if t in ("1", "true", "on", "yes"):
        return True
    if t in ("0", "false", "off", "no", ""):
        return False
    raise ValueError(f"不是合法的线圈值: {tok}")


def parse_command(data: Any) -> Dict[str, Any]:
    """Normalise a test-step action into a request spec dict.

    Returns ``{"fc", "addr", "count"|"values", "dtype", "slave_id"}``.
    Raises ``ValueError`` with a actionable message when malformed.
    """
    if isinstance(data, dict):
        spec = dict(data)
    elif isinstance(data, str):
        text = data.strip()
        if not text:
            raise ValueError("空命令")
        if text.startswith("{"):
            try:
                spec = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError(f"JSON 命令解析失败: {exc}") from exc
        else:
            spec = _parse_compact(text)
    else:
        raise ValueError(f"不支持的命令类型: {type(data).__name__}")

    # Accept both the canonical key and the legacy example-plugin keys.
    fc = spec.get("fc", spec.get("function_code"))
    if fc is None:
        raise ValueError("缺少功能码 fc（例如 fc=3 或 FC03）")
    try:
        fc = int(str(fc).upper().removeprefix("FC"))
    except (TypeError, ValueError):
        raise ValueError(f"功能码必须是数字: {fc!r}") from None
    if fc not in FC_NAMES:
        raise ValueError(
            f"不支持的功能码 {fc}，可用: {', '.join(str(f) for f in sorted(FC_NAMES))}"
        )

    addr = spec.get("addr", spec.get("register_address", spec.get("address")))
    if addr is None:
        raise ValueError("缺少地址 addr")
    try:
        addr = _to_int(addr)
    except (TypeError, ValueError):
        raise ValueError(f"地址必须是数字: {addr!r}") from None
    addr = normalize_address(fc, addr)

    out: Dict[str, Any] = {"fc": fc, "addr": addr}
    if "slave_id" in spec:
        out["slave_id"] = int(spec["slave_id"])
    if "dtype" in spec:
        out["dtype"] = str(spec["dtype"]).lower()
    if "byte_order" in spec:
        out["byte_order"] = str(spec["byte_order"]).lower()
    if "word_order" in spec:
        out["word_order"] = str(spec["word_order"]).lower()
    if "response_format" in spec:
        out["response_format"] = str(spec["response_format"]).lower()

    if fc in READ_FCS:
        out["count"] = int(spec.get("count", 1))
    elif fc in WRITE_SINGLE_FCS:
        raw_value = spec.get("value", spec.get("values", 0))
        out["values"] = [raw_value]
    else:  # 15 / 16
        raw_values = spec.get("values", spec.get("value", []))
        if isinstance(raw_values, (list, tuple)):
            out["values"] = list(raw_values)
        else:
            out["values"] = [
                v.strip() for v in str(raw_values).split(",") if v.strip() != ""
            ]
        if not out["values"]:
            raise ValueError(f"FC{fc} 需要至少一个待写入的值")
    return out


def _parse_compact(text: str) -> Dict[str, Any]:
    """Parse ``FC03:40001:2`` / ``read_holding:40001:2`` style commands."""
    parts = [p.strip() for p in text.split(":")]
    if len(parts) < 2:
        raise ValueError(
            f"命令格式应为 FC<功能码>:<地址>:<数量或值>，收到: {text!r}"
        )
    head = parts[0].upper().removeprefix("FC")
    name_to_fc = {v.upper(): k for k, v in FC_NAMES.items()}
    if head.isdigit():
        fc = int(head)
    elif head in name_to_fc:
        fc = name_to_fc[head]
    else:
        raise ValueError(f"无法识别的功能码/原语名: {parts[0]!r}")

    try:
        addr = _to_int(parts[1])
    except ValueError:
        raise ValueError(f"地址必须是数字: {parts[1]!r}") from None

    third = parts[2] if len(parts) > 2 else None
    spec: Dict[str, Any] = {"fc": fc, "addr": addr}
    if fc in READ_FCS:
        spec["count"] = int(third) if third else 1
    elif fc in WRITE_SINGLE_FCS:
        if third is None:
            raise ValueError(f"FC{fc} 需要写入值，格式 FC{fc}:<地址>:<值>")
        spec["value"] = third
    else:
        if third is None:
            raise ValueError(f"FC{fc} 需要写入值列表，格式 FC{fc}:<地址>:<v1,v2,...>")
        spec["values"] = [v.strip() for v in third.split(",") if v.strip() != ""]
    return spec


# --------------------------------------------------------------------------- #
# Plugin
# --------------------------------------------------------------------------- #

class ModbusTcpProtocolPlugin(BaseProtocolPlugin):
    """Modbus TCP master — one driver for PLCs, robots and field instruments."""

    plugin_name = "Modbus TCP"
    protocol_name = "modbus_tcp"
    version = "1.0.0"

    def __init__(self) -> None:
        self._client = None
        self._connected = False
        self._host: Optional[str] = None
        self._port: int = 502
        self._slave_id: int = 1
        self._timeout: float = 3.0
        self._byte_order: str = "big"
        self._word_order: str = "big"
        self._response_format: str = "text"  # "text" | "typed" (P0-1 后切换)
        self._last_error: Optional[str] = None
        self._last_spec: Optional[Dict[str, Any]] = None
        # Optional background polling (robot "wait until in position" pattern)
        self._poll_spec: Optional[Dict[str, Any]] = None
        self._poll_interval_ms: int = 0
        self._last_poll_ts: float = 0.0

    # ---------------------------------------------------------------- config

    def _require_pymodbus(self) -> None:
        if AsyncModbusTcpClient is None:
            raise RuntimeError(
                "缺少依赖 pymodbus。请在运行环境执行 `pip install pymodbus==3.16.1`，"
                "或导入包含该依赖的离线插件包。"
                + (f"（导入错误：{_PYMODBUS_IMPORT_ERROR}）" if _PYMODBUS_IMPORT_ERROR else "")
            )

    # ------------------------------------------------------------- lifecycle

    async def connect(self, config: dict) -> bool:
        self._require_pymodbus()

        host = config.get("host") or config.get("address") or config.get("ip")
        if not host:
            raise ValueError("缺少连接参数 host（设备 IP 地址）")

        self._host = str(host)
        self._port = int(config.get("port", 502))
        self._slave_id = int(config.get("slave_id", config.get("unit_id", 1)))
        self._timeout = float(config.get("timeout", 3.0))
        self._byte_order = str(config.get("byte_order", "big")).lower()
        self._word_order = str(config.get("word_order", "big")).lower()
        self._response_format = str(config.get("response_format", "text")).lower()
        self._poll_interval_ms = int(config.get("poll_interval_ms", 0) or 0)
        poll_raw = config.get("poll")
        self._poll_spec = parse_command(poll_raw) if poll_raw else None

        if self._byte_order not in ("big", "little"):
            raise ValueError("byte_order 必须是 big 或 little")
        if self._word_order not in ("big", "little"):
            raise ValueError("word_order 必须是 big 或 little")

        client = AsyncModbusTcpClient(
            self._host,
            port=self._port,
            timeout=self._timeout,
            retries=0,  # 测试判定必须可复现：超时即失败，不静默重试
        )
        try:
            ok = await client.connect()
        except Exception as exc:
            self._connected = False
            self._last_error = str(exc)
            raise ConnectionError(
                f"无法连接 Modbus TCP 设备 {self._host}:{self._port} — {exc}"
            ) from exc

        if not ok or not getattr(client, "connected", False):
            self._connected = False
            self._last_error = "TCP 连接被拒绝"
            raise ConnectionError(
                f"无法连接 Modbus TCP 设备 {self._host}:{self._port}（连接被拒绝）"
            )

        self._client = client
        self._connected = True
        self._last_error = None
        logger.info("Modbus TCP connected: %s:%s slave=%s", self._host, self._port, self._slave_id)
        return True

    async def disconnect(self) -> bool:
        if self._client is not None:
            try:
                self._client.close()
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("Modbus TCP close failed: %s", exc)
        self._client = None
        self._connected = False
        return True

    # ------------------------------------------------------------------ send

    async def send(self, data: Any) -> Any:
        if not self._connected or self._client is None:
            raise ConnectionError("Modbus TCP 未连接")

        spec = parse_command(data)
        self._last_spec = spec
        fmt = spec.pop("response_format", None) or self._response_format
        result = await self._execute(spec)
        return self._render(result, fmt)

    async def _execute(self, spec: Dict[str, Any]) -> Dict[str, Any]:
        """Run one Modbus primitive and return a typed result dict."""
        fc = spec["fc"]
        addr = spec["addr"]
        slave = int(spec.get("slave_id", self._slave_id))
        byte_order = spec.get("byte_order", self._byte_order)
        word_order = spec.get("word_order", self._word_order)
        dtype = spec.get("dtype", "raw")

        client = self._client
        try:
            if fc == 1:
                resp = await client.read_coils(addr, count=spec["count"], device_id=slave)
            elif fc == 2:
                resp = await client.read_discrete_inputs(addr, count=spec["count"], device_id=slave)
            elif fc == 3:
                resp = await client.read_holding_registers(addr, count=spec["count"], device_id=slave)
            elif fc == 4:
                resp = await client.read_input_registers(addr, count=spec["count"], device_id=slave)
            elif fc == 5:
                values = [bool(_parse_bool_token(v)) for v in spec["values"][:1]]
                resp = await client.write_coil(addr, values[0], device_id=slave)
            elif fc == 6:
                regs = encode_value(spec["values"][0], dtype, byte_order, word_order)
                resp = await client.write_register(addr, regs[0], device_id=slave)
            elif fc == 15:
                values = [bool(_parse_bool_token(v)) for v in spec["values"]]
                resp = await client.write_coils(addr, values, device_id=slave)
            else:  # 16
                if dtype in ("raw", "", None) or len(spec["values"]) > 1:
                    regs = [_to_int(v) & 0xFFFF for v in spec["values"]]
                else:
                    regs = encode_value(spec["values"][0], dtype, byte_order, word_order)
                resp = await client.write_registers(addr, regs, device_id=slave)
        except (ValueError, TypeError):
            # 命令/编码本身有问题（地址越界、dtype 与寄存器数不匹配等）：
            # 属于用例配置错误，不应判定为链路故障，也不应断开设备。
            raise
        except asyncio.TimeoutError as exc:
            self._last_error = f"请求超时（{self._timeout}s）"
            raise ConnectionError(
                f"Modbus FC{fc} @ {addr} 超时未响应（{self._timeout}s）"
            ) from exc
        except (OSError, ConnectionError) as exc:
            self._connected = False
            self._last_error = str(exc)
            raise ConnectionError(f"Modbus 链路中断: {exc}") from exc
        except Exception as exc:
            # pymodbus raises ModbusIOException when nothing came back within
            # ``timeout`` — treat it as a dead link, not a protocol error.
            if ModbusIOException is not None and isinstance(exc, ModbusIOException):
                self._last_error = "无响应"
                raise ConnectionError(
                    f"Modbus FC{fc} @ {addr} 无响应（超时 {self._timeout}s 或从站离线）"
                ) from exc
            self._last_error = str(exc)
            raise ConnectionError(f"Modbus FC{fc} 请求失败: {exc}") from exc

        # --- Device answered with a Modbus exception: report, keep the link.
        if resp is None or resp.isError():
            if ModbusIOException is not None and isinstance(resp, ModbusIOException):
                self._last_error = f"请求超时或无响应（FC{fc} @ {addr}）"
                raise ConnectionError(
                    f"Modbus FC{fc} @ {addr} 无响应（超时 {self._timeout}s 或从站离线）"
                )
            code = getattr(resp, "exception_code", None)
            name = MODBUS_EXCEPTIONS.get(code, f"EXCEPTION_{code}")
            self._last_error = f"{name}(0x{code:02x})" if code is not None else "未知错误"
            return {
                "kind": "error",
                "value": f"ERROR: {self._last_error}",
                "meta": {
                    "fc": fc,
                    "primitive": FC_NAMES[fc],
                    "addr": addr,
                    "slave_id": slave,
                    "exception_code": code,
                    "exception": name,
                },
            }

        if fc in WRITE_SINGLE_FCS or fc in WRITE_MULTI_FCS:
            return {
                "kind": "ack",
                "value": "OK",
                "meta": {
                    "fc": fc,
                    "primitive": FC_NAMES[fc],
                    "addr": addr,
                    "slave_id": slave,
                    "count": len(spec.get("values", [])) if fc in WRITE_MULTI_FCS else 1,
                },
            }

        if fc in (1, 2):
            bits = list(resp.bits[: spec["count"]])
            return {
                "kind": "bits",
                "value": bits,
                "meta": {
                    "fc": fc,
                    "primitive": FC_NAMES[fc],
                    "addr": addr,
                    "count": len(bits),
                    "slave_id": slave,
                },
            }

        regs = [int(r) & 0xFFFF for r in resp.registers[: spec["count"]]]
        try:
            decoded = decode_registers(regs, dtype, byte_order, word_order)
        except Exception as exc:
            return {
                "kind": "error",
                "value": f"ERROR: {exc}",
                "meta": {"fc": fc, "addr": addr, "registers": regs},
            }
        kind = "regs" if isinstance(decoded, list) else "scalar"
        if dtype == "string":
            kind = "string"
        return {
            "kind": kind,
            "value": decoded,
            "meta": {
                "fc": fc,
                "primitive": FC_NAMES[fc],
                "addr": addr,
                "dtype": dtype,
                "byte_order": byte_order,
                "word_order": word_order,
                "registers": regs,
                "slave_id": slave,
            },
        }

    # --------------------------------------------------------------- receive

    async def receive(self) -> Any:
        """Modbus is strictly master/slave — there are no unsolicited frames.

        Returns ``None`` unless a ``poll`` spec was configured on the device,
        in which case the configured primitive is re-read at most once per
        ``poll_interval_ms`` (used for "wait until robot in position" loops).
        """
        if not self._connected or self._client is None:
            return None
        if self._poll_spec is None or self._poll_interval_ms <= 0:
            return None

        loop = asyncio.get_running_loop()
        now = loop.time()
        if now - self._last_poll_ts < self._poll_interval_ms / 1000.0:
            return None
        self._last_poll_ts = now

        try:
            result = await self._execute(self._poll_spec)
        except Exception as exc:  # never let polling kill the monitor loop
            logger.debug("Modbus poll failed: %s", exc)
            return None
        if self._response_format == "typed":
            return result
        return self._render(result)

    # --------------------------------------------------------------- helpers

    def _render(self, result: Dict[str, Any], fmt: Optional[str] = None) -> Any:
        """Phase 1: flatten to a string so the existing parser/assertions work.

        Set ``response_format = "typed"`` to get the structured dict instead
        (used once P0-1 ``TypedResult`` lands in the pipeline).
        """
        if (fmt or self._response_format) == "typed":
            return result
        value = result.get("value")
        if isinstance(value, bool):
            return "1" if value else "0"
        if isinstance(value, list):
            if all(isinstance(v, bool) for v in value):
                return ",".join("1" if v else "0" for v in value)
            return ",".join(str(v) for v in value)
        if isinstance(value, float):
            return f"{value:.6g}"
        return str(value)

    # ------------------------------------------------------------ introspection

    def get_config_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "host": {
                    "type": "string",
                    "title": "设备 IP / 主机名",
                    "description": "PLC、机械臂或仪表的 Modbus TCP 地址",
                },
                "port": {
                    "type": "integer",
                    "title": "端口",
                    "default": 502,
                    "minimum": 1,
                    "maximum": 65535,
                },
                "slave_id": {
                    "type": "integer",
                    "title": "从站号 (Unit ID)",
                    "default": 1,
                    "minimum": 1,
                    "maximum": 247,
                    "description": "TCP 直连时通常为 1；经网关转发串口设备时填实际从站号",
                },
                "timeout": {
                    "type": "number",
                    "title": "超时（秒）",
                    "default": 3.0,
                    "minimum": 0.1,
                    "maximum": 60,
                },
                "byte_order": {
                    "type": "string",
                    "title": "字节序（寄存器内）",
                    "default": "big",
                    "enum": ["big", "little"],
                },
                "word_order": {
                    "type": "string",
                    "title": "字序（寄存器间）",
                    "default": "big",
                    "enum": ["big", "little"],
                    "description": "读 float32/int32 数值异常时，优先切换此项",
                },
                "response_format": {
                    "type": "string",
                    "title": "返回格式",
                    "default": "text",
                    "enum": ["text", "typed"],
                },
                "poll": {
                    "type": "string",
                    "title": "后台轮询命令（可选）",
                    "description": "例如 FC03:40001:1；留空则不轮询（Modbus 无主动上报）",
                },
                "poll_interval_ms": {
                    "type": "integer",
                    "title": "轮询间隔（毫秒）",
                    "default": 1000,
                    "minimum": 100,
                },
            },
            "required": ["host"],
        }

    def get_device_template(self) -> dict:
        return {
            "name": "Modbus TCP 设备",
            "type": "plc",
            "protocol": "modbus_tcp",
            "connection_type": "ethernet",
            "config": {
                "host": "192.168.1.10",
                "port": 502,
                "slave_id": 1,
                "timeout": 3.0,
                "byte_order": "big",
                "word_order": "big",
            },
        }

    def get_commands(self) -> list:
        def cmd(name: str, syntax: str, desc: str, params: list) -> dict:
            return {"name": name, "syntax": syntax, "description": desc, "parameters": params}

        return [
            cmd("read_coils", "FC01:<地址>:<数量>", "读线圈（可读写位）", ["addr", "count"]),
            cmd("read_discrete_inputs", "FC02:<地址>:<数量>", "读离散输入（只读位）", ["addr", "count"]),
            cmd("read_holding_registers", "FC03:<地址>:<数量>", "读保持寄存器（最常用）", ["addr", "count", "dtype"]),
            cmd("read_input_registers", "FC04:<地址>:<数量>", "读输入寄存器（只读）", ["addr", "count", "dtype"]),
            cmd("write_single_coil", "FC05:<地址>:<0|1>", "写单个线圈", ["addr", "value"]),
            cmd("write_single_register", "FC06:<地址>:<值>", "写单个寄存器", ["addr", "value", "dtype"]),
            cmd("write_multiple_coils", "FC15:<地址>:<v1,v2,...>", "写多个线圈", ["addr", "values"]),
            cmd("write_multiple_registers", "FC16:<地址>:<v1,v2,...>", "写多个寄存器", ["addr", "values", "dtype"]),
        ]

    def get_status(self) -> dict:
        return {
            "name": self.plugin_name,
            "protocol": self.protocol_name,
            "version": self.version,
            "connected": self._connected,
            "host": self._host,
            "port": self._port,
            "slave_id": self._slave_id,
            "byte_order": self._byte_order,
            "word_order": self._word_order,
            "last_error": self._last_error,
            "dependency_ok": AsyncModbusTcpClient is not None,
        }
