#!/usr/bin/env python3
"""Issue #24 guards: DBC import + signal decoding end-to-end.

Uses ``fixtures/mg100_demo.dbc`` covering Intel (@1) / Motorola (@0), signed,
factor/offset, min/max, physical unit, VAL_ choice tables, CM_ comments and
multiplexer markers.

The four layers that must never diverge are all asserted here:

  1. DBC parsing (``parse_dbc``)
  2. bit-level decoding (``decode_signal`` / ``decode_message``) — cross-checked
     against cantools 39.4.5 when installed
  3. runtime parser (``ResponseParser``) with a DBC-generated spec
  4. generated Python script (``codegen_service``) — actually ``exec``-ed and
     compared numerically, not merely checked for substring presence

plus the DB / API round trip, upload encoding, error handling and boundaries.

Run: ``python3 Test/test_dbc_import_and_parse.py``
"""
import asyncio
import json
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
    decode_message_with_cantools, sawtooth_to_linear,
)
from app.services.response_parser import ResponseParser  # noqa: E402
from app.services.codegen_service import codegen_service as gen  # noqa: E402

_failures: List[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("  PASS  " if ok else "  FAIL  ") + label + (f"  -> {detail}" if detail else ""))
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
BITS = "".join(f"{b:08b}" for b in PAYLOAD)


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
    check("BO_ id exposes can_id / is_extended",
          eng["can_id"] == 256 and eng["is_extended"] is False, str(eng["can_id"]))

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
    # Standard DBC: "M" marks the multiplexer, "mN" the multiplexed signals.
    check("multiplexer markers parsed (M on selector, mN on branches)",
          names.get("MuxSelector") == "M" and names.get("SignalA") == "m0"
          and names.get("SignalB") == "m1", str(names))


def decode_checks(db) -> None:
    by_id = {m["id"]: m for m in db["messages"]}

    # Motorola expectations are calibrated against cantools 39.4.5 (the DBC
    # @0 start bit is sawtooth-numbered, NOT a linear MSB-first index).
    eng = decode_message(PAYLOAD, by_id[256])
    expect_eng = {
        "EngineSpeed": 2180.25,   # 0x2211 * 0.25
        "CoolantTemp": 11.0,      # 0x33 - 40
        "ThrottlePos": 27.2,      # 0x44 * 0.4
        "StatusFlags": 179,       # @0 start 32 -> linear 39 -> 0xB3
        "TorqueNm": 15300,        # @0 start 40 -> linear 47 -> 0x3BC4
    }
    for name, want in expect_eng.items():
        check(f"decode {name} == {want}", eq(eng[name], want), str(eng[name]))

    batt = decode_message(PAYLOAD, by_id[257])
    expect_batt = {
        "Voltage": 87.21,        # 0x2211 * 0.01
        "Current": 1745.9,       # 0x4433 * 0.1 (positive)
        "SOC": 42.5,             # 0x55 * 0.5
        "CellTemp": 55.6,        # @0 12-bit raw 956 * 0.1 - 40
    }
    for name, want in expect_batt.items():
        check(f"decode {name} == {want}", eq(batt[name], want), str(batt[name]))


