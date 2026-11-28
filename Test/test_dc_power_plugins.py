#!/usr/bin/env python3
"""Regression guards for the four programmable DC power supply plugins.

Run: python Test/test_dc_power_plugins.py

Covers the things that silently broke plugins before: a hard-coded /dev/ port
default, a missing transport binding (LAN unreachable from the UI), a command
error being classified as a transport error (device kicked offline), and two
copies of a command dialect drifting apart. Both transports are exercised with
fakes; no hardware is required.
"""
import asyncio
import collections
import importlib.util
import inspect
import os
import re
import sys
import types
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from app.core.interfaces import (  # noqa: E402
    PLUGIN_TRANSPORT_BINDINGS, PLUGIN_POLLUTION_TARGETS, STANDARD_PROTOCOLS,
    apply_plugin_transport, column_from_config, all_interface_field_keys,
)
from app.services.plugin_service import (  # noqa: E402
    BaseProtocolPlugin, PluginService,
)
from app.services.device_service import _is_transport_error  # noqa: E402

_failures = []
_passes = 0


def check(label, ok, detail=""):
    global _passes
    if ok:
        _passes += 1
        print("  PASS  " + label)
    else:
        _failures.append(label)
        print("  FAIL  " + label + (f"  -> {detail}" if detail else ""))


PLUGIN_FILES = {
    "itech_dc_power": "itech_dc_power_plugin.py",
    "tdk_lambda_dc_power": "tdk_lambda_dc_power_plugin.py",
    "chroma_dc_power": "chroma_dc_power_plugin.py",
    "keysight_dc_power": "keysight_dc_power_plugin.py",
}


def load_plugins():
    out = {}
    for protocol, filename in PLUGIN_FILES.items():
        path = BACKEND / "plugins" / filename
        spec = importlib.util.spec_from_file_location(protocol + "_under_test", str(path))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        classes = [
            c for c in vars(module).values()
            if inspect.isclass(c) and issubclass(c, BaseProtocolPlugin)
            and c is not BaseProtocolPlugin
        ]
        out[protocol] = (path, module, classes)
    return out


# --------------------------------------------------------------------------- #
# fakes
# --------------------------------------------------------------------------- #
class FakeSerial:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.writes = []
        self.lines = collections.deque()
        self.timeout = kwargs.get("timeout", 2.0)
        self.closed = False

    def write(self, data):
        self.writes.append(bytes(data))
        return len(data)

    def readline(self):
        return self.lines.popleft() if self.lines else b""

    def reset_input_buffer(self):
        return None

    def close(self):
        self.closed = True


def fake_serial_module(holder):
    mod = types.ModuleType("serial")
    mod.PARITY_NONE, mod.PARITY_EVEN, mod.PARITY_ODD = "N", "E", "O"
    mod.STOPBITS_ONE, mod.STOPBITS_ONE_POINT_FIVE, mod.STOPBITS_TWO = 1, 1.5, 2
    mod.EIGHTBITS = 8

    def factory(**kwargs):
        obj = FakeSerial(**kwargs)
        holder.append(obj)
        return obj

    mod.Serial = factory
    return mod


class FakeReader:
    def __init__(self, lines=()):
        self.lines = collections.deque(lines)

    async def read(self, _n):
        return b""

    async def readline(self):
        return self.lines.popleft() if self.lines else b""


class FakeWriter:
    def __init__(self):
        self.writes = []
        self.closed = False

    def write(self, data):
        self.writes.append(bytes(data))

    async def drain(self):
        return None

    def close(self):
        self.closed = True

    async def wait_closed(self):
        return None


def run(coro):
    return asyncio.run(coro)


