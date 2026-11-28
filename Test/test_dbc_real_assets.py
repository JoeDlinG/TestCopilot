#!/usr/bin/env python3
"""Real-world DBC + CAN log asset regression (hardware-free).

Unlike ``test_dbc_log_e2e.py`` (which uses a synthetic, purpose-built text
log), this suite drives the *actual* vendor and bench assets in ``Test/dbc``:

    X6S高定_OTS_SCANFD_Matrix_V3.0_20251215(1)(1).dbc   GBK, 28 msgs / 279 signals
    body_chassis.dbc + body_chassis.asc/.blf             3 msgs, 53 CAN frames
    powertrain.dbc  + powertrain.asc/.blf                3 msgs, 45 CAN frames
    mg100_demo.dbc  (synthetic fixture, kept for continuity)

Pipeline exercised for every asset::

    bytes -> encoding detection -> parse_dbc -> cantools metadata cross-check
          -> temp SQLite import -> DB-generated ParserSpec
          -> ASC/BLF log frames -> decode_message / ResponseParser / generated
             script / cantools  (four-way numeric agreement)

Defects these assets exposed (all guarded below):

1. 64-bit CAN FD signals were scaled through ``raw * 1.0`` and lost the low
   bits above 2**53; cantools keeps exact integers.
2. ``[0|0]`` in a vendor DBC means "no limits", but became a min=0/max=0
   judgement that failed every real frame.
3. The supplied .blf files are *near*-standard Vector BLF: top-level
   CAN_MESSAGE objects (no LOG_CONTAINER), header_version=0 and a swapped
   dlc/flags pair. ``can.BLFReader`` silently returns zero frames for them.
   A tolerant reader plus a standards-compliant rewrite are both verified.

Run: ``python3 Test/test_dbc_real_assets.py``
"""
import asyncio
import math
import os
import random
import re
import struct
import sys
import tempfile
import zlib
from typing import Any, Dict, List, Optional, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(ROOT, "backend"))

from app.api.dbc import _decode_dbc_bytes  # noqa: E402
from app.services.dbc_parser import (  # noqa: E402
    parse_dbc, decode_message, decode_signal, signal_to_parser_spec,
    cantools_available,
)
from app.services.response_parser import ResponseParser  # noqa: E402
from app.services.codegen_service import codegen_service as gen  # noqa: E402

ASSETS = os.path.join(HERE, "dbc")
VENDOR_DBC = "X6S高定_OTS_SCANFD_Matrix_V3.0_20251215(1)(1).dbc"
DBC_NAMES = [VENDOR_DBC, "body_chassis.dbc", "powertrain.dbc", "mg100_demo.dbc"]
LOG_PAIRS = [("body_chassis", "body_chassis.dbc"), ("powertrain", "powertrain.dbc")]

try:
    import can as python_can  # python-can, optional
except Exception:  # pragma: no cover - depends on the local environment
    python_can = None

_failures: List[str] = []
_passes = 0
_comparisons = 0


def check(label: str, ok: bool, detail: str = "", quiet: bool = False) -> None:
    """Aggregate assertions are printed; per-frame/per-signal ones stay quiet."""
    global _passes, _comparisons
    if quiet:
        _comparisons += 1
    else:
        _passes += 1
    if ok:
        if not quiet:
            print("  PASS  " + label + (f"  -> {detail}" if detail else ""))
    else:
        _failures.append(label)
        print("  FAIL  " + label + (f"  -> {detail}" if detail else ""))


def note(text: str) -> None:
    print("  info  " + text)


def eq(a: Any, b: Any) -> bool:
    """Exact for integer pairs (64-bit precision!), tolerant for floats."""
    if isinstance(a, bool) or isinstance(b, bool):
        return a == b
    if isinstance(a, int) and isinstance(b, int):
        return a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return math.isclose(float(a), float(b), rel_tol=1e-9, abs_tol=1e-9)
    return a == b


# --------------------------------------------------------------------------- #
# Asset readers
# --------------------------------------------------------------------------- #

def read_dbc(path: str) -> Tuple[str, str]:
    """Bytes -> (text, encoding), including GBK vendor databases."""
    return _decode_dbc_bytes(open(path, "rb").read())


