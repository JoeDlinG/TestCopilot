"""CAN DBC parsing and signal decoding (Issue #24).

A single source of truth for turning a ``.dbc`` file into:
  * a database of messages / signals (``parse_dbc``), and
  * the exact bit-level decoding rules (``decode_signal`` / ``decode_message``)
    shared by the *runtime* parser (``response_parser``) and the *generated*
    scripts (``codegen_service``) so they can never diverge.

``cantools`` is the reference implementation but it cannot always be installed
(offline / packaging). We therefore ship a small parser for the DBC constructs
we actually consume (``BO_``, ``SG_``, ``CM_``, ``VAL_``) and keep the bit
arithmetic identical to cantools 39.4.5:

  * ``SG_ ... @1`` = Intel / little-endian : ``start`` is the LSB0 index of the
    signal LSB; value = ``int.from_bytes(payload, 'little') >> start``.
  * ``SG_ ... @0`` = Motorola / big-endian : ``start`` is a **sawtooth** index.
    DBC numbers those start bits LSB-first within a byte, while the payload bit
    string is MSB-first. cantools converts with
    ``linear = 8*(start//8) + (7 - start%8)`` and reads ``length`` bits from
    that MSB-first position, i.e.
    ``int.from_bytes(payload, 'big') >> (8*len - linear - length)``.

Using ``start`` directly (without the sawtooth conversion) silently decodes
*every* Motorola signal from the wrong bits; this is verified against cantools
in ``Test/test_dbc_import_and_parse.py``.
"""
from __future__ import annotations

import math
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

# DBC marks an extended (29-bit) frame by setting bit 31 on the BO_ id.
_EXTENDED_FLAG = 0x80000000
_CAN_ID_MASK = 0x1FFFFFFF


def normalize_byte_order(value: Any) -> str:
    """Return the canonical ``little_endian`` / ``big_endian`` spelling."""
    v = str(value or "little_endian").strip().lower()
    if v in _INTEL:
        return "little_endian"
    if v in _MOTOROLA:
        return "big_endian"
    # Unknown values default to Intel (little-endian) per the DBC convention
    # that ``@1`` is the common case and so a missing order degrades safely.
    # IMPORTANT: the generated PARSE_HELPER must use the SAME default.
    return "little_endian"


def _to_float(value: Any, default: float = 0.0) -> float:
    """Finite float only. NaN/Inf would break JSONResponse (allow_nan=False)."""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return default
    return f if math.isfinite(f) else default


