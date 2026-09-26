"""Response parsing and judgement engine for test step results.

A test step may declare one or more *parsers* on its flow node::

    config.parsers = [
        {
            "name": "母线电压",
            "data_type": "hex",      # hex | bin | bool | dec | string
            "start": 0,              # start offset
            "length": 2,             # number of units
            "unit": "byte",          # bit | byte
            "conditions": {
                "min": 10, "max": 60,
                "equals": ["0x01", "0x02"]   # OR semantics
            }
        }
    ]

The same engine is used by
  * the execution engine  -> to decide pass/fail at runtime
  * the code generator    -> so generated scripts judge identically
"""
from __future__ import annotations
import re
from typing import Any, Dict, List, Optional, Tuple

# Public data types offered by the configuration UI
DATA_TYPES = ("hex", "bin", "bool", "dec", "string")
UNITS = ("bit", "byte")

# Shown when a reply carries no payload at all (empty frame / timeout).
# It is deliberately a string so the UI can display it and so it never
# turns into a bogus numeric sample.
UNKNOWN = "unknown"

# status values carried by every parsed field
STATUS_OK = "ok"        # parsed and judged, passed
STATUS_FAIL = "fail"    # parsed and judged, failed
STATUS_UNKNOWN = "unknown"  # empty frame - nothing to judge
STATUS_ERROR = "error"  # configuration / out-of-range problem

_HEX_RE = re.compile(r"^[0-9a-fA-F]+$")