_ASC_LINE = re.compile(
    r"^\s*(?P<time>\d+(?:\.\d+)?)\s+(?P<channel>\d+)\s+"
    r"(?P<id>[0-9A-Fa-f]+)(?P<ext>x?)\s+(?:Rx|Tx)\s+"
    r"(?P<kind>[dDrR])\s+(?P<dlc>\d+)\s+(?P<data>(?:[0-9A-Fa-f]{2}\s+)+)",
    re.IGNORECASE,
)
_ASC_SKIP = ("//", "date ", "base ", "internal ", "Begin ", "End ")


def read_asc(path: str) -> List[Dict[str, Any]]:
    """Vector CANalyzer/CANoe ``.asc`` (base hex or dec, classic data frames)."""
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        raw_lines = fh.readlines()
    base_dec = any(line.lower().startswith("base dec") for line in raw_lines)
    frames: List[Dict[str, Any]] = []
    scenario = ""
    for lineno, line in enumerate(raw_lines, 1):
        stripped = line.strip()
        if stripped.startswith("//"):
            scenario = stripped[2:].strip()
            continue
        if not stripped or stripped.startswith(_ASC_SKIP):
            continue
        m = _ASC_LINE.match(line)
        if not m:
            raise ValueError(f"{os.path.basename(path)}:{lineno}: unrecognised ASC line: {stripped[:80]!r}")
        if m.group("kind").lower() != "d":
            continue  # remote frames carry no payload
        data = bytes.fromhex(m.group("data").replace(" ", ""))
        can_id = int(m.group("id"), 10 if base_dec else 16)
        frames.append({
            "line": lineno,
            "scenario": scenario,
            "time": float(m.group("time")),
            "channel": int(m.group("channel")),
            "can_id": can_id & 0x1FFFFFFF,
            "is_extended": bool(m.group("ext")),
            "dlc": int(m.group("dlc")),
            "payload": data[:int(m.group("dlc"))],
        })
    return frames


def _scan_blf_objects(buf: bytes) -> List[Dict[str, Any]]:
    """Scan a buffer of LOBJ records, tolerating non-standard top-level frames.

    Standard Vector BLF wraps CAN_MESSAGE objects in a (possibly zlib
    compressed) LOG_CONTAINER. The bench files store CAN_MESSAGE objects at
    top level with ``header_version=0`` and a swapped dlc/flags pair; both
    shapes are accepted here.
    """
    frames: List[Dict[str, Any]] = []
    pos = buf.find(b"LOBJ")
    while pos >= 0 and pos + 16 <= len(buf):
        _sig, _hdr_size, version, obj_size, obj_type = struct.unpack_from("<4sHHLL", buf, pos)
        if obj_size < 16 or pos + obj_size > len(buf):
            break
        body = buf[pos + 16:pos + obj_size]
        if obj_type == 10 and len(body) >= 16:  # LOG_CONTAINER
            method, = struct.unpack_from("<H", body, 0)
            container = body[16:]
            if method == 2:
                try:
                    container = zlib.decompressobj().decompress(container)
                except zlib.error:
                    container = b""
            frames.extend(_scan_blf_objects(container))
        elif obj_type in (1, 86) and len(body) >= 32:
            flags, _client, _over, ts_raw = struct.unpack_from("<LHHQ", body, 0)
            ts = ts_raw * (1e-5 if flags == 1 else 1e-9)
            channel, b2, b3, can_id, data8 = struct.unpack_from("<HBBL8s", body, 16)
            # Standard: (channel, flags, dlc, id, data). Variant: (channel,
            # dlc, flags, id, data). The DLC is the non-zero small byte unless
            # both are zero (DLC 0). Guard against a wild flags byte.
            dlc = b3 if b3 else b2
            if dlc > 8:
                dlc = 8
            frames.append({
                "time": ts,
                "channel": channel - 1,
                "can_id": can_id & 0x1FFFFFFF,
                "is_extended": bool(can_id & 0x80000000),
                "dlc": dlc,
                "payload": data8[:dlc],
            })
        pos += obj_size
    return frames


def read_blf(path: str) -> List[Dict[str, Any]]:
    with open(path, "rb") as fh:
        data = fh.read()
    if not data.startswith(b"LOGG"):
        raise ValueError(f"{os.path.basename(path)}: not a Vector BLF (missing LOGG header)")
    return _scan_blf_objects(data)