def start_bit_checks() -> None:
    check("motorola start bit converts sawtooth -> linear",
          dbc_start_to_linear(40, 16, "motorola") == 47
          and dbc_start_to_linear(32, 8, "big_endian") == 39
          and sawtooth_to_linear(40) == 47)
    check("intel start bit converts LSB -> MSB",
          dbc_start_to_linear(0, 16, "intel") == 8
          and dbc_start_to_linear(16, 8, "intel") == 16)
    check("byte order normalisation",
          normalize_byte_order("intel") == "little_endian"
          and normalize_byte_order("motorola") == "big_endian"
          and normalize_byte_order("0") == "big_endian"
          and normalize_byte_order("1") == "little_endian"
          and normalize_byte_order(" auto ") == "little_endian")

    lin = dbc_start_to_linear(40, 16, "motorola")
    legacy = int(BITS[lin:lin + 16], 2)
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

    # Both signal dict shapes must map identically (raw parse_dbc output uses
    # `unit` + List[Tuple]; the DB/API shape uses `physical_unit` + List[dict]).
    stored_shape = {
        **speed, "physical_unit": speed["unit"], "unit": None,
        "choices": [{"value": 0, "text": "Empty"}, {"value": 100, "text": "Full"}],
    }
    stored_spec = signal_to_parser_spec(stored_shape, message_id=256)
    check("stored-shape spec keeps physical unit",
          stored_spec.get("physical_unit") == "rpm", str(stored_spec.get("physical_unit")))
    check("stored-shape spec keeps VAL_ choices verbatim",
          stored_spec.get("choices") == [
              {"value": 0, "text": "Empty"}, {"value": 100, "text": "Full"}],
          str(stored_spec.get("choices")))
    raw_shape = signal_to_parser_spec(
        {**speed, "choices": [(0, "Empty"), (100, "Full")]}, message_id=256)
    check("tuple and dict choices normalise identically",
          raw_shape["choices"] == stored_spec["choices"], str(raw_shape["choices"]))

    # Extended-frame DBC ids carry bit 31; ParserSpec must expose the real id.
    ext_spec = signal_to_parser_spec(speed, message_id=0x80000100)
    check("extended frame id is masked in ParserSpec",
          ext_spec["dbc_message_id"] == 0x100 and ext_spec.get("dbc_is_extended") is True,
          str(ext_spec["dbc_message_id"]))

    parsed = ResponseParser.parse("0x1122334455667788", spec)
    check("runtime parser decodes DBC signal",
          eq(parsed["value"], 2180.25) and parsed["ok"] is True,
          f"{parsed['value']} / {parsed['detail']}")

    bad = dict(spec, name="EngineSpeedBad")
    parsed_short = ResponseParser.parse("0xFF", bad)
    check("runtime parser flags a too-short payload",
          parsed_short["status"] == "error", parsed_short["detail"])
    parsed_oor = ResponseParser.parse("0xFFFF", bad)
    check("runtime parser flags an out-of-range value as FAIL",
          parsed_oor["status"] == "fail" and "超出最大值" in parsed_oor["detail"],
          parsed_oor["detail"])

    # A float-valued DBC signal must not crash when the UI sets data_type=string.
    as_string = ResponseParser.parse("0x1122334455667788", dict(spec, data_type="string"))
    check("float signal with data_type=string does not raise",
          as_string.get("value") == "2180.25" and as_string.get("status") == "ok",
          str(as_string.get("value")))


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

    # Executing the generated script (not just grepping its text) is the only
    # way to catch a divergence between the runtime and generated decoders.
    ns = {"__name__": "dbc_guard"}
    try:
        exec(compile(code, "generated_dbc.py", "exec"), ns)
    except Exception as exc:
        check("generated script executes", False, f"{type(exc).__name__}: {exc}")
        return
    check("generated script executes", "parse_field" in ns, "")

    cases = [
        {"byte_order": "intel", "start": 0, "length": 16, "factor": 0.25, "offset": 0.0},
        {"byte_order": "motorola", "start": 40, "length": 16, "factor": 1.0, "offset": 0.0},
        {"byte_order": "big_endian", "start": 32, "length": 8, "factor": 1.0, "offset": 0.0},
        {"byte_order": "motorola", "start": 40, "length": 12, "factor": 0.1, "offset": -40.0},
        # Unknown byte order and string factor used to diverge / crash.
        {"byte_order": "auto", "start": 0, "length": 16, "factor": 0.25, "offset": 0.0},
        {"byte_order": " intel ", "start": 0, "length": 16, "factor": "0.25", "offset": 0.0},
        {"byte_order": "motorola", "start": 40, "length": 16, "factor": float("nan"), "offset": 0.0},
    ]
    for c in cases:
        runtime_spec = {"name": "x", "data_type": "dec", "unit": "bit", **c}
        runtime = ResponseParser.parse("0x1122334455667788", runtime_spec)
        try:
            generated = ns["parse_field"](
                "0x1122334455667788", "dec", c["start"], c["length"], "bit",
                byte_order=c["byte_order"], factor=c["factor"], offset=c["offset"],
            )
        except Exception as exc:
            check(f"generated == runtime ({c['byte_order']}, {c['factor']!r})", False,
                  f"{type(exc).__name__}: {exc}")
            continue
        check(f"generated == runtime ({c['byte_order']}, {c['factor']!r})",
              eq(generated, runtime["value"]) or (generated is None and runtime["status"] == "error"),
              f"generated={generated!r} runtime={runtime['value']!r}/{runtime['status']}")

    check("generated dbc_start_to_linear matches dbc_parser",
          ns["dbc_start_to_linear"](40, 16, "motorola") == dbc_start_to_linear(40, 16, "motorola")
          and ns["dbc_start_to_linear"](0, 16, "intel") == dbc_start_to_linear(0, 16, "intel"))


