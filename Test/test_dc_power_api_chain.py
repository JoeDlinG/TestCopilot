#!/usr/bin/env python3
"""Live API regression guard for the four programmable DC power plugins.

Run: python Test/test_dc_power_api_chain.py   (backend must be up on :8000)

The unit suite ``test_dc_power_plugins.py`` exercises the transport with fakes;
this one exercises the real chain that used to be broken (issue #11 / #33
regression class): discovered -> install -> enable -> add-device ->
PUT /interface serial -> PUT /interface ethernet -> back to serial.

It asserts, against a real running service:

* the plugin protocol is never overwritten by a generic bus name;
* ``config.transport`` follows the chosen interface and address columns are
  mirrored into the keys the plugin actually reads (port / host / tcp_port);
* stale keys of the previous interface are removed;
* after a LAN -> serial round trip the brand's manual baud rate is restored
  (ITECH/Chroma/Keysight 9600, TDK-Lambda 115200) instead of the generic
  115200 interface-spec default.

All created rows are removed in ``finally``. When the backend is not running
the script prints ``[SKIP]`` and exits 0 (see run_all.sh).
"""
import json
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8000"
# Bypass the system proxy: it can make a healthy local service look down.
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))

BAUDRATE = {
    "itech_dc_power": 9600,
    "tdk_lambda_dc_power": 115200,
    "chroma_dc_power": 9600,
    "keysight_dc_power": 9600,
}
LAN_PORT = {
    "itech_dc_power": 5025,
    "tdk_lambda_dc_power": 8003,
    "chroma_dc_power": 5025,
    "keysight_dc_power": 5025,
}

_failures = []
_passes = 0


def check(label, ok, detail=""):
    global _passes
    if ok:
        _passes += 1
    else:
        _failures.append(label)
        print("  FAIL  " + label + (f"  -> {detail}" if detail else ""))


def call(method, path, body=None):
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        BASE + path, data=data, method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with OPENER.open(req, timeout=20) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        try:
            return exc.code, json.loads(raw)
        except ValueError:
            return exc.code, raw[:200]


def config_of(device):
    cfg = device.get("config") or {}
    return json.loads(cfg) if isinstance(cfg, str) else cfg


def health():
    try:
        with OPENER.open(BASE + "/api/health", timeout=3) as resp:
            return resp.status == 200
    except Exception:
        return False