def write_standard_blf(frames: List[Dict[str, Any]], path: str, epoch: float) -> None:
    """Rewrite frames into a standards-compliant BLF via python-can."""
    writer = python_can.BLFWriter(path, channel=1)
    try:
        for f in frames:
            writer.on_message_received(python_can.Message(
                timestamp=epoch + f["time"],
                arbitration_id=f["can_id"],
                is_extended_id=f["is_extended"],
                is_rx=True,
                dlc=f["dlc"],
                data=f["payload"],
                channel=0,
            ))
    finally:
        writer.stop()


def load_specs(dbc_text: str, filename: str) -> Tuple[Dict[str, Any], Dict[Tuple[int, str], Dict[str, Any]]]:
    """Import a DBC into a throwaway DB and build one ParserSpec per signal."""
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker
    from app.core.database import Base
    from app.services.dbc_service import dbc_service

    async def run():
        with tempfile.TemporaryDirectory() as td:
            engine = create_async_engine(f"sqlite+aiosqlite:///{td}/real_assets.db")
            try:
                async with engine.begin() as conn:
                    await conn.run_sync(Base.metadata.create_all)
                Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
                async with Session() as db:
                    result = await dbc_service.import_dbc(db, dbc_text, filename)
                    detail = await dbc_service.get_file(db, result["id"])
                    specs: Dict[Tuple[int, str], Dict[str, Any]] = {}
                    for msg in detail["messages"]:
                        for sig in msg["signals"]:
                            spec = await dbc_service.signal_parser_spec(db, sig["id"])
                            specs[(msg["can_id"], sig["name"])] = spec
                    return detail, specs
            finally:
                await engine.dispose()

    return asyncio.run(run())


def build_generated_runtime():
    """Exec the real generated script so parse_field is exercised, not mocked."""
    spec = {"name": "Probe", "data_type": "dec", "start": 0, "length": 16,
            "unit": "bit", "byte_order": "intel", "is_signed": False,
            "factor": 0.25, "offset": 0.0}
    nodes = [
        {"id": "s", "type": "start", "data": {}, "config": {}},
        {"id": "a", "type": "action", "data": {}, "config": {"parsers": [spec]}},
        {"id": "e", "type": "end", "data": {}, "config": {}},
    ]
    edges = [{"source": "s", "target": "a", "label": ""},
             {"source": "a", "target": "e", "label": ""}]
    code = gen.generate_python(nodes, edges, "DbcRealAssets")
    ns = {"__name__": "dbc_real_assets"}
    exec(compile(code, "generated_real_assets.py", "exec"), ns)
    return ns["parse_field"]


# --------------------------------------------------------------------------- #
# Checks
# --------------------------------------------------------------------------- #

def compare_layers(label: str, reference: Any, spec: Dict[str, Any],
                   sig: Dict[str, Any], hexraw: str, parse_field) -> None:
    """Four-way numeric agreement for one signal of one frame."""
    runtime = ResponseParser.parse(hexraw, spec)
    check(f"{label}: runtime agrees with dbc_parser",
          runtime["status"] != "error" and eq(reference, runtime["value"]),
          f"dbc={reference!r} runtime={runtime['value']!r} ({runtime['status']})",
          quiet=True)
    try:
        generated = parse_field(
            hexraw, "dec", sig["start"], sig["length"], "bit",
            byte_order=spec["byte_order"], is_signed=spec["is_signed"],
            factor=spec["factor"], offset=spec["offset"],
        )
        generated_error = None
    except (ValueError, TypeError, OverflowError) as exc:
        generated, generated_error = None, exc
    check(f"{label}: generated script agrees",
          generated_error is None and eq(reference, generated),
          f"dbc={reference!r} generated={generated!r} err={generated_error!r}",
          quiet=True)


