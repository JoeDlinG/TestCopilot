"""Project bundle service — export / import the whole workspace configuration.

A *project file* is one JSON document that captures every configuration the
user assembled in AITestLab:

``models``           AI model configs (API keys are NEVER included)
``devices``          instrument definitions
``plugins``          plugin registry + runtime config
``skills``           plugin skill / manual markdown
``test_cases``       test cases together with their flowchart
``execution_plans``  execution-manager plans and their items
``dashboards``       custom dashboard layouts

The bundle backs the 导出 / 导入 / 另存为 / 重命名 actions in the UI.  Saved
project files live in ``backend/projects/``.

Design notes
------------
* JSON text columns are decoded to real JSON on export and re-encoded on
  import, so the file stays human readable while round-tripping losslessly.
* Import matches an existing row first by ``id`` and then by its natural key,
  which makes re-importing an exported project idempotent instead of creating
  duplicates.
* Secrets (``ai_models.api_key_encrypted``) are excluded on export and left
  untouched on import — a project file is meant to be shared.
"""
import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import delete, inspect as sa_inspect, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.timeutils import UTCDateTime, parse_iso_utc, utc_now
from app.models.models import (
    AIModelConfig,
    CommunicationLog,
    Dashboard,
    Device,
    ExecutionPlan,
    ExecutionPlanItem,
    Plugin,
    TestCase,
    TestExecution,
    TestFlow,
    TestStepResult,
)
from app.services.plugin_service import plugin_service

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

SCHEMA = "aitestlab.project"
SCHEMA_VERSION = 1

PROJECTS_DIR = Path(__file__).resolve().parents[2] / "projects"

SECTIONS: Tuple[str, ...] = (
    "models",
    "devices",
    "plugins",
    "skills",
    "test_cases",
    "execution_plans",
    "dashboards",
)

SECTION_LABELS: Dict[str, str] = {
    "models": "模型配置",
    "devices": "设备配置",
    "plugins": "插件配置",
    "skills": "Skill 配置",
    "test_cases": "测试用例",
    "execution_plans": "执行管理器",
    "dashboards": "仪表盘配置",
}

# Columns that must never leave the machine.
SECRET_COLUMNS = ("api_key_encrypted",)

_UNSAFE_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Generic row <-> dict helpers
# --------------------------------------------------------------------------- #

def _decode_json(value: Any, default: Any = None) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (ValueError, TypeError):
            return default
    return value


