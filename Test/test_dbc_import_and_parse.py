#!/usr/bin/env python3
"""Issue #24 guards: DBC import + signal decoding end-to-end.

Uses a self-built DBC fixture (``fixtures/mg100_demo.dbc``) covering:

  * Intel (@1) and Motorola (@0) byte order
  * signed / unsigned, factor / offset, min / max, physical unit
  * ``VAL_`` choice tables, ``CM_`` comments, multiplexer markers

Assertions span the four layers the issue demands must never diverge:

  1. DBC parsing (``parse_dbc``)
  2. bit-level decoding (``decode_signal`` / ``decode_message``) against
     hand-computed vectors — cross-checked with ``cantools`` when installed
  3. the runtime parser (``ResponseParser``) with a DBC-generated spec
  4. the generated Python script (``codegen_service``)

plus the DB/API round trip (import -> browse -> signal -> ParserSpec).

Run: ``python3 Test/test_dbc_import_and_parse.py``
"""
import asyncio
import math
import os
import sys
import tempfile
from typing import List

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
BACKEND = os.path.join(ROOT, "backend")
sys.path.insert(0, BACKEND)

from app.services.dbc_parser import (  # noqa: E402
    parse_dbc, decode_signal, decode_message, signal_to_parser_spec,
    dbc_start_to_linear, normalize_byte_order, cantools_available,
)
from app.services.response_parser import ResponseParser  # noqa: E402
from app.services.codegen_service import codegen_service as gen  # noqa: E402

_failures: List[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("  PASS  " if ok else "  FAIL  ") + label + (f"  -> {detail}"))
    if not ok:
        _failures.append(label)


def eq(a, b) -> bool:
    """Numeric comparison tolerant of IEEE-754 factor/offset rounding."""
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return math.isclose(float(a), float(b), rel_tol=1e-9, abs_tol=1e-9)
    return a == b


FIXTURE = os.path.join(HERE, "fixtures", "mg100_demo.dbc")
with open(FIXTURE, encoding="utf-8") as fh:
    DBC_TEXT = fh.read()

PAYLOAD = bytes.fromhex("1122334455667788")


def N(i, t, cfg=None, label=""):
    return {"id": i, "type": t, "data": {"label": label or i}, "config": cfg or {}}


def parse_checks(db) -> None:
    messages = db["messages"]
    by_id = {m["id"]: m for m in messages}
    check("parsed 3 messages", len(messages) == 3, str(len(messages)))
    check("nodes extracted", "MG100" in db["nodes"] and "PCAN" in db["nodes"],
          str(db["nodes"]))

    eng = by_id[256]
    check("message 256 has 5 signals", len(eng["signals"]) == 5,
          str(len(eng["signals"])))

    speed = next(s for s in eng["signals"] if s["name"] == "EngineSpeed")
    check("EngineSpeed: intel/unsigned/factor/unit",
          speed["byte_order"] == "little_endian" and not speed["is_signed"]
          and speed["factor"] == 0.25 and speed["unit"] == "rpm"
          and speed["min"] == 0 and speed["max"] == 16000, str(speed))

    torque = next(s for s in eng["signals"] if s["name"] == "TorqueNm")
    check("TorqueNm: motorola/signed",
          torque["byte_order"] == "big_endian" and torque["is_signed"]
          and torque["min"] == -500 and torque["max"] == 500, str(torque))

    eng_comment = eng["comment"]
    check("BO_ comment parsed", "Engine data frame" in eng_comment, eng_comment)
    flags = next(s for s in eng["signals"] if s["name"] == "StatusFlags")
    check("SG_ comment parsed", "Bitfield" in flags["comment"], flags["comment"])

    batt = by_id[257]
    soc = next(s for s in batt["signals"] if s["name"] == "SOC")
    check("VAL_ choice table parsed",
          soc["choices"] == [(0, "Empty"), (100, "Full")], str(soc["choices"]))

    mux = by_id[258]
    names = {s["name"]: s["multiplexer"] for s in mux["signals"]}
    check("multiplexer markers parsed",
          names.get("MuxSelector") == "m0" and names.get("SignalA") == "M"
          and names.get("SignalB") == "m1", str(names))


def decode_checks(db) -> None:
    by_id = {m["id"]: m for m in db["messages"]}

    eng = decode_message(PAYLOAD, by_id[256])
    expect_eng = {
        "EngineSpeed": 2180.25,   # 0x2211 * 0.25
        "CoolantTemp": 11.0,      # 0x33 - 40
        "ThrottlePos": 27.2,      # 0x44 * 0.4
        "StatusFlags": 85,        # motorola byte4 = 0x55
        "TorqueNm": 26231,        # motorola bytes5-6 = 0x6677
    }
    for name, want in expect_eng.items():
        check(f"decode {name} == {want}", eq(eng[name], want), str(eng[name]))

    batt = decode_message(PAYLOAD, by_id[257])
    expect_batt = {
        "Voltage": 87.21,        # 0x2211 * 0.01
        "Current": 1745.9,       # 0x4433 * 0.1 (positive)
        "SOC": 42.5,             # 0x55 * 0.5
        "CellTemp": 123.9,       # motorola 12-bit 0x667 * 0.1 - 40
    }
    for name, want in expect_batt.items():
        check(f"decode {name} == {want}", eq(batt[name], want), str(batt[name]))