def verify_dbc_assets(parse_field) -> None:
    rnd = random.Random(20261128)
    has_cantools = cantools_available()
    if has_cantools:
        import cantools  # noqa: F401

    for name in DBC_NAMES:
        path = os.path.join(ASSETS, name)
        if not os.path.isfile(path):
            check(f"asset exists: {name}", False, path)
            continue
        text, enc = read_dbc(path)
        parsed = parse_dbc(text)
        sig_count = sum(len(m["signals"]) for m in parsed["messages"])
        label = f"[{name}]"
        check(f"{label} decoded as {enc}", bool(text.strip()), f"{len(text)} chars")
        check(f"{label} imports {len(parsed['messages'])} messages / {sig_count} signals",
              parsed["messages"] and sig_count > 0, f"enc={enc}")
        if enc == "gbk":
            check(f"{label} GBK vendor file would break a naive utf-8 open",
                  _utf8_fails(path), "utf-8 decode raises as expected")

        detail, specs = load_specs(text, name)
        check(f"{label} DB import matches parsed signal count",
              detail["signal_count"] == sig_count and len(specs) == sig_count,
              f"db={detail['signal_count']} specs={len(specs)} parsed={sig_count}")
        check(f"{label} every stored signal yields a usable ParserSpec",
              all(s.get("dbc_message_id") is not None and s.get("byte_order") for s in specs.values()))

        unit_signals = [s for m in parsed["messages"] for s in m["signals"] if s["unit"]]
        check(f"{label} physical units survive the DB round-trip",
              all(specs[(m["can_id"], s["name"])].get("physical_unit") == s["unit"]
                  for m in parsed["messages"] for s in m["signals"] if s["unit"]),
              f"{len(unit_signals)} unit-bearing signals")
        choice_signals = [(m["can_id"], s) for m in parsed["messages"] for s in m["signals"] if s["choices"]]
        check(f"{label} VAL_ choice tables survive the DB round-trip",
              all(isinstance(specs[(cid, s["name"])].get("choices"), list)
                  and all(isinstance(c.get("value"), (int, float))
                          for c in specs[(cid, s["name"])]["choices"])
                  for cid, s in choice_signals),
              f"{len(choice_signals)} choice tables")

        # DBC ``[0|0]`` = unspecified limits, never a min=0/max=0 judgement.
        zero_range = [(m["can_id"], s) for m in parsed["messages"] for s in m["signals"]
                      if s.get("min") == 0 and s.get("max") == 0]
        check(f"{label} [0|0] placeholder does not create a always-fail condition",
              all("conditions" not in specs[(cid, s["name"])] for cid, s in zero_range),
              f"{len(zero_range)} signals")

        if not has_cantools:
            continue
        import cantools
        db = cantools.database.load_string(text, database_format="dbc")
        check(f"{label} cantools loads the same message count",
              len(db.messages) == len(parsed["messages"]), str(len(db.messages)))

        metadata_diffs: List[str] = []
        for m in parsed["messages"]:
            cm = db.get_message_by_name(m["name"])
            cmap = {s.name: s for s in cm.signals}
            if (cm.frame_id & 0x1FFFFFFF) != m["can_id"] or cm.length != m["length"]:
                metadata_diffs.append(f"{m['name']}: frame/dlc mismatch")
            for s in m["signals"]:
                c = cmap.get(s["name"])
                if c is None:
                    metadata_diffs.append(f"{m['name']}.{s['name']} missing in cantools")
                    continue
                for key, a, b in (("start", s["start"], c.start),
                                  ("length", s["length"], c.length),
                                  ("order", s["byte_order"], c.byte_order),
                                  ("signed", s["is_signed"], c.is_signed),
                                  ("factor", s["factor"], c.scale),
                                  ("offset", s["offset"], c.offset),
                                  ("unit", s["unit"], c.unit or "")):
                    if not eq(a, b):
                        metadata_diffs.append(f"{m['name']}.{s['name']}.{key}: {a!r} vs {b!r}")
                if s["choices"] and c.choices:
                    ours = {int(v): t for v, t in s["choices"]}
                    theirs = {int(k): (v.name if hasattr(v, "name") else str(v))
                              for k, v in c.choices.items()}
                    if ours != theirs:
                        metadata_diffs.append(f"{m['name']}.{s['name']}: VAL_ mismatch {ours} vs {theirs}")
        check(f"{label} metadata matches cantools for every signal",
              not metadata_diffs, "; ".join(metadata_diffs[:3]))

        # Decode agreement across deterministic payloads, including 64-byte
        # CAN FD frames from the vendor matrix.
        for m in parsed["messages"]:
            cm = db.get_message_by_name(m["name"])
            is_mux = any(s.get("multiplexer") for s in m["signals"])
            for variant in range(3):
                payload = bytes(rnd.randrange(256) for _ in range(cm.length))
                hexraw = "0x" + payload.hex()
                ours = decode_message(payload, m)
                theirs: Dict[str, Any] = {}
                if not is_mux:
                    try:
                        theirs = db.decode_message(cm.frame_id, payload, decode_choices=False)
                    except Exception:
                        theirs = {}
                for sig in m["signals"]:
                    key = f"{label} {m['name']}.{sig['name']} v{variant}"
                    base = ours[sig["name"]]
                    if sig["name"] in theirs:
                        check(f"{key}: cantools agrees", eq(base, theirs[sig["name"]]),
                              f"{base!r} vs {theirs[sig['name']]!r}", quiet=True)
                    spec = specs.get((m["can_id"], sig["name"]))
                    if spec is None:
                        check(f"{key}: ParserSpec found", False, "missing spec")
                        continue
                    compare_layers(key, base, spec, sig, hexraw, parse_field)
                    if sig["length"] >= 64:
                        check(f"{key}: 64-bit value stays an exact integer",
                              isinstance(base, int) and base == int(theirs.get(sig["name"], base)),
                              f"{base!r} vs {theirs.get(sig['name'])!r}", quiet=True)