def db_round_trip_checks() -> None:
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker
    from app.core.database import Base
    from app.services.dbc_service import dbc_service

    async def run():
        with tempfile.TemporaryDirectory() as td:
            engine = create_async_engine(f"sqlite+aiosqlite:///{td}/dbc.db")
            try:
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
                    check("message detail exposes can_id / is_extended",
                          data["messages"][0]["can_id"] == 256
                          and data["messages"][0]["is_extended"] is False)

                    hits = await dbc_service.search(db, r1["id"], "voltage")
                    check("search finds signals case-insensitively",
                          any(h.get("name") == "Voltage" for h in hits), str(hits))

                    sig_ids = {}
                    for m in data["messages"]:
                        for s in m["signals"]:
                            sig_ids[s["name"]] = s["id"]

                    spec = await dbc_service.signal_parser_spec(db, sig_ids["EngineSpeed"])
                    check("stored signal -> ParserSpec keeps physical unit",
                          spec["physical_unit"] == "rpm", str(spec.get("physical_unit")))
                    check("stored signal -> ParserSpec keeps choices",
                          (await dbc_service.signal_parser_spec(db, sig_ids["SOC"]))["choices"]
                          == [{"value": 0, "text": "Empty"}, {"value": 100, "text": "Full"}],
                          str((await dbc_service.signal_parser_spec(db, sig_ids["SOC"]))["choices"]))
                    check("stored signal -> ParserSpec byte order/factor",
                          spec["byte_order"] == "intel" and spec["factor"] == 0.25,
                          str(spec))

                    sig = await dbc_service.get_signal(db, sig_ids["EngineSpeed"])
                    val = dbc_service.preview_decode(sig, PAYLOAD)
                    check("service preview decode matches hand value", eq(val, 2180.25), str(val))

                    # A failed import must roll back and leave the session usable.
                    huge = ('BO_ 999999999999999999999 Big: 8 ECU\n'
                            ' SG_ S : 0|8@1+ (1,0) [0|255] "" ECU\n')
                    try:
                        await dbc_service.import_dbc(db, huge, "huge.dbc")
                        failed = False
                    except Exception:
                        failed = True
                    check("oversized DBC id raises (and rolls back)", failed, "")
                    after = await dbc_service.list_files(db)
                    check("session usable after failed import", len(after) == 1, str(len(after)))
            finally:
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
            client = TestClient(app, raise_server_exceptions=False)

            # HEAD is a standard liveness probe; @app.get regressed to 405.
            for path in ("/api/health", "/api/system/diag", "/api/system/drivers", "/"):
                check(f"HEAD {path} -> 200", client.head(path).status_code == 200)

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
            check("404 for unknown file",
                  client.get("/api/dbc/files/nope").status_code == 404)

            search = client.get(f"/api/dbc/files/{file_id}/search", params={"q": "speed"})
            check("search endpoint returns matches",
                  search.status_code == 200 and any("Speed" in h["name"] for h in search.json()))

            sig_id = None
            msg_id = None
            for m in detail.json()["messages"]:
                if m["name"] == "EngineData":
                    msg_id = m["id"]
                for s in m["signals"]:
                    if s["name"] == "EngineSpeed":
                        sig_id = s["id"]
            check("GET /api/dbc/messages/{id}",
                  client.get(f"/api/dbc/messages/{msg_id}").status_code == 200)
            check("GET /api/dbc/signals/{id}",
                  client.get(f"/api/dbc/signals/{sig_id}").status_code == 200)

            spec = client.post(f"/api/dbc/signals/{sig_id}/parser-spec")
            check("POST /api/dbc/signals/{id}/parser-spec keeps unit",
                  spec.status_code == 200 and spec.json()["byte_order"] == "intel"
                  and spec.json().get("physical_unit") == "rpm", str(spec.json()))

            preview = client.post("/api/dbc/preview", json={
                "byte_order": "intel", "start": 0, "length": 16,
                "is_signed": False, "factor": 0.25, "offset": 0.0,
                "payload_hex": "1122334455667788",
            })
            check("POST /api/dbc/preview decodes correctly",
                  preview.status_code == 200 and eq(preview.json()["value"], 2180.25),
                  str(preview.json()))

            motorola = client.post("/api/dbc/preview", json={
                "byte_order": "motorola", "start": 40, "length": 16,
                "payload_hex": "0x11 22 33 44 55 66 77 88",
            })
            check("preview accepts 0x/spaced hex and decodes Motorola via cantools rule",
                  motorola.status_code == 200 and eq(motorola.json()["value"], 15300),
                  str(motorola.json()))

            for label, body in (
                ("NaN factor", {"factor": 1e400, "payload_hex": "1122334455667788", "length": 16}),
                ("odd hex", {"payload_hex": "112", "length": 8}),
                ("invalid hex", {"payload_hex": "zzzz", "length": 8}),
                ("out-of-range geometry", {"payload_hex": "1122", "start": 0, "length": 64}),
            ):
                resp = client.post("/api/dbc/preview", json=body)
                check(f"preview rejects {label} with 400", resp.status_code == 400,
                      f"{resp.status_code} {resp.text[:100]}")

            gbk = ('VERSION ""\nBU_: ECU\nBO_ 101 Msg: 1 ECU\n'
                   ' SG_ S : 0|8@1+ (1,0) [0|255] "" ECU\nCM_ BO_ 101 "发动机数据";\n')
            up = client.post("/api/dbc/upload",
                             files={"file": ("gbk.dbc", gbk.encode("gbk"),
                                             "application/octet-stream")})
            ok_gbk = up.status_code == 200 and up.json().get("encoding") == "gbk"
            if ok_gbk:
                got = client.get(f"/api/dbc/files/{up.json()['id']}").json()
                ok_gbk = got["messages"][0]["comment"] == "发动机数据"
            check("upload decodes GBK comment instead of replacing with U+FFFD", ok_gbk,
                  str(up.json())[:140])

            too_big = client.post("/api/dbc/import", json={
                "filename": "big.dbc", "content": " " * (5 * 1024 * 1024 + 1)})
            check("oversized import rejected with 413", too_big.status_code == 413,
                  str(too_big.status_code))

            huge = ('BO_ 999999999999999999999 Big: 8 ECU\n'
                    ' SG_ S : 0|8@1+ (1,0) [0|255] "" ECU\n')
            bad = client.post("/api/dbc/import", json={"filename": "huge.dbc", "content": huge})
            check("oversized DBC id rejected with 400 (not 500)", bad.status_code == 400,
                  f"{bad.status_code} {bad.text[:120]}")
            check("DB still usable after failed import",
                  client.get("/api/dbc/files").status_code == 200)
        finally:
            app.dependency_overrides.pop(get_db, None)
            asyncio.run(engine.dispose())