def start_bit_checks() -> None:
    check("motorola start bit is already linear (identity)",
          dbc_start_to_linear(40, 16, "motorola") == 40
          and dbc_start_to_linear(32, 8, "big_endian") == 32)
    check("intel start bit converts LSB -> MSB",
          dbc_start_to_linear(0, 16, "intel") == 8
          and dbc_start_to_linear(16, 8, "intel") == 16)
    check("byte order normalisation",
          normalize_byte_order("intel") == "little_endian"
          and normalize_byte_order("motorola") == "big_endian"
          and normalize_byte_order("0") == "big_endian"
          and normalize_byte_order("1") == "little_endian")

    # Round trip: the linear MSB-first index must let the legacy bit slicer
    # reproduce the Motorola decode exactly.
    bits = "".join(f"{b:08b}" for b in PAYLOAD)
    lin = dbc_start_to_linear(40, 16, "motorola")
    legacy = int(bits[lin:lin + 16], 2)
    check("motorola legacy slicer matches decode_signal",
          legacy == decode_signal(PAYLOAD, 40, 16, "motorola"), str(legacy))


def spec_checks() -> None:
    by_id = {m["id"]: m for m in parse_dbc(DBC_TEXT)["messages"]}
    speed = next(s for s in by_id[256]["signals"] if s["name"] == "EngineSpeed")
    spec = signal_to_parser_spec(speed, message_id=256)
    check("spec maps byte_order -> intel",
          spec["byte_order"] == "intel" and spec["data_type"] == "dec"
          and spec["unit"] == "bit", str(spec["byte_order"]))
    check("spec carries factor/offset/signed/unit",
          spec["factor"] == 0.25 and spec["offset"] == 0.0
          and spec["is_signed"] is False and spec["physical_unit"] == "rpm",
          str((spec["factor"], spec["offset"], spec["physical_unit"])))
    check("spec carries min/max conditions",
          spec["conditions"] == {"min": 0, "max": 16000}, str(spec["conditions"]))

    # Runtime engine must decode a DBC spec to the same physical value.
    parsed = ResponseParser.parse("0x1122334455667788", spec)
    check("runtime parser decodes DBC signal",
          eq(parsed["value"], 2180.25) and parsed["ok"] is True,
          f"{parsed['value']} / {parsed['detail']}")

    # A too-short payload is an error, an out-of-range value is a FAIL.
    bad = dict(spec, name="EngineSpeedBad")
    parsed_short = ResponseParser.parse("0xFF", bad)
    check("runtime parser flags a too-short payload",
          parsed_short["status"] == "error", parsed_short["detail"])
    parsed_oor = ResponseParser.parse("0xFFFF", bad)
    check("runtime parser flags an out-of-range value as FAIL",
          parsed_oor["status"] == "fail" and "超出最大值" in parsed_oor["detail"],
          parsed_oor["detail"])


def codegen_checks() -> None:
    spec = {
        "name": "EngineSpeed", "data_type": "dec", "start": 0, "length": 16,
        "unit": "bit", "byte_order": "intel", "is_signed": False,
        "factor": 0.25, "offset": 0.0,
    }
    nodes = [
        N("s", "start"),
        N("a1", "action", {"command": "@11_READ;", "parsers": [spec]}, "读取"),
        N("e", "end"),
    ]
    edges = [{"source": "s", "target": "a1"}, {"source": "a1", "target": "e"}]
    code = gen.generate_python(nodes, edges, "DbcTest")
    check("generated code defines the DBC decoder",
          "_decode_signal" in code and "dbc_start_to_linear" in code)
    check("generated call passes byte_order/factor/offset",
          "byte_order='intel'" in code and "factor=0.25" in code
          and "offset=0.0" in code)
    check("generated code compiles", compile(code, "generated_dbc.py", "exec") is not None)