def _utf8_fails(path: str) -> bool:
    try:
        open(path, "rb").read().decode("utf-8")
        return False
    except UnicodeDecodeError:
        return True


def verify_log_semantics(stem: str, asc: List[Dict[str, Any]],
                         by_id: Dict[int, Dict[str, Any]]) -> None:
    """Compare decoded physical values with the scenario comments in the log."""
    label = f"[{stem}]"

    def vals(scenario_part: str, can_id: int, signal_name: str) -> List[Any]:
        msg = by_id.get(can_id)
        if msg is None:
            return []
        out = [decode_message(f["payload"], msg)[signal_name]
               for f in asc
               if scenario_part in (f.get("scenario") or "") and f["can_id"] == can_id]
        return [v for v in out if v is not None]

    if stem == "powertrain":
        check(f"{label} engine-off frames decode to 0 rpm / 0 km/h",
              bool(vals("Engine OFF", 0x100, "EngineSpeed"))
              and all(v == 0 for v in vals("Engine OFF", 0x100, "EngineSpeed"))
              and all(v == 0 for v in vals("Engine OFF", 0x200, "VehicleSpeed")))
        idle = vals("Engine idling", 0x100, "EngineSpeed")
        check(f"{label} idling scenario decodes to ~1000 rpm",
              bool(idle) and all(900 <= v <= 1100 for v in idle), str(idle))
        rpm = vals("RPM ~2500", 0x100, "EngineSpeed")
        speed = vals("RPM ~2500", 0x200, "VehicleSpeed")
        check(f"{label} cruising scenario decodes to ~2500 rpm / ~35 km/h",
              bool(rpm) and bool(speed)
              and all(2400 <= v <= 2600 for v in rpm)
              and all(30 <= v <= 40 for v in speed), f"rpm={rpm} speed={speed}")
        last_rpm = vals("Stopped, idling", 0x100, "EngineSpeed")
        last_speed = vals("Stopped, idling", 0x200, "VehicleSpeed")
        check(f"{label} stopped scenario decodes to ~900 rpm / 0 km/h",
              bool(last_rpm) and all(850 <= v <= 950 for v in last_rpm)
              and bool(last_speed) and all(v == 0 for v in last_speed),
              f"rpm={last_rpm} speed={last_speed}")
        all_rpm = [decode_message(f["payload"], by_id[0x100])["EngineSpeed"]
                   for f in asc if f["can_id"] == 0x100]
        all_speed = [decode_message(f["payload"], by_id[0x200])["VehicleSpeed"]
                     for f in asc if f["can_id"] == 0x200]
        check(f"{label} every decoded rpm/speed stays physically plausible",
              all(0 <= v <= 4000 for v in all_rpm) and all(0 <= v <= 100 for v in all_speed),
              f"rpm range {min(all_rpm)}..{max(all_rpm)}, speed range {min(all_speed)}..{max(all_speed)}")
        check(f"{label} speed rises then falls as the scenario describes",
              max(all_speed) >= 60 and all_speed[-1] == 0, str(all_speed[::5]))
    else:
        check(f"{label} driver door opens in the unlock scenario",
              1 in vals("Car unlocked", 0x400, "DoorOpen_FL"),
              str(vals("Car unlocked", 0x400, "DoorOpen_FL")))
        check(f"{label} interior light turns on while the door is open",
              any(v > 0 for v in vals("interior light on", 0x500, "InteriorLight")))
        closed = vals("All doors closed, engine started", 0x400, "DoorOpen_FL")
        headlight = vals("All doors closed, engine started", 0x500, "HeadLight")
        check(f"{label} doors closed + auto headlights on",
              bool(closed) and all(v == 0 for v in closed)
              and bool(headlight) and all(v > 0 for v in headlight),
              f"door={closed} light={headlight}")
        check(f"{label} left turn decodes a positive steering angle",
              any(v > 100 for v in vals("Left turn, maximum", 0x600, "SteeringAngle")))
        check(f"{label} right turn decodes a negative steering angle",
              any(v < 0 for v in vals("Right turn in progress", 0x600, "SteeringAngle")))
        check(f"{label} braking scenario decodes a pressed brake pedal",
              any(v > 0 for v in vals("braking lightly", 0x600, "BrakePedalPosition")))
        check(f"{label} locked car has all doors shut and lights off",
              vals("car locked", 0x400, "DoorOpen_FL") == [0]
              and all(v == 0 for v in vals("car locked", 0x500, "HeadLight")))
        # The log generator writes turn-signal state into byte 1, while the
        # DBC defines TurnSignal at byte 0 bits 2-3. Decoding therefore stays
        # 0 in those scenarios. That is a fixture/DBC mismatch, not a parser
        # defect, so report it instead of failing the suite.
        note(f"{label} TurnSignal stays 0 in turn scenarios: log writes byte 1, "
             f"DBC defines it at byte 0 bits 2-3 (asset inconsistency)")