def _encode_json(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def _column_pairs(model_or_obj: Any) -> List[Tuple[str, str, Any]]:
    """Return ``[(db_column_name, attribute_key, column)]`` for every mapped column.

    ``Column.key`` cannot be trusted here: for a column declared as
    ``extra_meta = Column("metadata", Text)`` it still reports ``"metadata"``,
    so ``getattr(row, "metadata")`` returns SQLAlchemy's ``MetaData`` object
    rather than the row value — which recursed forever during JSON encoding.
    The mapper's column property always carries the real attribute name.
    """
    inspected = sa_inspect(model_or_obj)
    mapper = getattr(inspected, "mapper", inspected)
    pairs: List[Tuple[str, str, Any]] = []
    for col in mapper.columns:
        try:
            pairs.append((col.name, mapper.get_property_by_column(col).key, col))
        except Exception:  # noqa: BLE001 - unmapped column, skip it
            continue
    return pairs


def _coerce_value(col: Any, value: Any) -> Any:
    """Turn a bundle value back into the Python type the column expects."""
    if isinstance(col.type, UTCDateTime) and isinstance(value, str):
        # The bundle stores ISO-8601; the column wants a datetime.
        return parse_iso_utc(value)
    return value


def _dump_row(
    obj: Any,
    json_cols: Sequence[str] = (),
    exclude: Sequence[str] = (),
) -> Dict[str, Any]:
    """Serialize an ORM row using DB column names as keys."""
    out: Dict[str, Any] = {}
    for name, key, _col in _column_pairs(obj):
        if name in exclude or name in SECRET_COLUMNS:
            continue
        value = getattr(obj, key, None)
        if isinstance(value, datetime):
            value = value.isoformat()
        elif name in json_cols:
            value = _decode_json(value)
        out[name] = value
    return out


def _apply_row(
    obj: Any,
    data: Dict[str, Any],
    json_cols: Sequence[str] = (),
    skip: Sequence[str] = (),
) -> None:
    """Copy *data* onto an ORM row, re-encoding JSON columns."""
    for name, key, col in _column_pairs(obj):
        if name in skip or name in SECRET_COLUMNS:
            continue
        if name not in data:
            continue
        value = data[name]
        if name in json_cols:
            value = _encode_json(value)
        setattr(obj, key, _coerce_value(col, value))


def _build_kwargs(
    model: Any,
    data: Dict[str, Any],
    json_cols: Sequence[str] = (),
) -> Dict[str, Any]:
    """Build ``model(**kwargs)`` arguments from a serialized row."""
    kwargs: Dict[str, Any] = {}
    for name, key, col in _column_pairs(model):
        if name in SECRET_COLUMNS or name not in data:
            continue
        value = data[name]
        if name in json_cols:
            value = _encode_json(value)
        kwargs[key] = _coerce_value(col, value)
    return kwargs


def _new_stats() -> Dict[str, int]:
    return {"created": 0, "updated": 0, "skipped": 0}


# --------------------------------------------------------------------------- #
# Export
# --------------------------------------------------------------------------- #

async def _export_models(db: AsyncSession) -> List[Dict[str, Any]]:
    rows = (await db.execute(select(AIModelConfig))).scalars().all()
    return [_dump_row(r, json_cols=("parameters",)) for r in rows]


async def _export_devices(db: AsyncSession) -> List[Dict[str, Any]]:
    rows = (await db.execute(select(Device))).scalars().all()
    return [_dump_row(r, json_cols=("config", "metadata")) for r in rows]


async def _export_plugins(db: AsyncSession) -> List[Dict[str, Any]]:
    rows = (await db.execute(select(Plugin))).scalars().all()
    return [_dump_row(r, json_cols=("config_schema", "config")) for r in rows]


async def _export_skills() -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for meta in plugin_service.list_plugin_skills():
        full = plugin_service.get_plugin_skill_content(meta["protocol"]) or {}
        out.append({
            "protocol": meta["protocol"],
            "name": meta.get("name") or meta["protocol"],
            "keywords": meta.get("keywords") or [],
            "skill": full.get("skill") or "",
            "manual": full.get("manual") or "",
        })
    return out


async def _export_test_cases(db: AsyncSession) -> List[Dict[str, Any]]:
    cases = (await db.execute(select(TestCase))).scalars().all()
    flows = {
        f.testcase_id: f
        for f in (await db.execute(select(TestFlow))).scalars().all()
    }
    out: List[Dict[str, Any]] = []
    for tc in cases:
        row = _dump_row(tc, json_cols=("tags",), exclude=("flow_id",))
        flow = flows.get(tc.id)
        row["flow"] = (
            _dump_row(flow, json_cols=("nodes", "edges", "viewport"))
            if flow else None
        )
        out.append(row)
    return out


async def _export_execution_plans(db: AsyncSession) -> List[Dict[str, Any]]:
    plans = (await db.execute(select(ExecutionPlan))).scalars().all()
    items = (await db.execute(select(ExecutionPlanItem))).scalars().all()
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for it in items:
        grouped.setdefault(it.plan_id, []).append(
            _dump_row(it, json_cols=("resolved_device_ids",))
        )
    out: List[Dict[str, Any]] = []
    for plan in plans:
        row = _dump_row(plan, exclude=("last_run_id",))
        row["items"] = sorted(
            grouped.get(plan.id, []), key=lambda r: (r.get("group_no") or 0, r.get("seq") or 0)
        )
        out.append(row)
    return out


async def _export_dashboards(db: AsyncSession) -> List[Dict[str, Any]]:
    rows = (await db.execute(select(Dashboard))).scalars().all()
    return [_dump_row(r, json_cols=("layout", "widgets", "data_source")) for r in rows]


async def export_bundle(
    db: AsyncSession,
    sections: Optional[Sequence[str]] = None,
    project_name: str = "",
) -> Dict[str, Any]:
    """Build the project bundle from the current database."""
    wanted = [s for s in (sections or SECTIONS) if s in SECTIONS] or list(SECTIONS)

    builders = {
        "models": lambda: _export_models(db),
        "devices": lambda: _export_devices(db),
        "plugins": lambda: _export_plugins(db),
        "skills": _export_skills,
        "test_cases": lambda: _export_test_cases(db),
        "execution_plans": lambda: _export_execution_plans(db),
        "dashboards": lambda: _export_dashboards(db),
    }

    data: Dict[str, Any] = {}
    for section in wanted:
        data[section] = await builders[section]()

    return {
        "schema": SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "project_name": project_name or "未命名项目",
        "app_version": settings.APP_VERSION,
        "exported_at": utc_now().isoformat(),
        "sections": wanted,
        "counts": {s: len(data.get(s) or []) for s in wanted},
        "data": data,
    }


# --------------------------------------------------------------------------- #
# Import
# --------------------------------------------------------------------------- #

async def _clear_section(db: AsyncSession, section: str) -> None:
    """Delete every row of a section (``mode="replace"``), child rows first."""
    if section == "test_cases":
        await db.execute(delete(TestStepResult))
        await db.execute(delete(TestExecution))
        await db.execute(delete(TestFlow))
        await db.execute(delete(TestCase))
    elif section == "models":
        await db.execute(update(TestCase).values(ai_model_id=None))
        await db.execute(delete(AIModelConfig))
    elif section == "devices":
        await db.execute(delete(CommunicationLog))
        await db.execute(delete(Device))
    elif section == "plugins":
        await db.execute(delete(Plugin))
    elif section == "execution_plans":
        await db.execute(delete(ExecutionPlanItem))
        await db.execute(delete(ExecutionPlan))
    elif section == "dashboards":
        await db.execute(delete(Dashboard))


async def _import_models(db: AsyncSession, rows: List[Dict[str, Any]]) -> Dict[str, int]:
    stats = _new_stats()
    existing = list((await db.execute(select(AIModelConfig))).scalars().all())
    by_id = {m.id: m for m in existing}
    by_key = {(m.name, m.provider, m.model_name): m for m in existing}

    for row in rows or []:
        if not (row or {}).get("name"):
            stats["skipped"] += 1
            continue
        obj = by_id.get(row.get("id")) or by_key.get(
            (row.get("name"), row.get("provider"), row.get("model_name"))
        )
        if obj is None:
            obj = AIModelConfig(**_build_kwargs(AIModelConfig, row, ("parameters",)))
            db.add(obj)
            stats["created"] += 1
        else:
            _apply_row(obj, row, ("parameters",), skip=("id",))
            obj.updated_at = utc_now()
            stats["updated"] += 1
    return stats


async def _import_devices(db: AsyncSession, rows: List[Dict[str, Any]]) -> Dict[str, int]:
    stats = _new_stats()
    existing = list((await db.execute(select(Device))).scalars().all())
    by_id = {d.id: d for d in existing}
    by_name = {d.name: d for d in existing}

    for row in rows or []:
        if not (row or {}).get("name"):
            stats["skipped"] += 1
            continue
        obj = by_id.get(row.get("id")) or by_name.get(row.get("name"))
        if obj is None:
            obj = Device(**_build_kwargs(Device, row, ("config", "metadata")))
            db.add(obj)
            stats["created"] += 1
        else:
            # Keep the live connection state — importing a file must not claim
            # a device is connected when it is not.
            _apply_row(obj, row, ("config", "metadata"), skip=("id", "status", "last_seen"))
            obj.updated_at = utc_now()
            stats["updated"] += 1
    return stats


async def _import_plugins(db: AsyncSession, rows: List[Dict[str, Any]]) -> Dict[str, int]:
    stats = _new_stats()
    existing = list((await db.execute(select(Plugin))).scalars().all())
    by_id = {p.id: p for p in existing}
    by_name = {p.name: p for p in existing}

    for row in rows or []:
        if not (row or {}).get("name"):
            stats["skipped"] += 1
            continue
        obj = by_id.get(row.get("id")) or by_name.get(row.get("name"))
        if obj is None:
            obj = Plugin(**_build_kwargs(Plugin, row, ("config_schema", "config")))
            db.add(obj)
            stats["created"] += 1
        else:
            # ``file_path``/``module_name`` are machine-specific: only the
            # portable configuration is merged.
            _apply_row(
                obj, row, ("config_schema", "config"),
                skip=("id", "file_path", "module_name", "class_name", "status"),
            )
            obj.updated_at = utc_now()
            stats["updated"] += 1
    return stats


def _import_skills(rows: List[Dict[str, Any]]) -> Dict[str, int]:
    stats = _new_stats()
    for row in rows or []:
        protocol = (row or {}).get("protocol")
        if not protocol:
            stats["skipped"] += 1
            continue
        try:
            plugin_service.save_plugin_skill(
                protocol=str(protocol),
                name=row.get("name") or str(protocol),
                keywords=row.get("keywords") or [],
                content=row.get("skill") or "",
            )
            stats["updated"] += 1
        except Exception as exc:  # noqa: BLE001 - one bad skill must not abort
            logger.warning("project import: skill %s failed: %s", protocol, exc)
            stats["skipped"] += 1
    return stats


async def _import_test_cases(db: AsyncSession, rows: List[Dict[str, Any]]) -> Dict[str, int]:
    stats = _new_stats()
    existing = list((await db.execute(select(TestCase))).scalars().all())
    by_id = {t.id: t for t in existing}
    by_name = {t.name: t for t in existing}
    flows = {f.testcase_id: f for f in (await db.execute(select(TestFlow))).scalars().all()}

    for row in rows or []:
        if not (row or {}).get("name"):
            stats["skipped"] += 1
            continue
        obj = by_id.get(row.get("id")) or by_name.get(row.get("name"))
        if obj is None:
            obj = TestCase(**_build_kwargs(TestCase, row, ("tags",)))
            db.add(obj)
            await db.flush()
            stats["created"] += 1
        else:
            _apply_row(obj, row, ("tags",), skip=("id", "flow_id", "ai_model_id"))
            obj.updated_at = utc_now()
            stats["updated"] += 1

        flow_data = row.get("flow")
        if not flow_data:
            continue
        flow = flows.get(obj.id)
        if flow is None:
            flow = TestFlow(
                testcase_id=obj.id,
                nodes=_encode_json(flow_data.get("nodes")) or "[]",
                edges=_encode_json(flow_data.get("edges")) or "[]",
                viewport=_encode_json(flow_data.get("viewport")),
            )
            db.add(flow)
            flows[obj.id] = flow
        else:
            flow.nodes = _encode_json(flow_data.get("nodes")) or "[]"
            flow.edges = _encode_json(flow_data.get("edges")) or "[]"
            flow.viewport = _encode_json(flow_data.get("viewport"))
        obj.flow_id = flow.id
    return stats


async def _import_execution_plans(db: AsyncSession, rows: List[Dict[str, Any]]) -> Dict[str, int]:
    stats = _new_stats()
    existing = list((await db.execute(select(ExecutionPlan))).scalars().all())
    by_id = {p.id: p for p in existing}
    by_name = {p.name: p for p in existing}

    for row in rows or []:
        if not (row or {}).get("name"):
            stats["skipped"] += 1
            continue
        obj = by_id.get(row.get("id")) or by_name.get(row.get("name"))
        if obj is None:
            obj = ExecutionPlan(**_build_kwargs(ExecutionPlan, row))
            db.add(obj)
            await db.flush()
            stats["created"] += 1
        else:
            _apply_row(obj, row, skip=("id", "last_run_id"))
            obj.updated_at = utc_now()
            stats["updated"] += 1

        items = row.get("items")
        if items is None:
            continue
        # Items are plan-owned configuration: replace them wholesale so the
        # imported ordering/groups are reproduced exactly.
        await db.execute(delete(ExecutionPlanItem).where(ExecutionPlanItem.plan_id == obj.id))
        for item in items:
            payload = dict(item)
            payload.pop("id", None)
            payload["plan_id"] = obj.id
            db.add(ExecutionPlanItem(
                **_build_kwargs(ExecutionPlanItem, payload, ("resolved_device_ids",))
            ))
    return stats


async def _import_dashboards(db: AsyncSession, rows: List[Dict[str, Any]]) -> Dict[str, int]:
    stats = _new_stats()
    existing = list((await db.execute(select(Dashboard))).scalars().all())
    by_id = {d.id: d for d in existing}
    by_name = {d.name: d for d in existing}

    for row in rows or []:
        if not (row or {}).get("name"):
            stats["skipped"] += 1
            continue
        obj = by_id.get(row.get("id")) or by_name.get(row.get("name"))
        if obj is None:
            obj = Dashboard(
                **_build_kwargs(Dashboard, row, ("layout", "widgets", "data_source"))
            )
            db.add(obj)
            stats["created"] += 1
        else:
            _apply_row(obj, row, ("layout", "widgets", "data_source"), skip=("id",))
            obj.updated_at = utc_now()
            stats["updated"] += 1
    return stats


async def import_bundle(
    db: AsyncSession,
    bundle: Dict[str, Any],
    sections: Optional[Sequence[str]] = None,
    mode: str = "merge",
) -> Dict[str, Any]:
    """Apply a project bundle to the database.

    ``mode="replace"`` clears the section before importing it; ``"merge"``
    (default) only adds/updates.  Returns per-section statistics.
    """
    if not isinstance(bundle, dict):
        raise ValueError("工程文件内容不是合法的 JSON 对象")

    schema = bundle.get("schema")
    if schema and schema != SCHEMA:
        raise ValueError(f"未知的工程文件格式：{schema}")

    data = bundle.get("data")
    if not isinstance(data, dict):
        # Tolerate a bundle whose sections sit at the top level.
        data = {k: v for k, v in bundle.items() if k in SECTIONS}
    if not data:
        raise ValueError("工程文件中没有可导入的配置段")

    wanted = [s for s in (sections or SECTIONS) if s in SECTIONS and s in data]
    if not wanted:
        raise ValueError("所选配置段在工程文件中不存在")

    if mode not in ("merge", "replace"):
        raise ValueError("mode 只能是 merge 或 replace")

    results: Dict[str, Any] = {}
    for section in wanted:
        if mode == "replace":
            await _clear_section(db, section)
        rows = data.get(section) or []
        if section == "models":
            results[section] = await _import_models(db, rows)
        elif section == "devices":
            results[section] = await _import_devices(db, rows)
        elif section == "plugins":
            results[section] = await _import_plugins(db, rows)
        elif section == "skills":
            results[section] = _import_skills(rows)
        elif section == "test_cases":
            results[section] = await _import_test_cases(db, rows)
        elif section == "execution_plans":
            results[section] = await _import_execution_plans(db, rows)
        elif section == "dashboards":
            results[section] = await _import_dashboards(db, rows)

    await db.commit()
    return {"mode": mode, "sections": results}


# --------------------------------------------------------------------------- #
# Project file storage (另存为 / 重命名 / 列表 / 删除)
# --------------------------------------------------------------------------- #

def _safe_name(name: str) -> str:
    cleaned = _UNSAFE_CHARS.sub("_", (name or "").strip())
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    return cleaned or "untitled"


def _project_path(name: str) -> Path:
    return PROJECTS_DIR / f"Project_{_safe_name(name)}.json"


def _display_name(path: Path) -> str:
    stem = path.stem
    return stem[len("Project_"):] if stem.startswith("Project_") else stem


def _ensure_dir() -> None:
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)


