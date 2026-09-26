#!/usr/bin/env python3
"""
Test: 通信日志链路全链路验证

模拟一个 PeakCAN 设备（其 receive() 不接受 timeout kwarg，即之前导致
TypeError 被静默吞掉的场景）持续产生 CAN ID=0x001 的报文，验证：

1. 设备级监听任务能正确接收（_safe_receive 兼容无 timeout 参数的接口）
2. 收到的报文实时广播给通信终端（device_data）
3. 收到的报文写入 communication_logs 表（通信日志页数据源）
4. send_command 过程中实时广播 command_sent / command_response

运行：python3 Test/test_can_comlog.py
"""

import os
import sys
import asyncio
import tempfile

# 使用临时数据库，避免污染真实数据
_tmpdir = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_tmpdir}/test.db"

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))


class FakePeakCAN:
    """Fake PeakCAN interface.

    receive() deliberately takes NO ``timeout`` kwarg to reproduce the plugin
    signature that previously crashed the receive loop with a TypeError.
    """

    def __init__(self, frames):
        self._frames = list(frames)
        self.sent = []

    async def connect(self):
        return True

    async def disconnect(self):
        return True

    async def send(self, data):
        self.sent.append(data)
        return {"status": "sent", "arbitration_id": 0x001, "data": "AABB"}

    async def receive(self):  # noqa: D401 -- intentionally no timeout kwarg
        if self._frames:
            return self._frames.pop(0)
        return None


CAN_FRAMES_001 = [
    {
        "arbitration_id": 0x001,
        "is_extended_id": False,
        "is_remote_frame": False,
        "is_fd": False,
        "is_error_frame": False,
        "dlc": 4,
        "data": "11223344",
        "timestamp": 0.101,
    },
    {
        "arbitration_id": 0x001,
        "is_extended_id": False,
        "is_remote_frame": False,
        "is_fd": False,
        "is_error_frame": False,
        "dlc": 2,
        "data": "5566",
        "timestamp": 0.202,
    },
]


async def main():
    from app.api import websocket as ws_mod
    from app.services import device_service
    from app.core.database import init_db, async_session
    from app.models.models import Device, CommunicationLog
    from sqlalchemy import select

    await init_db()

    device_id = "can-test-001"

    # 1) Create a connected device row (needed by send_command)
    async with async_session() as db:
        db.add(Device(
            id=device_id,
            name="Test CAN Device",
            type="can",
            protocol="peakcan",
            connection_type="can",
            status="connected",
        ))
        await db.commit()

    fake = FakePeakCAN(CAN_FRAMES_001)
    device_service._active_connections[device_id] = fake

    # 2) Capture broadcasts from BOTH the monitor loop (ws module) and
    #    send_command (device_service module namespace)
    broadcast = []

    async def fake_broadcast(did, payload):
        broadcast.append(payload)

    ws_mod.broadcast_device_update = fake_broadcast
    device_service.broadcast_device_update = fake_broadcast

    # 3) Start the global device monitor
    ws_mod.start_device_monitor(device_id, protocol="peakcan")
    await asyncio.sleep(0.8)

    # 4) Verify real-time broadcast of CAN 0x001 frames
    rx = [m for m in broadcast if m.get("type") == "device_data"]
    assert rx, "FAIL: 未收到任何 device_data 广播（监听任务未工作）"
    ids = {m["data"].get("arbitration_id") for m in rx}
    assert 0x001 in ids, f"FAIL: 未收到 ID 0x001 报文, 收到 {ids}"
    print(f"  ✓ 监听任务广播了 {len(rx)} 帧 CAN 报文, 包含 ID 0x001: {rx[0]['data']}")

    # 5) Verify the received frames were persisted for the 通信日志 page
    async with async_session() as db:
        result = await db.execute(select(CommunicationLog))
        rows = result.scalars().all()
    rx_rows = [r for r in rows if r.direction == "received"]
    assert rx_rows, "FAIL: communication_logs 表中没有 RECEIVED 记录"
    hexes = {r.raw_data_hex for r in rx_rows}
    assert "11223344" in hexes, f"FAIL: raw_data_hex 缺少 11223344, 实际 {hexes}"
    print(f"  ✓ 通信日志表写入 {len(rx_rows)} 条 RECEIVED 记录: {rx_rows[0].raw_data_hex} (dlc={rx_rows[0].raw_data_size})")

    ws_mod.stop_device_monitor(device_id)

    # 6) Verify send_command broadcasts sent/response in real time
    broadcast.clear()
    async with async_session() as db:
        await device_service.device_service.send_command(db, device_id, "0x001#AABB")
    types = [m.get("type") for m in broadcast]
    assert "command_sent" in types, f"FAIL: 缺少 command_sent 广播: {types}"
    assert "command_response" in types, f"FAIL: 缺少 command_response 广播: {types}"
    print(f"  ✓ send_command 实时广播: {types}")

    ws_mod.stop_device_monitor(device_id)
    device_service._active_connections.pop(device_id, None)

    print("\n=== 全部通过：通信日志链路正常 ===")


if __name__ == "__main__":
    asyncio.run(main())