def main():
    if not health():
        print("[SKIP] backend not running on :8000 - live plugin API chain skipped")
        return 0

    status, discovered = call("GET", "/api/plugins/discovered")
    check("discovered endpoint returns 200", status == 200, status)
    plugins = [
        p for p in discovered.get("data", [])
        if p.get("protocol_name") in BAUDRATE
    ]
    check("four power plugins discovered", len(plugins) == 4,
          [p.get("protocol_name") for p in plugins])

    installed, devices = {}, []
    try:
        for meta in plugins:
            proto = meta["protocol_name"]
            payload = {
                "name": meta["name"], "version": meta.get("version") or "1.0.0",
                "description": meta.get("description"),
                "protocol_type": proto, "file_path": meta["file_path"],
                "module_name": meta["module_name"], "class_name": meta["class_name"],
            }
            st, res = call("POST", "/api/plugins/install", payload)
            check(f"{proto}: install", st == 200 and res.get("code") == 0, (st, res))
            if st != 200:
                continue
            pid = res["data"]["id"]
            installed[proto] = pid
            check(f"{proto}: plugin class loads without error",
                  not res["data"].get("error_message"), res["data"].get("error_message"))
            st, res = call("POST", f"/api/plugins/{pid}/enable", {})
            check(f"{proto}: enable", st == 200 and res["data"]["status"] == "enabled",
                  (st, res.get("detail")))
            st, res = call("POST", f"/api/plugins/{pid}/add-device", {})
            check(f"{proto}: add-device", st == 200 and res.get("code") == 0, (st, res))
            if st == 200:
                dev = res["data"]
                devices.append((proto, dev["id"]))
                check(f"{proto}: template keeps plugin protocol + serial default",
                      dev["protocol"] == proto and dev["connection_type"] == "serial",
                      (dev.get("protocol"), dev.get("connection_type")))
                check(f"{proto}: no hard-coded serial port in template",
                      not config_of(dev).get("port"), config_of(dev).get("port"))

        for proto, did in devices:
            st, res = call("PUT", f"/api/devices/{did}/interface", {
                "connection_type": "serial",
                "params": {"serial_port": "COM9", "baudrate": BAUDRATE[proto],
                           "data_bits": 7, "stop_bits": 2, "parity": "E"},
            })
            check(f"{proto}: PUT serial", st == 200 and res.get("code") == 0, (st, res))
            if st != 200:
                continue
            dev, cfg = res["data"], config_of(res["data"])
            check(f"{proto}: serial transport + mirrored port",
                  cfg.get("transport") == "serial" and cfg.get("port") == "COM9", cfg)
            check(f"{proto}: UI serial params reach config",
                  cfg.get("data_bits") == 7 and cfg.get("stop_bits") == 2
                  and cfg.get("parity") == "E", cfg)
            check(f"{proto}: protocol not overwritten by generic serial",
                  dev["protocol"] == proto, dev.get("protocol"))

            st, res = call("PUT", f"/api/devices/{did}/interface", {
                "connection_type": "ethernet",
                "params": {"ip_address": "192.168.1.77", "port": LAN_PORT[proto],
                           "protocol": "tcp"},
            })
            check(f"{proto}: PUT ethernet", st == 200 and res.get("code") == 0, (st, res))
            if st != 200:
                continue
            dev, cfg = res["data"], config_of(res["data"])
            check(f"{proto}: LAN transport + mirrored host/port",
                  cfg.get("transport") == "ethernet"
                  and cfg.get("host") == "192.168.1.77"
                  and cfg.get("tcp_port") == LAN_PORT[proto], cfg)
            check(f"{proto}: stale serial keys removed",
                  not any(k in cfg for k in ("port", "baudrate", "data_bits", "stop_bits")), cfg)
            check(f"{proto}: serial_port column cleared",
                  dev.get("serial_port") in (None, ""), dev.get("serial_port"))
            check(f"{proto}: protocol preserved after LAN switch",
                  dev["protocol"] == proto, dev.get("protocol"))

            # Minimal payload: the user just picks "串口" again. The generic
            # spec default (115200) must not silently replace the manual value.
            st, res = call("PUT", f"/api/devices/{did}/interface", {
                "connection_type": "serial", "params": {"serial_port": "COM4"},
            })
            check(f"{proto}: PUT serial round trip", st == 200 and res.get("code") == 0,
                  (st, res))
            if st != 200:
                continue
            cfg = config_of(res["data"])
            check(f"{proto}: brand baud rate restored ({BAUDRATE[proto]})",
                  cfg.get("baudrate") == BAUDRATE[proto], cfg.get("baudrate"))
            check(f"{proto}: transport back to serial, LAN keys cleared",
                  cfg.get("transport") == "serial" and cfg.get("port") == "COM4"
                  and "host" not in cfg and "tcp_port" not in cfg, cfg)
            st, res = call("GET", f"/api/devices/{did}/interface")
            check(f"{proto}: interface form reports the brand baud rate",
                  st == 200 and res["data"]["params"].get("baudrate") == BAUDRATE[proto],
                  res.get("data", {}).get("params", {}).get("baudrate"))
    finally:
        # Never leave test rows behind: other suites inspect the device/plugin
        # list, and a half-installed plugin changes startup repair behaviour.
        for _proto, did in devices:
            call("DELETE", f"/api/devices/{did}")
        for _proto, pid in installed.items():
            call("DELETE", f"/api/plugins/{pid}")

    print(f"  live API chain: {_passes} checks, {len(_failures)} failures")
    if _failures:
        print("FAILED: " + ", ".join(_failures[:12]))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
