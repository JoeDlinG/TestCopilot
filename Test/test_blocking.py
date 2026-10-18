#!/usr/bin/env python3
"""Regression tests for app.core.blocking.run_blocking.

Why this file exists
--------------------
PeakCAN stopped connecting after the blocking-I/O migration: the plugin called
``run_blocking(can.interface.Bus, **bus_kwargs)`` while ``run_blocking`` only
accepted positional args, so every connect attempt raised::

    TypeError: run_blocking() got an unexpected keyword argument 'interface'

The plugin's ``except Exception`` then reported a misleading "kernel module not
loaded" hint. These tests pin the contract so the next refactor cannot silently
break it again:

1. keyword arguments must be forwarded (the actual bug);
2. positional arguments still work;
3. the call really runs off the event loop — that is the whole point;
4. exceptions propagate instead of being swallowed.
"""
import asyncio
import os
import sys
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.core.blocking import run_blocking  # noqa: E402

FAILURES = []


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  -> {detail}" if detail else ""))
    if not ok:
        FAILURES.append(name)


def main():
    loop = asyncio.new_event_loop()
    try:
        # 1. kwargs are forwarded (the regression that broke PeakCAN)
        try:
            got = loop.run_until_complete(
                run_blocking(dict, interface="socketcan", channel="can0")
            )
            check(
                "kwargs 被正确转发",
                got == {"interface": "socketcan", "channel": "can0"},
                str(got),
            )
        except TypeError as e:
            check("kwargs 被正确转发", False, f"TypeError: {e}")

        # 2. positional args still work
        got = loop.run_until_complete(run_blocking(str, 42))
        check("位置参数仍然生效", got == "42", got)

        # 3. mixed args + kwargs
        got = loop.run_until_complete(run_blocking(dict, {"a": 1}, b=2))
        check("位置参数与 kwargs 混用", got == {"a": 1, "b": 2}, str(got))

        # 4. it really runs in another thread, off the event loop
        main_thread = threading.get_ident()

        def blocking_sleep():
            time.sleep(0.3)
            return threading.get_ident()

        async def measure():
            # Kick the blocking call off *without* awaiting it, then count how
            # many event-loop ticks still happen while the worker sleeps.
            task = asyncio.ensure_future(run_blocking(blocking_sleep))
            start = time.monotonic()
            ticks = 0
            while time.monotonic() - start < 0.25:
                await asyncio.sleep(0.01)
                ticks += 1
            worker = await task
            return worker, ticks

        worker, ticks = loop.run_until_complete(measure())
        check("阻塞调用在其它线程执行", worker != main_thread)
        check("阻塞期间事件循环未被卡住", ticks > 10, f"ticks={ticks}")

        # 5. exceptions propagate (no silent swallowing)
        def boom():
            raise ValueError("boom")

        try:
            loop.run_until_complete(run_blocking(boom))
            check("异常向上传播", False, "没有抛出异常")
        except ValueError as e:
            check("异常向上传播", str(e) == "boom", str(e))
    finally:
        loop.close()


if __name__ == "__main__":
    print("=== test_blocking ===")
    main()
    if FAILURES:
        print(f"\nFAILED ({len(FAILURES)}): {', '.join(FAILURES)}")
        sys.exit(1)
    print("\nAll checks passed.")