def list_projects() -> List[Dict[str, Any]]:
    """List saved project files with a per-section summary."""
    _ensure_dir()
    items: List[Dict[str, Any]] = []
    for path in sorted(PROJECTS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        stat = path.stat()
        entry: Dict[str, Any] = {
            "name": _display_name(path),
            "file_name": path.name,
            "size": stat.st_size,
            "updated_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "counts": {},
            "project_name": _display_name(path),
            "app_version": None,
            "exported_at": None,
            "error": None,
        }
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            entry["counts"] = raw.get("counts") or {}
            entry["project_name"] = raw.get("project_name") or entry["name"]
            entry["app_version"] = raw.get("app_version")
            entry["exported_at"] = raw.get("exported_at")
        except Exception as exc:  # noqa: BLE001 - listing must survive a bad file
            entry["error"] = f"文件解析失败：{exc}"
        items.append(entry)
    return items


def save_project(name: str, bundle: Dict[str, Any]) -> Dict[str, Any]:
    """Write *bundle* to ``Project_<name>.json`` (overwrites)."""
    _ensure_dir()
    path = _project_path(name)
    bundle = dict(bundle or {})
    bundle["project_name"] = _safe_name(name)
    bundle["schema"] = SCHEMA
    bundle["schema_version"] = SCHEMA_VERSION
    path.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "name": _safe_name(name),
        "file_name": path.name,
        "path": str(path),
        "size": path.stat().st_size,
    }


def load_project(name: str) -> Dict[str, Any]:
    path = _project_path(name)
    if not path.is_file():
        raise FileNotFoundError(name)
    return json.loads(path.read_text(encoding="utf-8"))


def rename_project(name: str, new_name: str) -> Dict[str, Any]:
    path = _project_path(name)
    if not path.is_file():
        raise FileNotFoundError(name)
    target = _project_path(new_name)
    if target.is_file() and target != path:
        raise FileExistsError(new_name)

    bundle = json.loads(path.read_text(encoding="utf-8"))
    bundle["project_name"] = _safe_name(new_name)
    target.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
    if target != path:
        path.unlink()
    return {"name": _safe_name(new_name), "file_name": target.name}


def delete_project(name: str) -> bool:
    path = _project_path(name)
    if not path.is_file():
        return False
    path.unlink()
    return True