def edge_case_checks() -> None:
    for label, text in (("empty", ""), ("whitespace", "  \n \t"), ("no BO_", "VERSION \"\"\n")):
        try:
            parse_dbc(text)
            rejected = False
        except ValueError:
            rejected = True
        check(f"parse_dbc rejects {label} file", rejected, "")

    check("decode_signal rejects length=0 / negative start / huge length",
          decode_signal(PAYLOAD, 0, 0) is None
          and decode_signal(PAYLOAD, -1, 8) is None
          and decode_signal(PAYLOAD, 0, 1000) is None)
    check("decode_signal rejects non-finite factor/offset safely",
          decode_signal(PAYLOAD, 0, 16, factor=float("nan")) == 8721
          and decode_signal(PAYLOAD, 0, 16, offset=float("inf")) == 8721)

    weird = ('BO_ 300 Weird: 8 ECU\n SG_ W : 0|8@1+ (nan,inf) [nan|1e400] "" ECU\n')
    sig = parse_dbc(weird)["messages"][0]["signals"][0]
    spec = signal_to_parser_spec(sig, message_id=300)
    check("illegal factor/offset/min/max never reach a ParserSpec",
          spec["factor"] == 1.0 and spec["offset"] == 0.0
          and "conditions" not in spec, str(spec))

    dup = ('BO_ 100 A: 8 ECU\n SG_ S1 : 0|8@1+ (1,0) [0|255] "" ECU\n'
           'BO_ 100 B: 8 ECU\n SG_ S2 : 0|8@1+ (1,0) [0|255] "" ECU\n'
           'CM_ BO_ 100 "shared";\nVAL_ 100 S1 0 "Off" 1 "On" ;\n')
    parsed = parse_dbc(dup)
    check("duplicate BO_ id keeps CM_ on every frame",
          all(m["comment"] == "shared" for m in parsed["messages"]),
          str([m["comment"] for m in parsed["messages"]]))
    check("duplicate BO_ id keeps VAL_ on the matching signal",
          parsed["messages"][0]["signals"][0]["choices"] == [(0, "Off"), (1, "On")],
          str(parsed["messages"][0]["signals"][0]["choices"]))

    hexval = parse_dbc('BO_ 400 HexVal: 1 ECU\n SG_ H : 0|8@1+ (1,0) [0|255] "" ECU\n'
                       'VAL_ 400 H 0x10 "Sixteen" 1 "One" ;\n')
    check("VAL_ accepts 0x-prefixed values",
          hexval["messages"][0]["signals"][0]["choices"] == [(16, "Sixteen"), (1, "One")],
          str(hexval["messages"][0]["signals"][0]["choices"]))

    ext = parse_dbc('BO_ 2147483904 ExtMsg: 8 ECU\n SG_ S : 0|8@1+ (1,0) [0|255] "" ECU\n')
    check("extended frame id exposes masked can_id",
          ext["messages"][0]["id"] == 0x80000100
          and ext["messages"][0]["can_id"] == 0x100
          and ext["messages"][0]["is_extended"] is True,
          str(ext["messages"][0]["can_id"]))

    ok_nan, detail_nan = ResponseParser.evaluate(float("nan"), {"min": 0, "max": 10})
    check("NaN value cannot bypass a range judgement",
          ok_nan is False and "有限数值" in detail_nan, str(detail_nan))