# --------------------------------------------------------------------------- #
# checks
# --------------------------------------------------------------------------- #
def verify_metadata(plugins):
    protocols = list(plugins)
    check("four plugin files discovered", len(protocols) == 4, str(protocols))
    check("protocol names are unique", len(set(protocols)) == 4)
    for protocol, (path, _module, classes) in plugins.items():
        check(f"{protocol}: exactly one plugin class", len(classes) == 1,
              str([c.__name__ for c in classes]))
        if len(classes) != 1:
            continue
        cls = classes[0]
        inst = cls()
        check(f"{protocol}: class protocol matches file",
              cls.protocol_name == protocol, cls.protocol_name)
        check(f"{protocol}: not a standard protocol",
              cls.protocol_name not in STANDARD_PROTOCOLS)
        check(f"{protocol}: has both transport bindings",
              set(PLUGIN_TRANSPORT_BINDINGS.get(protocol, {})) == {"serial", "ethernet"})
        check(f"{protocol}: pollution repair target registered",
              protocol in PLUGIN_POLLUTION_TARGETS)

        schema = inst.get_config_schema()
        props = schema["properties"]
        check(f"{protocol}: port has no default", "default" not in props["port"])
        check(f"{protocol}: port has a placeholder",
              bool(props["port"].get("placeholder")))
        check(f"{protocol}: default transport is serial",
              props["transport"]["default"] == "serial")
        check(f"{protocol}: LAN port matches brand/manual",
              props["tcp_port"]["default"] == inst.DEFAULT_LAN_PORT)
        template = inst.get_device_template()
        check(f"{protocol}: template type=power_supply + legal connection_type",
              template["type"] == "power_supply" and template["connection_type"] == "serial",
              str(template)[:160])
        check(f"{protocol}: template config has no serial port default",
              "port" not in template["config"])
        cmds = {c["name"] for c in inst.get_commands()}
        check(f"{protocol}: command list covers core actions",
              {"set_voltage", "set_current", "output_on", "measure_voltage"} <= cmds,
              str(sorted(cmds)))
        check(f"{protocol}: get_status exposes transport",
              "transport" in inst.get_status())

    # Private signature keys must survive the subtractions in plugin_service,
    # otherwise a polluted device can never be repaired (issue #34).
    generic = all_interface_field_keys()
    for protocol, (_path, _module, classes) in plugins.items():
        if not classes:
            continue
        private = PluginService.plugin_private_keys(classes[0])
        exclusive = PluginService.plugin_exclusive_keys(classes[0])
        check(f"{protocol}: has private plugin signature keys",
              bool(private), str(sorted(private)))
        check(f"{protocol}: has an exclusive signature key",
              "brand_key" in exclusive and "idn_expect" in exclusive,
              str(sorted(exclusive)))
        check(f"{protocol}: signature keys are not interface fields",
              not (private & generic), str(sorted(private & generic)))


def verify_source_guards(plugins):
    for protocol, (path, _module, _classes) in plugins.items():
        source = path.read_text(encoding="utf-8")
        check(f"{protocol}: no hard-coded /dev or /tmp default",
              not re.search(r'["\']default["\']\s*:\s*["\']/(dev|tmp)/', source))
        check(f"{protocol}: imports shared transport",
              "scpi_power_transport" in source)
        check(f"{protocol}: inherits BaseProtocolPlugin",
              "BaseProtocolPlugin" in source)
    # Plugins are exec'd from disk at runtime, so PyInstaller cannot see their
    # shared transport. A packaged build without this hiddenimport silently
    # returns an empty /api/plugins/discovered (verified on v2.3.14 setup.exe).
    spec_src = (ROOT / "backend" / "aitestlab.spec").read_text(encoding="utf-8")
    check("PyInstaller spec bundles the runtime-loaded SCPI transport",
          'hiddenimports += ["app.services.scpi_power_transport"]' in spec_src)


