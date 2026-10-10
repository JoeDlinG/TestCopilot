"""Execution-plan service: device resolution + static conflict validation.

Two responsibilities live here, both of which run *before* anything is
executed:

1. **Device resolution** — work out which device(s) a plan item will occupy
   (``resolve_item_devices``).
2. **Conflict validation** — reject plans where two items that run *in
   parallel* would fight over the same device, or over the same physical port
   (``validate_plan``).
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session
from app.models.models import (
    Device,
    ExecutionPlan,
    ExecutionPlanItem,
    TestCase,
    TestExecution,
    TestFlow,
)
from app.services.execution_service import ExecutionEngine

logger = logging.getLogger(__name__)

MAX_ITEMS_PER_PLAN = 50
MAX_PARALLEL_LIMIT = 16
MAX_LOOP_COUNT = 10000
MAX_DELAY_MS = 3_600_000  # 1 hour


# ---------------------------------------------------------------------- #
# Device resource keys — the unit of "exclusive ownership"
# ---------------------------------------------------------------------- #
# Two devices are considered mutually exclusive when they share *any* resource
# key.  Beyond the device itself this covers the physical port: two distinct
# devices configured on the same serial port / CAN channel / VISA address /
# IP:port cannot both be driven at the same time.

def _norm(value: Optional[str]) -> str:
    return str(value or "").strip().lower()


def device_resource_keys(device: Any) -> Set[str]:
    """Resource keys a device exclusively owns while it is being used."""
    keys: Set[str] = {f"dev:{device.id}"}
    if getattr(device, "serial_port", None):
        keys.add(f"serial:{_norm(device.serial_port)}")
    if getattr(device, "can_channel", None):
        keys.add(f"can:{_norm(device.can_channel)}")
    if getattr(device, "visa_address", None):
        keys.add(f"visa:{_norm(device.visa_address)}")
    ip = getattr(device, "ip_address", None)
    if ip:
        keys.add(f"net:{_norm(ip)}:{getattr(device, 'port', None)}")
    return keys


def describe_resource(key: str, device_name: str) -> str:
    """Human readable label for a resource key (used in conflict messages)."""
    kind, _, value = key.partition(":")
    if kind == "dev":
        return f"设备「{device_name}」"
    labels = {
        "serial": "串口",
        "can": "CAN 通道",
        "visa": "VISA 地址",
        "net": "网口",
    }
    return f"{labels.get(kind, '端口')}「{value}」"


# ---------------------------------------------------------------------- #
# Device resolution
# ---------------------------------------------------------------------- #

@dataclass
class DeviceResolution:
    """Outcome of "which device(s) will this item occupy?"."""

    state: str = "unresolved"          # resolved | candidates | unresolved
    device_ids: List[str] = field(default_factory=list)
    node_count: int = 0
    reason: str = ""

    @property
    def is_unresolved(self) -> bool:
        return self.state == "unresolved" or not self.device_ids


async def load_nodes(db: AsyncSession, testcase_id: str) -> List[Dict[str, Any]]:
    result = await db.execute(select(TestFlow).where(TestFlow.testcase_id == testcase_id))
    flow = result.scalar_one_or_none()
    if not flow or not flow.nodes:
        return []
    try:
        nodes = json.loads(flow.nodes) if isinstance(flow.nodes, str) else flow.nodes
    except (json.JSONDecodeError, TypeError):
        return []
    return nodes if isinstance(nodes, list) else []


async def resolve_item_devices(
    db: AsyncSession,
    testcase_id: str,
    explicit_device_id: Optional[str] = None,
) -> DeviceResolution:
    """Resolve the device(s) a test case will occupy.

    Priority (PRD §6.1):

    ① an explicitly configured ``device_id`` on the plan item  -> definitive
    ② ``device_id`` written into the flow nodes               -> definitive
    ③ protocol inferred from the commands -> every *connected* device whose
       protocol matches (0..N)
    ④ nothing matched                                         -> UNRESOLVED

    Note that, unlike the single-run resolver, this never falls back to
    "whichever device happens to be connected" — that fallback is exactly what
    made conflict detection impossible.
    """
    nodes = await load_nodes(db, testcase_id)

    # ① explicit override wins outright
    if explicit_device_id:
        return DeviceResolution(
            state="resolved",
            device_ids=[explicit_device_id],
            node_count=len(nodes),
            reason="计划项显式指定设备",
        )

    # ② device ids statically written into the flow
    static_ids: List[str] = []
    protocols: Set[str] = set()
    for node in nodes:
        config = node.get("config") or {}
        params = config.get("parameters") or {}
        for source in (config, params):
            did = source.get("device_id") if isinstance(source, dict) else None
            if did and did not in static_ids:
                static_ids.append(str(did))
        engine = ExecutionEngine
        for cmd in engine._extract_commands(node):
            proto = engine._infer_protocol(cmd)
            if proto:
                protocols.add(proto)

    # A flow that names several devices occupies *all* of them (that is the
    # normal shape of a cross-device case: PeakCAN sends, MG100 receives) — it
    # is definitive, not ambiguous.  "candidates" only means "we could not tell
    # which single device the runtime would pick".
    if static_ids:
        return DeviceResolution(
            state="resolved", device_ids=static_ids, node_count=len(nodes),
            reason=(
                "用例流程中指定了设备"
                if len(static_ids) == 1
                else f"用例流程中指定了 {len(static_ids)} 台设备（将同时占用）"
            ),
        )

    # ③ protocol inference against currently connected devices
    result = await db.execute(select(Device).where(Device.status == "connected"))
    devices = result.scalars().all()
    if not protocols:
        return DeviceResolution(
            state="unresolved", device_ids=[], node_count=len(nodes),
            reason="用例未包含可识别的设备指令，且未指定设备",
        )

    matched = [
        d.id for d in devices
        if (d.protocol or "").lower() in {p.lower() for p in protocols}
    ]
    if not matched:
        names = ", ".join(sorted(protocols))
        return DeviceResolution(
            state="unresolved", device_ids=[], node_count=len(nodes),
            reason=f"未找到已连接的 {names} 设备",
        )
    if len(matched) == 1:
        return DeviceResolution(
            state="resolved", device_ids=matched, node_count=len(nodes),
            reason="按协议推断到唯一设备",
        )
    return DeviceResolution(
        state="candidates", device_ids=matched, node_count=len(nodes),
        reason=f"按协议推断到 {len(matched)} 台候选设备，需收敛为 1 台",
    )


async def resolve_plan_items(
    db: AsyncSession, items: Sequence[ExecutionPlanItem]
) -> None:
    """Re-resolve and snapshot every item of a saved plan (PRD H2)."""
    for item in items:
        res = await resolve_item_devices(db, item.testcase_id, item.device_id)
        item.resolved_state = res.state
        item.resolved_device_ids = json.dumps(res.device_ids) if res.device_ids else None


def _item_device_ids(item: Any) -> List[str]:
    """Device ids of a plan item, tolerating both ORM rows and raw dicts."""
    if isinstance(item, dict):
        raw = item.get("resolved_device_ids")
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                parsed = None
            raw = parsed
        if isinstance(raw, list):
            return [str(d) for d in raw if d]
        explicit = item.get("device_id")
        return [str(explicit)] if explicit else []
    raw = getattr(item, "resolved_device_ids", None)
    if isinstance(raw, str) and raw:
        try:
            return [str(d) for d in json.loads(raw)]
        except (json.JSONDecodeError, TypeError):
            return []
    explicit = getattr(item, "device_id", None)
    return [str(explicit)] if explicit else []


def _item_state(item: Any) -> str:
    if isinstance(item, dict):
        return str(item.get("resolved_state") or "unresolved")
    return str(getattr(item, "resolved_state", None) or "unresolved")


def _item_value(item: Any, key: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


# ---------------------------------------------------------------------- #
# Validation
# ---------------------------------------------------------------------- #

@dataclass
class Issue:
    code: str
    level: str            # error | warning | info
    message: str
    item_ids: List[str] = field(default_factory=list)
    device_id: Optional[str] = None
    device_name: Optional[str] = None
    group_no: Optional[int] = None
    resource: Optional[str] = None
    suggestions: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        out = {
            "code": self.code,
            "level": self.level,
            "message": self.message,
            "item_ids": self.item_ids,
        }
        for key in ("device_id", "device_name", "group_no", "resource", "suggestions"):
            value = getattr(self, key)
            if value not in (None, [], {}):
                out[key] = value
        return out


async def average_case_duration_ms(db: AsyncSession, testcase_id: str) -> Optional[int]:
    """Mean duration of the most recent finished runs of a test case."""
    result = await db.execute(
        select(TestExecution.duration_ms)
        .where(
            TestExecution.testcase_id == testcase_id,
            TestExecution.duration_ms.isnot(None),
        )
        .order_by(TestExecution.created_at.desc())
        .limit(5)
    )
    values = [v for v in result.scalars().all() if v]
    if not values:
        return None
    return int(sum(values) / len(values))


async def validate_plan(
    db: AsyncSession,
    plan: Dict[str, Any],
    items: Sequence[Any],
) -> Dict[str, Any]:
    """Statically validate a plan (saved or still a draft).

    Returns ``{valid, blocking, errors, warnings, infos}``.  ``blocking`` is
    true whenever at least one *error* exists, which is what disables the
    "start" button and makes ``POST /run`` answer 409.
    """
    errors: List[Issue] = []
    warnings: List[Issue] = []
    infos: List[Issue] = []

    devices_result = await db.execute(select(Device))
    devices = devices_result.scalars().all()
    devices_by_id: Dict[str, Any] = {d.id: d for d in devices}

    max_parallel = int(plan.get("max_parallel") or 4)
    plan_loop = int(plan.get("plan_loop_count") or 1)

    # ---- group items by group_no -------------------------------------
    groups: Dict[int, List[Any]] = {}
    for item in items:
        groups.setdefault(int(_item_value(item, "group_no", 0) or 0), []).append(item)

    total_iterations = 0
    estimated_ms = 0
    used_devices: Set[str] = set()
    seen_case_in_group: Dict[Tuple[int, str], int] = {}

    for group_no in sorted(groups):
        group_items = groups[group_no]

        # ---- E3: group larger than the concurrency ceiling -----------
        if len(group_items) > max_parallel:
            errors.append(Issue(
                code="PARALLEL_LIMIT_EXCEEDED",
                level="error",
                message=(
                    f"并行组 {group_no} 有 {len(group_items)} 项，"
                    f"超过最大并行度 {max_parallel}"
                ),
                group_no=group_no,
                item_ids=[str(_item_value(i, "id", "")) for i in group_items],
            ))

        # ---- E4: same test case twice inside one parallel group ------
        for item in group_items:
            case_id = str(_item_value(item, "testcase_id", ""))
            key = (group_no, case_id)
            seen_case_in_group[key] = seen_case_in_group.get(key, 0) + 1
        for (gno, case_id), count in seen_case_in_group.items():
            if gno == group_no and count > 1:
                dup_items = [
                    str(_item_value(i, "id", ""))
                    for i in group_items
                    if str(_item_value(i, "testcase_id", "")) == case_id
                ]
                tc = await db.get(TestCase, case_id)
                name = tc.name if tc else case_id
                errors.append(Issue(
                    code="DUPLICATE_CASE_IN_GROUP",
                    level="error",
                    message=f"用例「{name}」在并行组 {group_no} 中重复出现 {count} 次",
                    group_no=gno,
                    item_ids=dup_items,
                ))

        # ---- resource map: resource key -> item ids ------------------
        resource_map: Dict[str, List[str]] = {}
        resource_owner: Dict[str, str] = {}   # key -> device id (for messages)

        for item in group_items:
            item_id = str(_item_value(item, "id", "") or _item_value(item, "testcase_id", ""))
            state = _item_state(item)
            dev_ids = _item_device_ids(item)

            if not dev_ids or state == "unresolved":
                # ---- E2 ----
                case_id = str(_item_value(item, "testcase_id", ""))
                tc = await db.get(TestCase, case_id)
                name = tc.name if tc else case_id
                if len(group_items) > 1:
                    errors.append(Issue(
                        code="UNRESOLVED_DEVICE_IN_PARALLEL",
                        level="error",
                        message=f"「{name}」未确定设备，不能与其它项并行",
                        group_no=group_no,
                        item_ids=[item_id],
                    ))
                else:
                    warnings.append(Issue(
                        code="UNRESOLVED_DEVICE_SERIAL",
                        level="warning",
                        message=f"「{name}」未确定设备，执行时将沿用自动选择逻辑",
                        group_no=group_no,
                        item_ids=[item_id],
                    ))
                continue

            if state == "candidates" and len(group_items) > 1:
                case_id = str(_item_value(item, "testcase_id", ""))
                tc = await db.get(TestCase, case_id)
                name = tc.name if tc else case_id
                warnings.append(Issue(
                    code="CANDIDATE_DEVICE_IN_PARALLEL",
                    level="warning",
                    message=f"「{name}」匹配到多台候选设备，并行下建议手工指定为 1 台",
                    group_no=group_no,
                    item_ids=[item_id],
                ))

            for dev_id in dev_ids:
                used_devices.add(dev_id)
                dev = devices_by_id.get(dev_id)
                if dev is None:
                    warnings.append(Issue(
                        code="DEVICE_NOT_FOUND",
                        level="warning",
                        message=f"设备 {dev_id} 不存在，可能已被删除",
                        item_ids=[item_id],
                        device_id=dev_id,
                    ))
                    continue
                # ---- W1: device offline ------------------------------
                if dev.status != "connected":
                    warnings.append(Issue(
                        code="DEVICE_OFFLINE",
                        level="warning",
                        message=f"设备「{dev.name}」当前未连接，执行时会失败",
                        item_ids=[item_id],
                        device_id=dev_id,
                        device_name=dev.name,
                    ))
                for key in device_resource_keys(dev):
                    resource_map.setdefault(key, []).append(item_id)
                    resource_owner.setdefault(key, dev_id)

        # ---- E1: shared resource inside a parallel group -------------
        for key, item_ids in resource_map.items():
            unique = list(dict.fromkeys(item_ids))
            if len(unique) < 2:
                continue
            owner_id = resource_owner.get(key, "")
            owner = devices_by_id.get(owner_id)
            owner_name = owner.name if owner else owner_id
            is_port = not key.startswith("dev:")
            case_names = []
            for iid in unique:
                item = next(
                    (i for i in group_items
                     if str(_item_value(i, "id", "") or _item_value(i, "testcase_id", "")) == iid),
                    None,
                )
                if item is not None:
                    tc = await db.get(TestCase, str(_item_value(item, "testcase_id", "")))
                    case_names.append(tc.name if tc else str(_item_value(item, "testcase_id", "")))
            label = describe_resource(key, owner_name)
            suffix = "（两个不同设备占用了同一端口）" if is_port else ""
            errors.append(Issue(
                code="PORT_CONFLICT" if is_port else "DEVICE_CONFLICT",
                level="error",
                message=(
                    f"{label} 被 {len(unique)} 个并行用例同时占用{suffix}："
                    + "、".join(case_names)
                ),
                group_no=group_no,
                item_ids=unique,
                device_id=owner_id,
                device_name=owner_name,
                resource=key,
                suggestions=[
                    {"action": "auto_serialize", "label": "自动串行化(推荐)"},
                    {"action": "manual", "label": "手动调整分组"},
                ],
            ))

        # ---- estimate (I1) -------------------------------------------
        group_cost = 0
        for item in group_items:
            loop = int(_item_value(item, "loop_count", 1) or 1)
            before = int(_item_value(item, "delay_before_ms", 0) or 0)
            after = int(_item_value(item, "delay_after_ms", 0) or 0)
            interval = int(_item_value(item, "loop_interval_ms", 0) or 0)
            total_iterations += loop
            case_id = str(_item_value(item, "testcase_id", ""))
            avg = await average_case_duration_ms(db, case_id)
            per_iteration = (avg or 0) + before + after
            group_cost = max(group_cost, loop * per_iteration + max(loop - 1, 0) * interval)
        estimated_ms += group_cost

        # ---- W2: empty flow ------------------------------------------
        for item in group_items:
            if int(_item_value(item, "node_count", -1) or -1) == 0:
                case_id = str(_item_value(item, "testcase_id", ""))
                tc = await db.get(TestCase, case_id)
                name = tc.name if tc else case_id
                warnings.append(Issue(
                    code="EMPTY_FLOW",
                    level="warning",
                    message=f"用例「{name}」没有流程节点，执行将直接结束",
                    item_ids=[str(_item_value(item, "id", ""))],
                ))

    estimated_ms *= max(plan_loop, 1)

    if len(items) > MAX_ITEMS_PER_PLAN:
        errors.append(Issue(
            code="TOO_MANY_ITEMS",
            level="error",
            message=f"计划包含 {len(items)} 项，超过上限 {MAX_ITEMS_PER_PLAN}，请拆分",
        ))

    infos.append(Issue(
        code="ESTIMATE",
        level="info",
        message=(
            f"预计 {total_iterations * max(plan_loop, 1)} 次迭代 / "
            f"{len(used_devices)} 台设备 / 约 {estimated_ms / 1000:.1f} 秒"
        ),
    ))

    for issue in errors:
        logger.info("plan validation error: %s | %s", issue.code, issue.message)
    for issue in warnings:
        logger.info("plan validation warning: %s | %s", issue.code, issue.message)

    return {
        "valid": not errors,
        "blocking": bool(errors),
        "errors": [i.to_dict() for i in errors],
        "warnings": [i.to_dict() for i in warnings],
        "infos": [
            {
                "code": i.code,
                "message": i.message,
                "total_iterations": total_iterations * max(plan_loop, 1),
                "devices": len(used_devices),
                "estimated_ms": estimated_ms,
            }
            for i in infos
        ],
    }


def auto_serialize(items: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Fix suggestion: give every item its own group, preserving ``seq`` order.

    Conflicting items end up in consecutive single-item groups, so the relative
    order is unchanged while nothing runs in parallel any more.
    """
    ordered = sorted(items, key=lambda i: (int(i.get("seq") or 0), str(i.get("id") or "")))
    out: List[Dict[str, Any]] = []
    group_no = 1
    prev_seq_group: Optional[int] = None
    for item in ordered:
        current = int(item.get("group_no") or 0)
        if prev_seq_group is not None and current != prev_seq_group:
            group_no += 1
        new_item = dict(item)
        new_item["group_no"] = group_no
        out.append(new_item)
        prev_seq_group = current
    return out