def _to_optional_float(value: Any) -> Optional[float]:
    """Like :func:`_to_float` but keeps ``None`` for missing/invalid values."""
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def sawtooth_to_linear(start: int) -> int:
    """DBC ``@0`` start bit -> MSB-first payload bit index (cantools rule)."""
    return 8 * (start // 8) + (7 - (start % 8))


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

    Returns ``None`` when the payload is too short to hold the signal, the
    geometry is invalid, or the physical value is not finite; otherwise the
    physical value (``raw * factor + offset``) as an ``int`` (integral
    factor/offset) or ``float``.
    """
    if not payload:
        return None
    try:
        start = int(start)
        length = int(length)
    except (TypeError, ValueError):
        return None
    nbits = 8 * len(payload)
    if length <= 0 or start < 0 or length > nbits:
        return None

    order = normalize_byte_order(byte_order)
    mask = (1 << length) - 1
    if order == "little_endian":
        # Intel: ``start`` is the LSB0 position of the signal's least
        # significant bit; ``int.from_bytes(..., 'little')`` reproduces exactly
        # that bit numbering (bit 0 = LSB of byte 0).
        if start + length > nbits:
            return None
        raw = (int.from_bytes(payload, "little") >> start) & mask
    else:
        # Motorola: ``start`` is a sawtooth (MSB0) position. Convert it first;
        # the signal then occupies bits [linear, linear + length) of the
        # MSB-first bit string, i.e. integer bits counted from the top.
        linear = sawtooth_to_linear(start)
        if linear + length > nbits:
            return None
        raw = (int.from_bytes(payload, "big") >> (nbits - linear - length)) & mask

    if is_signed and (raw >> (length - 1)) & 1:
        raw -= 1 << length

    f = _to_float(factor, 1.0)
    o = _to_float(offset, 0.0)
    # 64-bit CAN FD signals exceed 2**53. Multiplying ``raw`` by a *float*
    # factor (even 1.0) promotes it to double and silently drops the low bits:
    # on the vendor matrix a diagnostic payload decoded as
    # 16949912957570496541 became 16949912957570496512. cantools keeps exact
    # integers whenever scale/offset are integral, so mirror that here.
    if f.is_integer() and o.is_integer():
        value: Any = raw * int(f) + int(o)
    else:
        value = raw * f + o
        # Starlette serialises responses with allow_nan=False; a non-finite
        # value would surface as a 500 outside the endpoint's try/except.
        if not math.isfinite(value):
            return None
    return int(value) if isinstance(value, float) and value.is_integer() else value


def dbc_start_to_linear(start: int, length: int, byte_order: Any = "little_endian") -> int:
    """Map the DBC start bit to the engine's linear MSB-first bit index.

    The platform's ``unit="bit"`` slicer numbers bits MSB-first within each
    byte (bit 0 = MSB of byte 0). Both DBC byte orders need conversion:

      * Motorola (``@0``): DBC uses sawtooth numbering -> :func:`sawtooth_to_linear`.
      * Intel (``@1``): DBC points at the signal LSB in LSB0 numbering; the
        signal's MSB is at ``start + length - 1`` -> flip within its byte.

    Used for display/diagnostics — actual decoding must go through
    :func:`decode_signal`.
    """
    order = normalize_byte_order(byte_order)
    if order == "big_endian":
        return sawtooth_to_linear(start)
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
    """Parse the ``n "text" n "text" ...`` tail of a VAL_ line.

    Accepts decimal and ``0x``-prefixed values (vendor DBCs use both).
    """
    def _value(token: str) -> int:
        negative = token.startswith("-")
        digits = token.lstrip("+-")
        n = int(digits, 16) if digits.lower().startswith("0x") else int(digits, 10)
        return -n if negative else n

    choices: List[Tuple[int, str]] = []
    for m in re.finditer(r"(-?(?:0[xX][0-9a-fA-F]+|\d+))\s+\"([^\"]*)\"", body):
        try:
            choices.append((_value(m.group(1)), m.group(2)))
        except ValueError:
            continue
    return choices


def parse_dbc(text: str) -> Dict[str, Any]:
    """Parse DBC text into ``{"messages": [...], "nodes": [...]}``.

    Tolerant by design: malformed lines are skipped, never fatal, so a single
    typo in a large file does not reject the whole import.
    """
    if not text or not text.strip():
        raise ValueError("DBC 文件内容为空")

    messages: List[Dict[str, Any]] = []
    # A DBC may legitimately contain both a standard and an extended frame with
    # the same arbitration id (differing only by bit 31), so keep *all* frames
    # for a numeric id and attach CM_/VAL_ to every matching one.
    by_id: Dict[int, List[Dict[str, Any]]] = {}
    nodes: List[str] = []

    current_message: Optional[Dict[str, Any]] = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        m = _BO_RE.match(line)
        if m:
            raw_id = int(m.group(1))
            msg = {
                "id": raw_id,
                "can_id": raw_id & _CAN_ID_MASK,
                "is_extended": bool(raw_id & _EXTENDED_FLAG),
                "name": m.group(2),
                "length": int(m.group(3)),
                "sender": m.group(4),
                "signals": [],
                "comment": "",
            }
            messages.append(msg)
            by_id.setdefault(raw_id, []).append(msg)
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
                "min": _to_optional_float(m.group("min")),
                "max": _to_optional_float(m.group("max")),
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
            for target in by_id.get(int(m.group(1)), []):
                target["comment"] = m.group(2)
            continue

        m = _CM_SG_RE.match(line)
        if m:
            for target in by_id.get(int(m.group(1)), []):
                for sig in target["signals"]:
                    if sig["name"] == m.group(2):
                        sig["comment"] = m.group(3)
                        break
            continue

        m = _VAL_RE.match(line)
        if m:
            choices = _parse_val_choices(m.group(3))
            for target in by_id.get(int(m.group(1)), []):
                for sig in target["signals"]:
                    if sig["name"] == m.group(2):
                        sig["choices"] = choices
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

    Accepts BOTH shapes of signal dictionary: the raw ``parse_dbc`` output
    (``unit``, ``choices`` as ``List[Tuple[int, str]]``) and the persisted/API
    shape from ``dbc_service._signal_to_dict`` (``physical_unit``, ``choices``
    as ``List[{value, text}]``). Mixing those two contracts used to silently
    drop the physical unit and corrupt every VAL_ choice table.
    """
    order = normalize_byte_order(signal.get("byte_order"))
    raw_message_id: Optional[int] = None
    if message_id is not None:
        try:
            raw_message_id = int(message_id)
        except (TypeError, ValueError):
            raw_message_id = None

    spec: Dict[str, Any] = {
        "name": signal["name"],
        "data_type": "dec",
        "start": signal["start"],
        "length": signal["length"],
        "unit": "bit",
        "byte_order": "intel" if order == "little_endian" else "motorola",
        "is_signed": bool(signal.get("is_signed")),
        "factor": _to_float(signal.get("factor", 1.0), 1.0),
        "offset": _to_float(signal.get("offset", 0.0), 0.0),
        "dbc_signal": signal["name"],
        # Downstream matches real CAN frames, so expose the 29-bit id without
        # the DBC extended-frame flag.
        "dbc_message_id": (raw_message_id & _CAN_ID_MASK) if raw_message_id is not None else None,
    }
    if raw_message_id is not None and (raw_message_id & _EXTENDED_FLAG):
        spec["dbc_is_extended"] = True
        spec["dbc_raw_message_id"] = raw_message_id

    unit = signal.get("unit") or signal.get("physical_unit")
    if unit:
        spec["physical_unit"] = unit
    if signal.get("comment"):
        spec["comment"] = signal["comment"]

    normalised_choices: List[Dict[str, Any]] = []
    for choice in signal.get("choices") or []:
        if isinstance(choice, dict):
            normalised_choices.append({"value": choice.get("value"), "text": choice.get("text", "")})
        elif isinstance(choice, (list, tuple)) and len(choice) >= 2:
            normalised_choices.append({"value": choice[0], "text": choice[1]})
    if normalised_choices:
        spec["choices"] = normalised_choices

    if signal.get("multiplexer"):
        spec["multiplexer"] = signal["multiplexer"]

    conditions: Dict[str, Any] = {}
    lo = _to_optional_float(signal.get("min"))
    hi = _to_optional_float(signal.get("max"))
    # ``[0|0]`` is the DBC convention for "physical limits not specified"
    # (common on 64-bit diagnostic payloads). Emitting min=0/max=0 would
    # mark every real frame as a fail. Only a genuinely bounded range is
    # worth turning into a judgement condition.
    if lo == 0 and hi == 0:
        lo = hi = None
    if lo is not None:
        conditions["min"] = lo
    if hi is not None:
        conditions["max"] = hi
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

    db = cantools.database.load_string(dbc_text, database_format="dbc")
    message = db.get_message_by_name(message_name)
    return db.decode_message(message.frame_id, bytes(payload), decode_choices=False)