def verify_command_dialects(plugins):
    expected = {
        "itech_dc_power": ("VOLT 12.5", "OUTP ON", "MEAS:VOLT?"),
        "tdk_lambda_dc_power": ("VOLT 12.5", "OUTP:STAT ON", "MEAS:VOLT?"),
        "chroma_dc_power": ("SOUR:VOLT 12.5", "CONF:OUTP ON", "MEAS:VOLT?"),
        "keysight_dc_power": ("VOLT 12.5", "OUTP ON", "MEAS:VOLT?"),
    }
    for protocol, (set_v, out_on, meas_v) in expected.items():
        inst = plugins[protocol][2][0]()
        check(f"{protocol}: set_voltage dialect",
              inst.format_command("set_voltage", 12.5) == set_v,
              inst.format_command("set_voltage", 12.5))
        check(f"{protocol}: output_on dialect",
              inst.format_command("output_on") == out_on,
              inst.format_command("output_on"))
        check(f"{protocol}: measure_voltage dialect",
              inst.format_command("measure_voltage") == meas_v,
              inst.format_command("measure_voltage"))
        check(f"{protocol}: dict payload renders the same command",
              inst._parse_payload({"action": "set_voltage", "value": 12.5})[0] == set_v)
        check(f"{protocol}: raw SCPI string passes through",
              inst._parse_payload(meas_v)[0] == meas_v)
        check(f"{protocol}: JSON string payload accepted",
              inst._parse_payload('{"action": "output_on"}')[0] == out_on)
        check(f"{protocol}: query detection on SCPI header",
              inst._is_query(meas_v) and not inst._is_query(set_v))

    inst = plugins["keysight_dc_power"][2][0]()
    check("Keysight multi-channel selection renders INST:SEL",
          inst.format_command("select_channel", channel="OUT2") == "INST:SEL OUT2")
    tdk = plugins["tdk_lambda_dc_power"][2][0]()
    check("TDK default LAN port is 8003 (manual)", tdk.DEFAULT_LAN_PORT == 8003)
    check("TDK default baud rate is 115200 (manual)", tdk.DEFAULT_BAUDRATE == 115200)
    keysight = plugins["keysight_dc_power"][2][0]()
    check("Keysight default LAN port is 5025 (manual)", keysight.DEFAULT_LAN_PORT == 5025)


def verify_semantic_errors(inst):
    for label, thunk in [
        ("unknown action -> ValueError", lambda: inst.format_command("no_such_action")),
        ("missing value -> ValueError", lambda: inst.format_command("set_voltage")),
        ("non-numeric value -> ValueError", lambda: inst.format_command("set_voltage", "abc")),
        ("NaN value -> ValueError", lambda: inst.format_command("set_voltage", float("nan"))),
        ("Inf value -> ValueError", lambda: inst.format_command("set_voltage", float("inf"))),
        ("empty dict -> ValueError", lambda: inst._parse_payload({})),
        ("unsupported type -> ValueError", lambda: inst._parse_payload(3.14)),
    ]:
        try:
            thunk()
            check(label, False, "no exception raised")
        except ValueError:
            check(label, True)
        except Exception as exc:
            check(label, False, f"raised {type(exc).__name__}: {exc}")
    check("ValueError is NOT a transport error",
          _is_transport_error(ValueError("bad command")) is False)
    check("ConnectionError IS a transport error",
          _is_transport_error(ConnectionError("link down")) is True)
    check("OSError IS a transport error",
          _is_transport_error(OSError("broken pipe")) is True)


def verify_transport_bindings(plugins):
    for protocol, (_path, _module, classes) in plugins.items():
        default_baud = classes[0].DEFAULT_BAUDRATE if classes else None
        binding = PLUGIN_TRANSPORT_BINDINGS.get(protocol, {}).get("serial", {})
        check(f"{protocol}: serial binding restores the manual baud rate",
              binding.get("defaults", {}).get("baudrate") == default_baud,
              f"binding={binding.get('defaults')} manual={default_baud}")
        serial_cfg = apply_plugin_transport(
            protocol, "serial",
            {"serial_port": "COM7"}, {"serial_port": "COM7"},
            {"host": "10.0.0.5", "tcp_port": 1234, "baudrate": 19200,
             "brand_key": "keep"},
        )
        check(f"{protocol}: an explicit user baud rate is never overridden",
              serial_cfg.get("baudrate") == 19200, str(serial_cfg))
        check(f"{protocol}: serial binding sets transport+port",
              serial_cfg.get("transport") == "serial" and serial_cfg.get("port") == "COM7",
              str(serial_cfg))
        check(f"{protocol}: serial binding drops LAN keys",
              "host" not in serial_cfg and "tcp_port" not in serial_cfg)
        check(f"{protocol}: serial binding keeps private keys",
              serial_cfg.get("brand_key") == "keep")
        # Ethernet strips ``baudrate`` (foreign_config_keys). Coming back to
        # serial must not fall back to the generic 115200 spec default.
        back = apply_plugin_transport(
            protocol, "serial", {"serial_port": "COM7"}, {},
            {"transport": "ethernet", "host": "10.0.0.9", "tcp_port": 8003,
             "brand_key": "keep"},
        )
        check(f"{protocol}: LAN -> serial round trip restores brand baud rate",
              back.get("baudrate") == default_baud, str(back))
        check(f"{protocol}: LAN -> serial round trip clears LAN keys",
              "host" not in back and "tcp_port" not in back)
        lan_cfg = apply_plugin_transport(
            protocol, "ethernet",
            {"ip_address": "10.0.0.9", "port": 8003}, {},
            {"transport": "serial", "port": "COM7", "baudrate": 9600, "brand_key": "keep"},
        )
        check(f"{protocol}: LAN binding sets transport+host+tcp_port",
              lan_cfg.get("transport") == "ethernet" and lan_cfg.get("host") == "10.0.0.9"
              and lan_cfg.get("tcp_port") == 8003, str(lan_cfg))
        check(f"{protocol}: LAN binding drops stale serial keys",
              "port" not in lan_cfg and "baudrate" not in lan_cfg)
        inverse = column_from_config(protocol, "ethernet")
        check(f"{protocol}: inverse binding backfills UI columns",
              inverse.get("ip_address") == "host" and inverse.get("port") == "tcp_port",
              str(inverse))