def cantools_cross_check() -> None:
    if not cantools_available():
        print("  SKIP  cantools not installed (offline); internal vectors are hand-computed")
        return
    import cantools
    db = parse_dbc(DBC_TEXT)
    try:
        ref = cantools.database.load_string(DBC_TEXT, database_format="dbc")
    except Exception as exc:
        check("cantools can load the fixture DBC", False, f"{type(exc).__name__}: {exc}")
        return
    check("cantools can load the fixture DBC", len(ref.messages) == 3,
          str([m.name for m in ref.messages]))

    for msg in db["messages"]:
        if any(sig.get("multiplexer") for sig in msg["signals"]):
            # A multiplexed frame needs a payload whose selector byte equals
            # one of the mN ids; our generic test payload (0x11) is not one.
            print(f"  SKIP  cantools mux frame {msg['name']} (no mux-selector payload)")
            continue
        ours = decode_message(PAYLOAD, msg)
        try:
            theirs = decode_message_with_cantools(DBC_TEXT, PAYLOAD, msg["name"])
        except Exception as exc:
            check(f"cantools decodes {msg['name']}", False, f"{type(exc).__name__}: {exc}")
            continue
        for sig in msg["signals"]:
            name = sig["name"]
            if name not in theirs:
                continue
            check(f"cantools agrees on {name}",
                  eq(ours[name], theirs[name]),
                  f"{ours[name]} vs {theirs[name]}")


def main() -> int:
    db = parse_dbc(DBC_TEXT)
    parse_checks(db)
    decode_checks(db)
    start_bit_checks()
    spec_checks()
    codegen_checks()
    db_round_trip_checks()
    api_checks()
    edge_case_checks()
    cantools_cross_check()
    if _failures:
        print(f"\nFAILED: {len(_failures)} check(s): {', '.join(_failures)}")
        return 1
    print("\nAll DBC import + parse guards passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