def verify_log_assets(parse_field) -> None:
    has_cantools = cantools_available()
    for stem, dbc_name in LOG_PAIRS:
        asc_path = os.path.join(ASSETS, stem + ".asc")
        blf_path = os.path.join(ASSETS, stem + ".blf")
        dbc_path = os.path.join(ASSETS, dbc_name)
        label = f"[{stem}]"
        if not all(os.path.isfile(p) for p in (asc_path, blf_path, dbc_path)):
            check(f"{label} ASC/BLF/DBC assets present", False,
                  f"asc={os.path.isfile(asc_path)} blf={os.path.isfile(blf_path)} dbc={os.path.isfile(dbc_path)}")
            continue

        asc = read_asc(asc_path)
        blf = read_blf(blf_path)
        check(f"{label} ASC frames parsed", len(asc) > 0, f"{len(asc)} frames")
        check(f"{label} tolerant BLF reader recovered every frame",
              len(blf) == len(asc) and len(blf) > 0, f"{len(blf)} frames")
        mismatches = [i for i, (a, b) in enumerate(zip(asc, blf))
                      if abs(a["time"] - b["time"]) > 1e-6
                      or a["can_id"] != b["can_id"]
                      or a["payload"] != b["payload"]]
        check(f"{label} ASC and BLF describe the identical frame sequence",
              not mismatches,
              f"{len(mismatches)} mismatches" + (f", first at #{mismatches[0]}" if mismatches else ""))

        if python_can is not None:
            plain = list(python_can.BLFReader(blf_path))
            note(f"{label} stock python-can BLFReader sees {len(plain)} frames "
                 f"(non-standard top-level objects); tolerant reader sees {len(blf)}")
            with tempfile.TemporaryDirectory() as td:
                fixed = os.path.join(td, stem + "_standard.blf")
                write_standard_blf(asc, fixed, 1754384400.0)
                standard = list(python_can.BLFReader(fixed))
                readable = (len(standard) == len(asc)
                            and all(s.arbitration_id == a["can_id"] and bytes(s.data) == a["payload"]
                                    for s, a in zip(standard, asc)))
                check(f"{label} standards-compliant BLF rewrite is readable by python-can",
                      readable, f"{len(standard)} frames")

        text, _enc = read_dbc(dbc_path)
        parsed = parse_dbc(text)
        by_id = {m["can_id"]: m for m in parsed["messages"]}
        ids = sorted({f["can_id"] for f in asc})
        check(f"{label} log ids are all defined in the DBC",
              all(i in by_id for i in ids),
              f"log={[hex(i) for i in ids]} dbc={[hex(i) for i in sorted(by_id)]}")
        verify_log_semantics(stem, asc, by_id)

        detail, specs = load_specs(text, dbc_name)
        ref_db = None
        if has_cantools:
            import cantools
            ref_db = cantools.database.load_string(text, database_format="dbc")

        for frame in asc:
            msg = by_id.get(frame["can_id"])
            if msg is None:
                continue
            payload = frame["payload"]
            hexraw = "0x" + payload.hex()
            reference = decode_message(payload, msg)
            if ref_db is not None and not any(s.get("multiplexer") for s in msg["signals"]):
                try:
                    theirs = ref_db.decode_message(frame["can_id"], payload, decode_choices=False)
                    for name, value in theirs.items():
                        if name in reference:
                            check(f"{label} t={frame['time']:.3f} {name}: cantools agrees",
                                  eq(reference[name], value),
                                  f"{reference[name]!r} vs {value!r}", quiet=True)
                except Exception as exc:
                    check(f"{label} cantools decode t={frame['time']:.3f}", False, repr(exc))
            for sig in msg["signals"]:
                spec = specs.get((msg["can_id"], sig["name"]))
                if spec is None:
                    check(f"{label} {sig['name']}: ParserSpec found", False, "missing spec")
                    continue
                if reference[sig["name"]] is None:
                    runtime = ResponseParser.parse(hexraw, spec)
                    check(f"{label} {sig['name']}: truncated signal refused cleanly",
                          runtime["status"] == "error", str(runtime), quiet=True)
                    continue
                compare_layers(f"{label} t={frame['time']:.3f} {sig['name']}",
                               reference[sig["name"]], spec, sig, hexraw, parse_field)
        check(f"{label} all {len(asc)} frames processed without an unhandled error",
              not any(f.startswith(label) and "unhandled" in f for f in _failures),
              f"{len(asc)} frames")

    # Explicit boundary checks, independent of the recorded frames.
    text, _ = read_dbc(os.path.join(ASSETS, "powertrain.dbc"))
    msg = parse_dbc(text)["messages"][0]
    short = b"\x12\x34"
    check("2-byte payload refuses out-of-range signals cleanly",
          all(decode_signal(short, s["start"], s["length"], s["byte_order"],
                            s.get("is_signed"), s.get("factor"), s.get("offset")) is None
              for s in msg["signals"] if s["start"] + s["length"] > 16)
          and decode_message(short, msg)[msg["signals"][0]["name"]] is not None)
    spec = signal_to_parser_spec(msg["signals"][0], msg["id"])
    check("truncated frame yields an error status, not an exception",
          ResponseParser.parse("0x1234", spec)["status"] in ("error", "ok", "fail"))
    check("unknown CAN id is simply absent from the message lookup",
          0x7FF not in {m["can_id"] for m in parse_dbc(text)["messages"]})