class ResponseParser:
    """Stateless helpers for slicing and judging device responses."""

    # ------------------------------------------------------------------ #
    # Normalisation / extraction
    # ------------------------------------------------------------------ #

    @staticmethod
    def _pick_hex_groups(groups: List[str], hex_field: Any) -> List[str]:
        """Choose which ``0x..`` field(s) of a reply form the payload.

        A reply may carry several hex fields
        (``1,STD,0X11,0X0102030000000000``). Joining *all* of them silently
        shifts every offset, so the user can pin one of them.
        """
        if not groups:
            return []
        hf = str(hex_field if hex_field is not None else "all").strip().lower()
        if hf in ("", "all", "*", "全部"):
            return groups
        if hf in ("first", "第一个"):
            return groups[:1]
        if hf in ("last", "最后", "最后一个"):
            return groups[-1:]
        try:
            idx = int(hf)
        except (TypeError, ValueError):
            return groups
        if idx < 0:
            idx = len(groups) + idx
        return groups[idx:idx + 1] if 0 <= idx < len(groups) else groups[-1:]

    @classmethod
    def is_empty_frame(cls, raw: Any) -> bool:
        """True when the reply carries no data at all.

        Mini-Gateway style replies mark the payload with ``0X``; when nothing
        was received the field is empty (``CAN1,RPLY1,0X``), which means
        "timeout / no frame" - **not** the value zero. Parsing those bytes
        would slice the literal text (',' = 0x2C, 'X' = 0x58) and report
        nonsense, so callers must detect it first.
        """
        if raw is None:
            return True
        if isinstance(raw, (bytes, bytearray)):
            return len(raw) == 0
        s = str(raw).strip()
        if not s:
            return True
        for m in re.finditer(r"(?i)0x([0-9a-f]*)(?![0-9a-f])", s):
            if not m.group(1):
                return True
        return False

    @classmethod
    def to_bytes(cls, raw: Any, hex_field: Any = "all") -> bytes:
        """Best-effort conversion of a device response into raw bytes.

        Handles hex strings ("0x85 02 01", "850201", "85,02,01"), byte lists
        and plain text (UTF-8 encoded).
        """
        if raw is None:
            return b""
        if isinstance(raw, bytes):
            return raw
        if isinstance(raw, (list, tuple)):
            return bytes(b & 0xFF for b in raw if isinstance(b, int))
        if isinstance(raw, int):
            return bytes([raw & 0xFF])

        s = str(raw).strip()
        if not s:
            return b""

        # Device replies are often prefixed text, e.g. "CAN1,RPLY1,0X850201".
        # Prefer the explicitly hex-tagged field(s) so the payload is what
        # gets parsed.
        hex_groups = re.findall(r"(?i)\b0x([0-9a-f]+)\b", s)
        if hex_groups:
            joined = "".join(cls._pick_hex_groups(hex_groups, hex_field))
            if joined and len(joined) % 2 == 0:
                try:
                    return bytes.fromhex(joined)
                except ValueError:
                    pass

        # drop separators and 0x prefixes, then try a pure-hex interpretation
        compact = re.sub(r"[,\s_]+", "", s)
        compact = re.sub(r"(?i)0x", "", compact)
        if compact and _HEX_RE.match(compact) and len(compact) % 2 == 0:
            try:
                return bytes.fromhex(compact)
            except ValueError:
                pass
        return s.encode("utf-8", errors="replace")

    @staticmethod
    def extract(raw: Any, spec: Dict[str, Any]) -> Tuple[Any, Optional[str]]:
        """Slice the response according to start/length/unit.

        Returns ``(value, error)``. ``value`` is an ``int`` for bit units and
        ``bytes`` for byte units.
        """
        data = ResponseParser.to_bytes(raw, spec.get("hex_field", "all"))
        try:
            start = max(0, int(spec.get("start") or 0))
            length = max(1, int(spec.get("length") or 1))
        except (TypeError, ValueError):
            return None, "起始位/数据长度必须是数字"

        unit = str(spec.get("unit") or "byte").lower()
        if unit not in UNITS:
            return None, f"单位必须是 {'/'.join(UNITS)}"

        if unit == "bit":
            bits = "".join(f"{b:08b}" for b in data)
            if start + length > len(bits):
                return None, (
                    f"位域越界: 需要 bit[{start}:{start + length}]，"
                    f"数据仅 {len(bits)} bit"
                )
            return int(bits[start:start + length], 2), None

        if start + length > len(data):
            return None, (
                f"字节越界: 需要 byte[{start}:{start + length}]，"
                f"数据仅 {len(data)} byte"
            )
        return data[start:start + length], None

    @staticmethod
    def convert(value: Any, data_type: str) -> Any:
        """Convert a sliced value into the configured data type."""
        dt = str(data_type or "string").lower()
        if dt == "hex":
            if isinstance(value, int):
                return f"0x{value:X}"
            return "0x" + value.hex().upper()
        if dt == "bin":
            if isinstance(value, int):
                width = max(1, value.bit_length())
                return format(value, f"0{width}b")
            return "".join(f"{b:08b}" for b in value)
        if dt == "bool":
            if isinstance(value, int):
                return bool(value)
            return any(b for b in value) if value else False
        if dt == "dec":
            if isinstance(value, int):
                return value
            # Textual replies ("100", "23.5") should read as their numeric
            # value, not as a big-endian byte concatenation.
            txt = value.decode("utf-8", errors="replace").strip().rstrip("\x00")
            if txt:
                try:
                    return float(txt) if re.search(r"[.eE]", txt) else int(txt)
                except ValueError:
                    pass
            return int.from_bytes(value, "big")
        # string (default)
        if isinstance(value, int):
            return str(value)
        return value.decode("utf-8", errors="replace").rstrip("\x00").strip()

    # ------------------------------------------------------------------ #
    # Judgement
    # ------------------------------------------------------------------ #

    @staticmethod
    def to_number(value: Any) -> Optional[float]:
        """Numeric view of a parsed value (hex/bin strings included)."""
        if isinstance(value, bool):
            return float(int(value))
        if isinstance(value, (int, float)):
            return float(value)
        s = str(value).strip()
        if not s:
            return None
        if re.fullmatch(r"(?i)0x[0-9a-f]+", s):
            return float(int(s, 16))
        if re.fullmatch(r"[01]+", s):
            return float(int(s, 2))
        try:
            return float(s)
        except ValueError:
            return None

    @staticmethod
    def _as_list(values: Any) -> List[str]:
        """Normalise the "equals" option into a list (comma string allowed)."""
        if values is None:
            return []
        if isinstance(values, str):
            return [v.strip() for v in values.split(",") if v.strip()]
        if isinstance(values, (list, tuple, set)):
            return [str(v).strip() for v in values if str(v).strip() != ""]
        return [str(values).strip()]

    @classmethod
    def evaluate(cls, value: Any, conditions: Optional[Dict[str, Any]]) -> Tuple[bool, str]:
        """Apply min/max and equals (OR) conditions to a parsed value."""
        cond = conditions or {}
        checks: List[str] = []

        lo = cond.get("min")
        hi = cond.get("max")
        has_lo = lo is not None and str(lo).strip() != ""
        has_hi = hi is not None and str(hi).strip() != ""
        if has_lo or has_hi:
            num = cls.to_number(value)
            if num is None:
                return False, f"无法将解析值 {value!r} 转为数值做范围判断"
            if has_lo:
                try:
                    if num < float(lo):
                        return False, f"低于最小值: {value} < {lo}"
                except (TypeError, ValueError):
                    return False, f"最小值 {lo!r} 不是合法数字"
            if has_hi:
                try:
                    if num > float(hi):
                        return False, f"超出最大值: {value} > {hi}"
                except (TypeError, ValueError):
                    return False, f"最大值 {hi!r} 不是合法数字"
            checks.append(
                f"{lo if has_lo else '-∞'} ≤ {value} ≤ {hi if has_hi else '∞'}"
            )

        equals = cls._as_list(cond.get("equals"))
        if equals:
            options = [str(o) for o in equals]
            # compare case-insensitively, and numerically when both are numbers
            actual_num = cls.to_number(value)
            matched = False
            for opt in options:
                if str(value).strip().lower() == opt.strip().lower():
                    matched = True
                    break
                opt_num = cls.to_number(opt)
                if actual_num is not None and opt_num is not None and actual_num == opt_num:
                    matched = True
                    break
            if not matched:
                return False, f"不等于任一期望值: {value} ∉ {options}"
            checks.append(f"= {options[0]}" if len(options) == 1 else f"∈ {options}")

        if not checks:
            return True, "未设置判断条件（仅解析）"
        return True, " 且 ".join(checks)

    # ------------------------------------------------------------------ #
    # Entry points
    # ------------------------------------------------------------------ #

    @classmethod
    def parse(cls, raw: Any, spec: Dict[str, Any], index: int = 0) -> Dict[str, Any]:
        """Parse one field of a response and judge it.

        Always returns a dict - never raises - so a broken configuration
        shows up as a failed judgement instead of breaking the run.
        """
        name = spec.get("name") or f"字段{index + 1}"
        data_type = str(spec.get("data_type") or "string").lower()
        if data_type not in DATA_TYPES:
            data_type = "string"

        base = {
            "name": name,
            "data_type": data_type,
            "unit": spec.get("unit", "byte"),
            "start": spec.get("start", 0),
            "length": spec.get("length", 1),
        }

        # Empty frame ("CAN1,RPLY1,0X" = timeout / nothing received):
        # there is no value to judge. Report "unknown" and skip the
        # judgement instead of slicing the reply text into fake numbers.
        if cls.is_empty_frame(raw):
            return {
                **base,
                "value": UNKNOWN,
                "status": "unknown",
                "ok": True,
                "detail": "空帧（无数据 / 超时），跳过判定",
            }

        value, err = cls.extract(raw, spec)
        if err:
            return {
                **base,
                "value": None,
                "status": "error",
                "ok": False,
                "detail": err,
            }

        converted = cls.convert(value, data_type)
        ok, detail = cls.evaluate(converted, spec.get("conditions"))
        return {
            **base,
            "value": converted,
            "status": "ok" if ok else "fail",
            "ok": ok,
            "detail": detail,
        }

    @classmethod
    def parse_all(cls, raw: Any, parsers: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
        """Parse every configured field of one response."""
        if not parsers:
            return []
        return [cls.parse(raw, spec, i) for i, spec in enumerate(parsers)]

    @classmethod
    def summarize(cls, parsed: List[Dict[str, Any]]) -> Tuple[bool, str]:
        """Aggregate parsed fields into (all_passed, human readable text)."""
        if not parsed:
            return True, ""
        ok = all(p.get("ok") for p in parsed)
        parts = []
        for p in parsed:
            flag = "UNKNOWN" if p.get("status") == STATUS_UNKNOWN else (
                "PASS" if p.get("ok") else "FAIL"
            )
            parts.append(f"{p.get('name')}={p.get('value')} [{flag}] {p.get('detail')}")
        return ok, "; ".join(parts)

    @classmethod
    def summarize_series(
        cls, samples: List[List[Dict[str, Any]]]
    ) -> Tuple[bool, str]:
        """Aggregate *every* reply of a step into (all_passed, summary).

        A step may repeat the same command N times ("read 100 times"), so one
        sample per reply is produced. The summary stays compact: per field it
        reports the latest value, the numeric range, and how many samples were
        empty frames or failed judgement.
        """
        if not samples:
            return True, ""
        if len(samples) == 1:
            return cls.summarize(samples[0])

        ok = all(all(p.get("ok") for p in sample) for sample in samples)

        stats: Dict[str, Dict[str, Any]] = {}
        for sample in samples:
            for p in sample or []:
                name = str(p.get("name") or "?")
                st = stats.setdefault(name, {
                    "n": 0, "unknown": 0, "fail": 0, "last": None, "vals": [],
                })
                st["n"] += 1
                if p.get("status") == STATUS_UNKNOWN:
                    st["unknown"] += 1
                    if st["last"] is None:
                        st["last"] = UNKNOWN
                    continue
                if not p.get("ok"):
                    st["fail"] += 1
                    continue
                st["last"] = p.get("value")
                num = cls.to_number(p.get("value"))
                if num is not None:
                    st["vals"].append(num)

        parts = []
        for name, st in stats.items():
            seg = f"{name}×{st['n']}"
            if st["vals"]:
                seg += (
                    f" 最新={st['last']}"
                    f" 最小={min(st['vals']):g} 最大={max(st['vals']):g}"
                )
            else:
                seg += f" 最新={st['last']}"
            if st["unknown"]:
                seg += f" 空帧{st['unknown']}"
            if st["fail"]:
                seg += f" FAIL{st['fail']}"
            parts.append(seg)
        return ok, f"共 {len(samples)} 次采样: " + "; ".join(parts)


response_parser = ResponseParser()