def db_round_trip_checks() -> None:
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker
    from app.core.database import Base
    from app.services.dbc_service import dbc_service

    async def run():
        with tempfile.TemporaryDirectory() as td:
            engine = create_async_engine(f"sqlite+aiosqlite:///{td}/dbc.db")
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

            async with Session() as db:
                r1 = await dbc_service.import_dbc(db, DBC_TEXT, "mg100_demo.dbc")
                r2 = await dbc_service.import_dbc(db, DBC_TEXT, "mg100_demo.dbc")
                check("import returns a file id", bool(r1["id"]) and not r1["duplicate"])
                check("duplicate import is de-duplicated by content hash",
                      r2["duplicate"] is True and r2["id"] == r1["id"])

                files = await dbc_service.list_files(db)
                check("imported file is listed",
                      len(files) == 1 and files[0]["message_count"] == 3
                      and files[0]["signal_count"] == 12, str(files[0]))

                data = await dbc_service.get_file(db, r1["id"])
                check("file detail exposes messages + signals",
                      len(data["messages"]) == 3
                      and len(data["messages"][0]["signals"]) == 5)

                hits = await dbc_service.search(db, r1["id"], "voltage")
                check("search finds signals case-insensitively",
                      any(h.get("name") == "Voltage" for h in hits), str(hits))

                sig_id = None
                for m in data["messages"]:
                    for s in m["signals"]:
                        if s["name"] == "EngineSpeed":
                            sig_id = s["id"]
                spec = await dbc_service.signal_parser_spec(db, sig_id)
                check("stored signal -> ParserSpec",
                      spec["byte_order"] == "intel" and spec["factor"] == 0.25,
                      str(spec))

                # preview decode through the service reuses dbc_parser
                sig = await dbc_service.get_signal(db, sig_id)
                val = dbc_service.preview_decode(sig, PAYLOAD)
                check("service preview decode matches hand value", eq(val, 2180.25), str(val))
            await engine.dispose()

    asyncio.run(run())


def api_checks() -> None:
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker
    from fastapi.testclient import TestClient
    from app.core.database import Base, get_db
    from app.main import app

    with tempfile.TemporaryDirectory() as td:
        engine = create_async_engine(f"sqlite+aiosqlite:///{td}/api.db")
        Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        async def prepare():
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
        asyncio.run(prepare())

        async def override_get_db():
            async with Session() as session:
                yield session

        app.dependency_overrides[get_db] = override_get_db
        try:
            client = TestClient(app)
            r = client.post("/api/dbc/import",
                            json={"filename": "mg100_demo.dbc", "content": DBC_TEXT})
            check("POST /api/dbc/import succeeds", r.status_code == 200, str(r.status_code))
            file_id = r.json().get("id")
            check("import returned an id", bool(file_id), str(r.json()))

            files = client.get("/api/dbc/files")
            check("GET /api/dbc/files lists the import",
                  files.status_code == 200 and len(files.json()) == 1)

            detail = client.get(f"/api/dbc/files/{file_id}")
            check("GET /api/dbc/files/{id} returns messages",
                  detail.status_code == 200 and len(detail.json()["messages"]) == 3)

            search = client.get(f"/api/dbc/files/{file_id}/search", params={"q": "speed"})
            check("search endpoint returns matches",
                  search.status_code == 200 and any("Speed" in h["name"] for h in search.json()))

            sig_id = None
            for m in detail.json()["messages"]:
                for s in m["signals"]:
                    if s["name"] == "EngineSpeed":
                        sig_id = s["id"]
            spec = client.post(f"/api/dbc/signals/{sig_id}/parser-spec")
            check("POST /api/dbc/signals/{id}/parser-spec",
                  spec.status_code == 200 and spec.json()["byte_order"] == "intel",
                  str(spec.json()))

            preview = client.post("/api/dbc/preview", json={
                "byte_order": "intel", "start": 0, "length": 16,
                "is_signed": False, "factor": 0.25, "offset": 0.0,
                "payload_hex": "1122334455667788",
            })
            check("POST /api/dbc/preview decodes correctly",
                  preview.status_code == 200 and eq(preview.json()["value"], 2180.25),
                  str(preview.json()))
        finally:
            app.dependency_overrides.pop(get_db, None)
            asyncio.run(engine.dispose())


def cantools_cross_check() -> None:
    if not cantools_available():
        print("  SKIP  cantools not installed (offline); internal vectors are hand-computed")
        return
    from app.services.dbc_parser import decode_message_with_cantools
    db = parse_dbc(DBC_TEXT)
    by_id = {m["id"]: m for m in db["messages"]}
    for msg in by_id.values():
        ours = decode_message(PAYLOAD, msg)
        theirs = decode_message_with_cantools(DBC_TEXT, PAYLOAD, msg["name"])
        for name in msg["signals"]:
            check(f"cantools agrees on {name['name']}",
                  eq(ours[name["name"]], theirs[name["name"]]),
                  f"{ours[name['name']]} vs {theirs[name['name']]}")


def main() -> int:
    db = parse_dbc(DBC_TEXT)
    parse_checks(db)
    decode_checks(db)
    start_bit_checks()
    spec_checks()
    codegen_checks()
    db_round_trip_checks()
    api_checks()
    cantools_cross_check()
    if _failures:
        print(f"\nFAILED: {len(_failures)} check(s): {', '.join(_failures)}")
        return 1
    print("\nAll DBC import + parse guards passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