def verify_serial_io(inst):
    holder = []
    fake = fake_serial_module(holder)
    with mock.patch.dict(sys.modules, {"serial": fake}), mock.patch("os.name", "nt"):
        async def scenario():
            ok = await inst.connect({
                "transport": "serial", "port": "COM3", "baudrate": 9600,
                "probe_idn": True,
            })
            return ok

        ok = run(scenario())
        check("serial connect succeeds with faked pyserial", ok is True)
        if not holder:
            check("serial handle created", False)
            return
        ser = holder[0]
        check("serial defaults to 8N1", ser.kwargs["bytesize"] == 8
              and ser.kwargs["parity"] == "N" and ser.kwargs["stopbits"] == 1,
              str(ser.kwargs))
        # connect() probes *IDN? best-effort; a bare fake answers nothing, which
        # must NOT fail the connection.
        check("failed *IDN? probe does not break the connection", inst.get_status()["connected"])
        ser.writes.clear()
        ser.lines.append(b"12.002\n")
        result = run(inst.send("MEAS:VOLT?"))
        check("serial query returns stripped reply", result == "12.002", str(result))
        check("serial query writes command + LF",
              ser.writes == [b"MEAS:VOLT?\n"], str(ser.writes))
        ser.writes.clear()
        ack = run(inst.send({"action": "set_voltage", "value": 12}))
        check("serial set command returns OK", ack == "OK", str(ack))
        check("serial set command renders brand dialect",
              ser.writes == [inst.format_command("set_voltage", 12).encode() + b"\n"],
              str(ser.writes))
        check("receive() is non-blocking and returns None",
              run(inst.receive(0.01)) is None)
        check("disconnect closes the serial handle", run(inst.disconnect()) and ser.closed)


def verify_ui_serial_params(plugins):
    """The interface dialog writes data_bits/stop_bits; the template writes
    bytesize/stopbits. Both live in config after "配置接口", so the UI value
    must win (otherwise a 7E2 device silently connects as 8N1)."""
    for protocol, (_path, _module, classes) in plugins.items():
        if not classes:
            continue
        inst = classes[0]()
        holder = []
        with mock.patch.dict(sys.modules, {"serial": fake_serial_module(holder)}), \
             mock.patch("os.name", "nt"):
            run(inst.connect({
                "transport": "serial", "port": "COM5", "baudrate": 19200,
                "bytesize": 8, "stopbits": 1,           # template defaults
                "data_bits": 7, "stop_bits": 2, "parity": "E",  # user's UI values
                "probe_idn": False,
            }))
        if not holder:
            check(f"{protocol}: UI serial params created a handle", False)
            continue
        kw = holder[0].kwargs
        check(f"{protocol}: UI data_bits/stop_bits/parity reach pyserial",
              kw.get("bytesize") == 7 and kw.get("stopbits") == 2
              and kw.get("parity") == "E", str(kw))
        run(inst.disconnect())


