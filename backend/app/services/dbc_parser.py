"""CAN DBC parsing and signal decoding (Issue #24).

A single source of truth for turning a ``.dbc`` file into:
  * a database of messages / signals (``parse_dbc``), and
  * the exact bit-level decoding rules (``decode_signal`` / ``decode_message``)
    shared by the *runtime* parser (``response_parser``) and the *generated*
    scripts (``codegen_service``) so they can never diverge.

``cantools`` is the recommended implementation but it cannot always be
installed (offline / packaging). We therefore ship a small, well-tested parser
for the DBC constructs we actually consume (``BO_``, ``SG_``, ``CM_``, ``VAL_``,
``BA_``/``BA_DEF_``) and keep the bit arithmetic identical to cantools:

  * ``SG_ ... @1`` = Intel / little-endian : ``start`` is the LSB0 index of the
    signal LSB; value = ``int.from_bytes(payload, 'little') >> start``.
  * ``SG_ ... @0`` = Motorola / big-endian : ``start`` is the MSB0 (sawtooth)
    index of the signal MSB; value =
    ``int.from_bytes(payload, 'big') >> (8*len - start - length)``.

Both are validated against hand-computed vectors in the test suite, and against
``cantools`` itself when the package is importable.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

# --------------------------------------------------------------------------- #
# Normalisation helpers
# --------------------------------------------------------------------------- #

# "little_endian" (DBC @1, Intel) and "big_endian" (DBC @0, Motorola) are the
# canonical internal spellings; the UI/issue vocabulary ("intel"/"motorola")
# and the raw DBC tokens are accepted everywhere.
_INTEL = ("intel", "little_endian", "little", "1")
_MOTOROLA = ("motorola", "big_endian", "big", "0")


def normalize_byte_order(value: Any) -> str:
    """Return the canonical ``little_endian`` / ``big_endian`` spelling."""
    v = str(value or "little_endian").strip().lower()
    if v in _INTEL:
        return "little_endian"
    if v in _MOTOROLA:
        return "big_endian"
    # Unknown values default to Intel (little-endian) per the DBC convention
    # that ``@1`` is the common case and so a missing order degrades safely.
    return "little_endian"


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


# --------------------------------------------------------------------------- #
# Bit-level decoding (must match cantools)
# --------------------------------------------------------------------------- #

def decode_signal(
    payload: bytes,
    start: int,
    length: int,
    byte_order: Any = "little_endian",
    is_signed: bool = False,
    factor: Any = 1.0,
    offset: Any = 0.0,
) -> Optional[float]:
    """Decode one signal from a raw CAN payload.

    Returns ``None`` when the payload is too short to hold the signal, otherwise
    the physical value (``raw * factor + offset``) as an ``int`` (integral
    factor/offset) or ``float``.
    """
    if not payload:
        return None
    nbits = 8 * len(payload)
    if length <= 0 or start < 0 or start + length > nbits:
        return None

    order = normalize_byte_order(byte_order)
    mask = (1 << length) - 1
    if order == "little_endian":
        # Intel: ``start`` is the LSB0 position of the signal's least
        # significant bit; ``int.from_bytes(..., 'little')`` reproduces exactly
        # that bit numbering (bit 0 = LSB of byte 0).
        raw = (int.from_bytes(payload, "little") >> start) & mask
    else:
        # Motorola: ``start`` is the MSB0 (sawtooth) position of the signal's
        # most significant bit. ``int.from_bytes(..., 'big')`` numbers bits from
        # the LSB of the last byte, so the signal occupies bits
        # [nbits - start - length, nbits - start).
        raw = (int.from_bytes(payload, "big") >> (nbits - start - length)) & mask

    if is_signed and length and (raw >> (length - 1)) & 1:
        raw -= 1 << length

    f = _to_float(factor, 1.0)
    o = _to_float(offset, 0.0)
    value = raw * f + o
    return int(value) if isinstance(value, float) and value.is_integer() else value


def dbc_start_to_linear(start: int, length: int, byte_order: Any = "little_endian") -> int:
    """Map the DBC (sawtooth) start bit to the engine's linear MSB-first index.

    The platform's ``unit="bit"`` slicer numbers bits MSB-first within each
    byte (bit 0 = MSB of byte 0). For Motorola signals the DBC start bit already
    uses that numbering, so the conversion is the identity; for Intel signals
    the DBC start bit points at the LSB, so we return the equivalent MSB
    position (used for display/diagnostics — actual decoding must go through
    :func:`decode_signal`).
    """
    order = normalize_byte_order(byte_order)
    if order == "big_endian":
        return start
    # Intel: signal LSB is at LSB0 position ``start``; its MSB is at LSB0
    # position ``start + length - 1``. Convert LSB0 -> MSB0 within its byte.
    msb = start + length - 1
    byte, bit = divmod(msb, 8)
    return byte * 8 + (7 - bit)


# --------------------------------------------------------------------------- #
# DBC text parsing
# --------------------------------------------------------------------------- #

_SG_RE = re.compile(
    r"^\s*SG_\s+(?P<name>[A-Za-z_][\w]*)"
    r"(?:\s+(?P<mux>M|m\d+M?))?"                # multiplexer indicator
    r"\s*:\s*"
    r"(?P<start>\d+)\|(?P<length>\d+)@(?P<byteorder>[01])(?P<sign>[+-])"
    r"\s*\(\s*(?P<factor>[^,()]+?)\s*,\s*(?P<offset>[^)]+?)\s*\)"
    r"(?:\s*\[\s*(?P<min>[^|]+?)\s*\|\s*(?P<max>[^\]]+?)\s*\])?"
    r"(?:\s*\"(?P<unit>[^\"]*)\")?"
    r"\s*(?P<receivers>.*?)\s*$"
)

_BO_RE = re.compile(r"^\s*BO_\s+(\d+)\s+([A-Za-z_][\w]*)\s*:\s*(\d+)\s+(\S+)")
_VAL_RE = re.compile(r"^\s*VAL_\s+(\d+)\s+([A-Za-z_][\w]*)\s+(.+?)\s*;")
_CM_BO_RE = re.compile(r"^\s*CM_\s+BO_\s+(\d+)\s+\"(.*)\"\s*;")
_CM_SG_RE = re.compile(r"^\s*CM_\s+SG_\s+(\d+)\s+([A-Za-z_][\w]*)\s+\"(.*)\"\s*;")
_BA_RE = re.compile(r"^\s*BA_\s+\"([^\"]+)\"\s+([A-Z_]*)\s+(\d+)\s+(\S+)\s*;")
_BU_RE = re.compile(r"^\s*BU_\s*:(.*)")


def _parse_val_choices(body: str) -> List[Tuple[int, str]]:
    """Parse the ``n "text" n "text" ...`` tail of a VAL_ line."""
    choices: List[Tuple[int, str]] = []
    for m in re.finditer(r"(-?\d+)\s+\"([^\"]*)\"", body):
        choices.append((int(m.group(1)), m.group(2)))
    return choices


def parse_dbc(text: str) -> Dict[str, Any]:
    """Parse DBC text into ``{"messages": [...], "nodes": [...]}``.

    Tolerant by design: malformed lines are skipped, never fatal, so a single
    typo in a large file does not reject the whole import.
    """
    if not text:
        raise ValueError("DBC 文件内容为空")

    messages: List[Dict[str, Any]] = []
    by_id: Dict[int, Dict[str, Any]] = {}
    nodes: List[str] = []

    current_message: Optional[Dict[str, Any]] = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        m = _BO_RE.match(line)
        if m:
            msg = {
                "id": int(m.group(1)),
                "name": m.group(2),
                "length": int(m.group(3)),
                "sender": m.group(4),
                "signals": [],
                "comment": "",
            }
            messages.append(msg)
            by_id[msg["id"]] = msg
            current_message = msg
            continue

        m = _SG_RE.match(line)
        if m and current_message is not None:
            byte_order = "little_endian" if m.group("byteorder") == "1" else "big_endian"
            signal = {
                "name": m.group("name"),
                "start": int(m.group("start")),
                "length": int(m.group("length")),
                "byte_order": byte_order,
                "is_signed": m.group("sign") == "-",
                "factor": _to_float(m.group("factor"), 1.0),
                "offset": _to_float(m.group("offset"), 0.0),
                "min": _to_float(m.group("min")) if m.group("min") is not None else None,
                "max": _to_float(m.group("max")) if m.group("max") is not None else None,
                "unit": (m.group("unit") or ""),
                "receivers": [r.strip() for r in (m.group("receivers") or "").split(",") if r.strip()],
                "multiplexer": m.group("mux") or None,
                "comment": "",
                "choices": [],
            }
            current_message["signals"].append(signal)
            continue

        m = _BU_RE.match(line)
        if m:
            nodes = [n.strip() for n in m.group(1).split() if n.strip()]
            continue

        m = _CM_BO_RE.match(line)
        if m:
            target = by_id.get(int(m.group(1)))
            if target is not None:
                target["comment"] = m.group(2)
            continue

        m = _CM_SG_RE.match(line)
        if m:
            target = by_id.get(int(m.group(1)))
            if target is not None:
                for sig in target["signals"]:
                    if sig["name"] == m.group(2):
                        sig["comment"] = m.group(3)
                        break
            continue

        m = _VAL_RE.match(line)
        if m:
            target = by_id.get(int(m.group(1)))
            if target is not None:
                for sig in target["signals"]:
                    if sig["name"] == m.group(2):
                        sig["choices"] = _parse_val_choices(m.group(3))
                        break
            continue

        # BA_ / BA_DEF_ / NS_ / BS_ / VERSION / ... are not needed for parsing
        # or decoding, so they are intentionally ignored.

    if not messages:
        raise ValueError("未在 DBC 中解析到任何 BO_ 报文定义")

    return {"messages": messages, "nodes": nodes}


# --------------------------------------------------------------------------- #
# Signal -> ParserSpec mapping
# --------------------------------------------------------------------------- #

def signal_to_parser_spec(signal: Dict[str, Any], message_id: Optional[int] = None) -> Dict[str, Any]:
    """Build a platform ``ParserSpec`` (one parser entry) from one DBC signal.

    The result carries the extra DBC-only keys (``byte_order``, ``is_signed``,
    ``factor``, ``offset``) that make ``response_parser`` and the generated
    scripts decode the signal with ``decode_signal`` instead of the plain
    byte/bit slicer.
    """
    order = normalize_byte_order(signal.get("byte_order"))
    spec: Dict[str, Any] = {
        "name": signal["name"],
        "data_type": "dec",
        "start": signal["start"],
        "length": signal["length"],
        "unit": "bit",
        "byte_order": "intel" if order == "little_endian" else "motorola",
        "is_signed": bool(signal.get("is_signed")),
        "factor": signal.get("factor", 1.0),
        "offset": signal.get("offset", 0.0),
        "dbc_signal": signal["name"],
        "dbc_message_id": message_id,
    }
    if signal.get("unit"):
        spec["physical_unit"] = signal["unit"]
    if signal.get("comment"):
        spec["comment"] = signal["comment"]
    if signal.get("choices"):
        spec["choices"] = [{"value": v, "text": t} for v, t in signal["choices"]]
    if signal.get("multiplexer"):
        spec["multiplexer"] = signal["multiplexer"]

    conditions: Dict[str, Any] = {}
    if signal.get("min") is not None:
        conditions["min"] = signal["min"]
    if signal.get("max") is not None:
        conditions["max"] = signal["max"]
    if conditions:
        spec["conditions"] = conditions
    return spec


def decode_message(payload: bytes, message: Dict[str, Any]) -> Dict[str, Optional[float]]:
    """Decode every signal of a message; returns ``{signal_name: value}``."""
    out: Dict[str, Optional[float]] = {}
    for sig in message.get("signals", []):
        out[sig["name"]] = decode_signal(
            payload,
            sig["start"],
            sig["length"],
            sig["byte_order"],
            sig.get("is_signed", False),
            sig.get("factor", 1.0),
            sig.get("offset", 0.0),
        )
    return out


# --------------------------------------------------------------------------- #
# Optional cantools cross-validation (single source of truth when available)
# --------------------------------------------------------------------------- #

def cantools_available() -> bool:
    try:
        import cantools  # noqa: F401
        return True
    except Exception:
        return False


def decode_message_with_cantools(dbc_text: str, payload: bytes, message_name: str) -> Dict[str, Any]:
    """Decode using ``cantools`` (requires the package).

    Used by the test suite to prove our hand-rolled bit arithmetic is
    bit-for-bit identical to the reference implementation.
    """
    import cantools  # local import: optional dependency

    db = cantools.db.load_string(dbc_text)
    message = db.get_message_by_name(message_name)
    decoded = db.decode_message(message.frame_id, bytes(payload))
    return decoded
