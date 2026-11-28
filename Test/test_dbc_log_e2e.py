#!/usr/bin/env python3
"""End-to-end DBC + CAN log simulation (Issue #24 validation, hardware-free).

Loads the DBC and the synthetic frame log from ``Test/dbc/`` and drives the
full pipeline for every frame:

    log frame -> DBC message lookup (by CAN id)
              -> dbc_parser.decode_message   (reference)
              -> ResponseParser.parse        (runtime, via DB-generated ParserSpec)
              -> generated script parse_field (codegen)
              -> cantools (optional independent reference)

Unknown ids and truncated frames must be skipped/refused without raising.

Run: ``python3 Test/test_dbc_log_e2e.py``
"""
import asyncio
import math
import os
import sys
import tempfile
from typing import Any, Dict, List

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(ROOT, "backend"))

from app.services.dbc_parser import (  # noqa: E402
    parse_dbc, decode_message, cantools_available,
)
from app.services.response_parser import ResponseParser  # noqa: E402
from app.services.codegen_service import codegen_service as gen  # noqa: E402

DBC_PATH = os.path.join(HERE, "dbc", "mg100_demo.dbc")
LOG_PATH = os.path.join(HERE, "dbc", "mg100_demo.log")

_failures: List[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("  PASS  " if ok else "  FAIL  ") + label + (f"  -> {detail}" if detail else ""))
    if not ok:
        _failures.append(label)


def eq(a, b) -> bool:
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return math.isclose(float(a), float(b), rel_tol=1e-9, abs_tol=1e-9)
    return a == b


def read_log(path: str) -> List[Dict[str, Any]]:
    """Parse ``<time> <channel> <0xID> <dlc> <hex bytes...>`` lines."""
    frames = []
    with open(path, encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, 1):
            line = raw.split("#", 1)[0].strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) < 4:
                raise ValueError(f"{path}:{lineno}: 字段不足: {line!r}")
            ts, channel, can_id, dlc = parts[0], parts[1], parts[2], parts[3]
            payload = bytes.fromhex("".join(parts[4:]))
            frames.append({
                "line": lineno,
                "time": float(ts),
                "channel": int(channel),
                "can_id": int(can_id, 16),
                "dlc": int(dlc),
                "payload": payload,
            })
    return frames


def load_specs(dbc_text: str) -> Dict[str, Dict[str, Any]]:
    """Import the DBC into a temp DB and build a ParserSpec per stored signal."""
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker
    from app.core.database import Base
    from app.services.dbc_service import dbc_service

    async def run():
        with tempfile.TemporaryDirectory() as td:
            engine = create_async_engine(f"sqlite+aiosqlite:///{td}/e2e.db")
            try:
                async with engine.begin() as conn:
                    await conn.run_sync(Base.metadata.create_all)
                Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
                async with Session() as db:
                    result = await dbc_service.import_dbc(db, dbc_text, "mg100_demo.dbc")
                    detail = await dbc_service.get_file(db, result["id"])
                    specs = {}
                    for msg in detail["messages"]:
                        for sig in msg["signals"]:
                            specs[sig["name"]] = await dbc_service.signal_parser_spec(db, sig["id"])
                    return detail, specs
            finally:
                await engine.dispose()

    return asyncio.run(run())


def build_generated_runtime():
    spec = {"name": "EngineSpeed", "data_type": "dec", "start": 0, "length": 16,
            "unit": "bit", "byte_order": "intel", "is_signed": False,
            "factor": 0.25, "offset": 0.0}
    nodes = [
        {"id": "s", "type": "start", "data": {}, "config": {}},
        {"id": "a", "type": "action", "data": {}, "config": {"parsers": [spec]}},
        {"id": "e", "type": "end", "data": {}, "config": {}},
    ]
    edges = [{"source": "s", "target": "a", "label": ""},
             {"source": "a", "target": "e", "label": ""}]
    code = gen.generate_python(nodes, edges, "DbcLogE2E")
    ns = {"__name__": "dbc_log_e2e"}
    exec(compile(code, "generated_e2e.py", "exec"), ns)
    return ns["parse_field"]