def verify_lan_io(inst, port):
    reader = FakeReader([b"24.001\n"])
    writer = FakeWriter()
    opened = {}

    async def fake_open(host, tcp_port):
        opened.update(host=host, port=tcp_port)
        return reader, writer

    with mock.patch("asyncio.open_connection", fake_open):
        ok = run(inst.connect({
            "transport": "LAN", "host": "192.168.1.50",
            "probe_idn": False,
        }))
    check("LAN connect succeeds with faked socket", ok is True)
    check("LAN connect uses the brand default port",
          opened == {"host": "192.168.1.50", "port": port}, str(opened))
    reader.lines.append(b"24.001\n")
    result = run(inst.send({"action": "measure_voltage"}))
    check("LAN query returns stripped reply", result == "24.001", str(result))
    check("LAN query writes command + LF",
          writer.writes == [inst.format_command("measure_voltage").encode() + b"\n"],
          str(writer.writes))
    writer.writes.clear()
    ack = run(inst.send("VOLT 24"))
    check("LAN write returns OK", ack == "OK", str(ack))
    check("LAN write sends SCPI + LF", writer.writes == [b"VOLT 24\n"], str(writer.writes))
    check("disconnect closes the socket", run(inst.disconnect()) and writer.closed)


def verify_error_paths(inst):
    check("send before connect raises ConnectionError",
          isinstance(_catch(run, inst.send("*IDN?")), ConnectionError))
    with mock.patch.dict(sys.modules, {"serial": fake_serial_module([])}), mock.patch("os.name", "nt"):
        err = _catch(run, inst.connect({"transport": "serial", "port": "", "probe_idn": False}))
        check("missing serial port raises ConnectionError with guidance",
              isinstance(err, ConnectionError) and "串口号" in str(err), str(err))
    err = _catch(run, inst.connect({"transport": "LAN", "host": "", "probe_idn": False}))
    check("missing LAN host raises ConnectionError",
          isinstance(err, ConnectionError) and "IP" in str(err), str(err))
    err = _catch(run, inst.connect({"transport": "gibbus", "probe_idn": False}))
    check("unknown transport raises ConnectionError",
          isinstance(err, ConnectionError), str(err))


def _catch(func, *args):
    try:
        func(*args)
    except Exception as exc:  # noqa: BLE001 - test helper
        return exc
    return None


def verify_assets(plugins):
    for protocol in plugins:
        manual = BACKEND / "plugins/manuals" / f"{protocol}.md"
        skill = BACKEND / "plugins/skills" / f"{protocol}_skill.md"
        check(f"{protocol}: manual exists", manual.is_file(), str(manual))
        check(f"{protocol}: skill exists", skill.is_file(), str(skill))
        if manual.is_file():
            head = manual.read_text(encoding="utf-8")[:400]
            check(f"{protocol}: manual frontmatter protocol matches",
                  re.search(rf"^protocol:\s*{re.escape(protocol)}\s*$", head, re.M) is not None)
        if skill.is_file():
            head = skill.read_text(encoding="utf-8")[:400]
            check(f"{protocol}: skill frontmatter protocol matches",
                  re.search(rf"^protocol:\s*{re.escape(protocol)}\s*$", head, re.M) is not None)
    pdf_dir = ROOT / "docs/dc_power/manuals"
    pdfs = sorted(pdf_dir.glob("*.pdf")) if pdf_dir.is_dir() else []
    print(f"  INFO  downloaded vendor manuals on disk: {len(pdfs)}")
    check("manual sources documented", (ROOT / "docs/DC_POWER_PLUGINS.md").is_file())


def main():
    plugins = load_plugins()
    verify_metadata(plugins)
    verify_source_guards(plugins)
    verify_command_dialects(plugins)
    sample = plugins["itech_dc_power"][2][0]()
    verify_semantic_errors(sample)
    verify_transport_bindings(plugins)
    for protocol, (_path, _module, classes) in plugins.items():
        if classes:
            verify_serial_io(classes[0]())
    verify_ui_serial_params(plugins)
    for protocol, (_path, _module, classes) in plugins.items():
        if classes:
            inst = classes[0]()
            verify_lan_io(inst, inst.DEFAULT_LAN_PORT)
    verify_error_paths(plugins["itech_dc_power"][2][0]())
    verify_assets(plugins)

    print(f"\n  summary: {_passes} checks, {len(_failures)} failures")
    if _failures:
        print(f"FAILED: {len(_failures)} check(s): {', '.join(_failures[:12])}")
        return 1
    print("All DC power plugin checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