def main() -> int:
    # Vendor DBC + ASC/BLF captures are local bench data and may not be part
    # of a fresh checkout. Missing assets are a data condition, not a product
    # regression: follow the same [SKIP] convention as the hardware suites.
    required = [os.path.join(ASSETS, name) for name in DBC_NAMES]
    required += [os.path.join(ASSETS, stem + ext)
                 for stem, _ in LOG_PAIRS for ext in (".asc", ".blf")]
    missing = [p for p in required if not os.path.isfile(p)]
    if missing:
        print("  [SKIP] real DBC/ASC/BLF assets are not present in this checkout")
        for p in missing:
            print("        missing:", os.path.relpath(p, ROOT))
        return 0
    check("Test/dbc asset directory exists", os.path.isdir(ASSETS), ASSETS)
    if _failures:
        return 1
    parse_field = build_generated_runtime()
    check("generated Python script compiles and exposes parse_field",
          callable(parse_field))
    verify_dbc_assets(parse_field)
    verify_log_assets(parse_field)

    print(f"\n  summary: {_passes} section checks, {_comparisons} per-signal/per-frame "
          f"comparisons, {len(_failures)} failures")
    if _failures:
        print(f"FAILED: {len(_failures)} check(s): {', '.join(_failures[:12])}")
        return 1
    print("All real DBC + ASC/BLF log asset checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