def main() -> int:
    check("DBC fixture exists", os.path.isfile(DBC_PATH), DBC_PATH)
    check("log fixture exists", os.path.isfile(LOG_PATH), LOG_PATH)
    if _failures:
        return 1

    with open(DBC_PATH, encoding="utf-8") as fh:
        dbc_text = fh.read()
    parsed = parse_dbc(dbc_text)
    by_can_id = {m["can_id"]: m for m in parsed["messages"]}
    frames = read_log(LOG_PATH)
    check("log parsed into frames", len(frames) == 7, str(len(frames)))

    detail, specs = load_specs(dbc_text)
    check("DBC import exposes 3 messages / 12 signals",
          len(detail["messages"]) == 3 and detail["signal_count"] == 12,
          str(detail["signal_count"]))
    check("every stored signal produced a ParserSpec",
          len(specs) == 12 and all(s.get("dbc_message_id") is not None for s in specs.values()),
          str(len(specs)))

    parse_field = build_generated_runtime()

    ref_db = None
    if cantools_available():
        import cantools
        ref_db = cantools.database.load_string(dbc_text, database_format="dbc")

    known = unknown = truncated = decoded_signals = agreed = cantools_matches = 0
    for frame in frames:
        msg = by_can_id.get(frame["can_id"])
        if msg is None:
            unknown += 1
            print(f"  frame {frame['time']:.3f} 0x{frame['can_id']:X}: unknown id -> skipped")
            continue
        known += 1
        hexraw = "0x" + frame["payload"].hex()
        reference = decode_message(frame["payload"], msg)

        if ref_db is not None and not any(s.get("multiplexer") for s in msg["signals"]):
            theirs = ref_db.decode_message(frame["can_id"], frame["payload"],
                                           decode_choices=False, allow_truncated=True)
            for name, value in theirs.items():
                if name in reference and reference[name] is not None:
                    check(f"cantools matches frame {frame['time']:.3f}/{name}",
                          eq(reference[name], value), f"{reference[name]} vs {value}")
                    cantools_matches += 1

        for sig in msg["signals"]:
            name = sig["name"]
            spec = specs[name]
            base = reference[name]
            runtime = ResponseParser.parse(hexraw, spec)
            try:
                generated = parse_field(
                    hexraw, "dec", sig["start"], sig["length"], "bit",
                    byte_order=spec["byte_order"], is_signed=spec["is_signed"],
                    factor=spec["factor"], offset=spec["offset"],
                )
                generated_error = None
            except (ValueError, TypeError) as exc:
                generated, generated_error = None, exc

            if base is None or len(frame["payload"]) < 2:
                # A truncated frame must be refused cleanly on all three paths.
                truncated += 1
                ok = runtime["status"] == "error" and generated_error is not None
                check(f"frame {frame['time']:.3f}/{name}: truncated frame refused cleanly",
                      ok, f"runtime={runtime['status']} generated={generated_error!r}")
                continue

            decoded_signals += 1
            ok = (eq(base, runtime["value"]) and eq(base, generated)
                  and runtime["status"] in ("ok", "fail"))
            if ok:
                agreed += 1
            else:
                check(f"frame {frame['time']:.3f}/{name}: 3-layer agreement", False,
                      f"dbc={base!r} runtime={runtime['value']!r} generated={generated!r}")
        print(f"  frame {frame['time']:.3f} 0x{frame['can_id']:X} "
              f"({msg['name']}): decoded {len(msg['signals'])} signals")

    check("known frames processed", known == 6, str(known))
    check("unknown frame skipped", unknown == 1, str(unknown))
    check("signals decoded on full frames", decoded_signals >= 20, str(decoded_signals))
    # EngineSpeed only needs 16 bit, so it still decodes on the 2-byte frame;
    # the other four EngineData signals must be refused.
    check("truncated frame signals refused cleanly", truncated == 4, str(truncated))
    check("all decoded signals agree across dbc_parser / runtime / generated script",
          agreed == decoded_signals, f"{agreed}/{decoded_signals}")
    if ref_db is not None:
        check("cantools cross-check ran", cantools_matches >= 8, str(cantools_matches))
    else:
        print("  SKIP  cantools not installed")

    print(f"\n  summary: {len(frames)} frames, {known} known, {unknown} unknown, "
          f"{decoded_signals} signal decodes, {truncated} truncated refusals, "
          f"{cantools_matches} cantools comparisons")
    if _failures:
        print(f"\nFAILED: {len(_failures)} check(s): {', '.join(_failures)}")
        return 1
    print("All DBC + log end-to-end checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
