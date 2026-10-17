"""Run blocking I/O off the asyncio event loop.

Why this module exists
----------------------
AITestLab drives real instruments from coroutines. Serial ports, CAN buses and
VISA resources are **synchronous** APIs: ``serial.Serial.read()`` blocks the
calling thread until a byte arrives or the read timeout expires.

Calling those directly inside ``async def`` therefore blocks the **whole event
loop** — not just the current request. The symptom is brutal and confusing:

* a running plan appears to freeze (its WebSocket progress cannot be sent);
* every unrelated button click in the UI hangs until the device times out.

Measured on this machine: while a Mini Gateway 100 command was in flight,
``/api/health`` latency jumped from ~114 ms to **2024 ms** — exactly the
plugin's 2.0 s serial timeout.

Everything that touches a synchronous device handle must go through
:func:`run_blocking`, which hands the call to a shared thread pool.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
from typing import Any, Callable

__all__ = ["run_blocking", "BLOCKING_POOL"]

# One pool for the whole process. Sized above the number of devices we can
# plausibly drive concurrently so a slow instrument never starves another.
BLOCKING_POOL = concurrent.futures.ThreadPoolExecutor(
    max_workers=16, thread_name_prefix="blocking-io"
)


async def run_blocking(func: Callable[..., Any], *args: Any) -> Any:
    """Await *func* executed in the blocking-I/O thread pool.

    Python 3.8 has no ``asyncio.to_thread``, hence this backport.
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(BLOCKING_POOL, func, *args)
