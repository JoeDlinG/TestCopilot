"""Test case management API routes.

GET    /api/testcases              - List test cases
POST   /api/testcases              - Create test case
GET    /api/testcases/{id}         - Get test case detail
PUT    /api/testcases/{id}         - Update test case
DELETE /api/testcases/{id}         - Delete test case
POST   /api/testcases/generate     - AI generate test cases
GET    /api/testcases/{id}/flow    - Get test case flow
POST   /api/testcases/{id}/flow    - Create/update test case flow
PUT    /api/testcases/{id}/flow    - Update test case flow
"""
import json
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.models.models import TestCase, TestFlow, TestExecution, TestStepResult
from app.schemas.schemas import (
    TestCaseCreate, TestCaseResponse, TestCaseUpdateRequest,
    TestCaseGenerateRequest, TestCaseGenerateResponse,
    TestFlowCreate, TestFlowUpdate, TestFlowResponse,
)
from app.services.testgen_service import testgen_service
from app.services.codegen_service import codegen_service
from app.services.response_parser import response_parser
from app.services.trend_service import collect_parsed_series

router = APIRouter(prefix="/api/testcases", tags=["Test Cases"])


def _parse_json(value):
    """Parse JSON string from DB."""
    if value is None:
        return None
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return value
    return value


@router.post("/")
async def create_test_case(data: TestCaseCreate, db: AsyncSession = Depends(get_db)):
    test_case = TestCase(
        name=data.name,
        description=data.description,
        requirement_raw=data.requirement_raw,
        tags=json.dumps(data.tags, ensure_ascii=False) if data.tags else None,
        ai_model_id=data.ai_model_id,
    )
    db.add(test_case)
    await db.commit()
    await db.refresh(test_case)
    return {
        "code": 0, "message": "success",
        "data": {
            "id": test_case.id, "name": test_case.name,
            "description": test_case.description,
            "requirement_raw": test_case.requirement_raw,
            "status": test_case.status, "flow_id": test_case.flow_id,
            "ai_model_id": test_case.ai_model_id,
            "tags": _parse_json(test_case.tags),
            "created_at": test_case.created_at.isoformat() if test_case.created_at else None,
            "updated_at": test_case.updated_at.isoformat() if test_case.updated_at else None,
        },
    }


@router.get("/")
async def list_test_cases(
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    query = select(TestCase)
    count_query = select(TestCase)

    if status:
        query = query.where(TestCase.status == status)
        count_query = count_query.where(TestCase.status == status)

    count_result = await db.execute(count_query)
    total = len(count_result.scalars().all())

    query = query.order_by(TestCase.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    test_cases = result.scalars().all()

    items = []
    for tc in test_cases:
        items.append({
            "id": tc.id, "name": tc.name, "description": tc.description,
            "requirement_raw": tc.requirement_raw, "status": tc.status,
            "flow_id": tc.flow_id, "ai_model_id": tc.ai_model_id,
            "tags": _parse_json(tc.tags),
            "created_at": tc.created_at.isoformat() if tc.created_at else None,
            "updated_at": tc.updated_at.isoformat() if tc.updated_at else None,
        })

    return {
        "code": 0, "message": "success",
        "data": {"items": items, "total": total, "page": page, "page_size": page_size},
    }


@router.get("/{test_case_id}")
async def get_test_case(test_case_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(TestCase).where(TestCase.id == test_case_id))
    tc = result.scalar_one_or_none()
    if not tc:
        raise HTTPException(status_code=404, detail={
            "code": 40004, "message": "Test case not found",
            "detail": f"No test case with id={test_case_id}",
        })

    return {
        "code": 0, "message": "success",
        "data": {
            "id": tc.id, "name": tc.name, "description": tc.description,
            "requirement_raw": tc.requirement_raw, "status": tc.status,
            "flow_id": tc.flow_id, "ai_model_id": tc.ai_model_id,
            "tags": _parse_json(tc.tags),
            "created_at": tc.created_at.isoformat() if tc.created_at else None,
            "updated_at": tc.updated_at.isoformat() if tc.updated_at else None,
        },
    }


@router.put("/{test_case_id}")
async def update_test_case(
    test_case_id: str, data: TestCaseUpdateRequest, db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(TestCase).where(TestCase.id == test_case_id))
    tc = result.scalar_one_or_none()
    if not tc:
        raise HTTPException(status_code=404, detail={
            "code": 40004, "message": "Test case not found",
            "detail": f"No test case with id={test_case_id}",
        })

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        if key == "tags" and value is not None:
            setattr(tc, key, json.dumps(value, ensure_ascii=False))
        elif value is not None:
            setattr(tc, key, value)

    await db.commit()
    await db.refresh(tc)

    return {
        "code": 0, "message": "success",
        "data": {
            "id": tc.id, "name": tc.name, "description": tc.description,
            "status": tc.status, "flow_id": tc.flow_id,
            "tags": _parse_json(tc.tags),
            "created_at": tc.created_at.isoformat() if tc.created_at else None,
            "updated_at": tc.updated_at.isoformat() if tc.updated_at else None,
        },
    }


@router.delete("/{test_case_id}")
async def delete_test_case(test_case_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(TestCase).where(TestCase.id == test_case_id))
    tc = result.scalar_one_or_none()
    if not tc:
        raise HTTPException(status_code=404, detail={
            "code": 40004, "message": "Test case not found",
            "detail": f"No test case with id={test_case_id}",
        })

    # Delete associated flow first
    flow_result = await db.execute(select(TestFlow).where(TestFlow.testcase_id == test_case_id))
    flow = flow_result.scalar_one_or_none()
    if flow:
        await db.delete(flow)

    await db.delete(tc)
    await db.commit()
    return {"code": 0, "message": "Test case deleted", "data": None}


# ============ AI Generation ============

@router.post("/generate")
async def generate_test_cases(data: TestCaseGenerateRequest, db: AsyncSession = Depends(get_db)):
    try:
        result = await testgen_service.generate_and_save(
            db,
            requirements=data.requirements,
            model_id=data.model_id,
            available_devices=data.available_devices,
            input_type=data.input_type,
            skill_protocols=data.skill_protocols,
        )
        return {"code": 0, "message": "success", "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail={
            "code": 40007, "message": "Generation failed", "detail": str(e),
        })


# ============ Import AI-Generated Test Cases (with flows) ============

@router.post("/import-ai-result")
async def import_ai_result(data: dict, db: AsyncSession = Depends(get_db)):
    """Import AI-generated test cases and create flows for each.

    Request body: {"test_cases": [...], "requirements": "...", "model_id": "..."}
    Each test case: {"name", "description", "steps", "expected_result", ...}
    """
    try:
        test_cases_data = data.get("test_cases", [])
        result = await testgen_service.import_from_ai(
            db,
            test_cases_data=test_cases_data,
            requirements=data.get("requirements", ""),
            model_id=data.get("model_id"),
        )
        return {"code": 0, "message": "success", "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail={
            "code": 40007, "message": "Import failed", "detail": str(e),
        })


# ============ Flow Management ============

@router.get("/{test_case_id}/flow")
async def get_test_flow(test_case_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(TestFlow).where(TestFlow.testcase_id == test_case_id))
    flow = result.scalar_one_or_none()
    if not flow:
        raise HTTPException(status_code=404, detail={
            "code": 40004, "message": "Flow not found",
            "detail": f"No flow for test case {test_case_id}",
        })

    return {
        "code": 0, "message": "success",
        "data": {
            "id": flow.id, "testcase_id": flow.testcase_id,
            "nodes": _parse_json(flow.nodes), "edges": _parse_json(flow.edges),
            "viewport": _parse_json(flow.viewport),
            "created_at": flow.created_at.isoformat() if flow.created_at else None,
            "updated_at": flow.updated_at.isoformat() if flow.updated_at else None,
        },
    }


@router.post("/{test_case_id}/flow")
async def create_test_flow(
    test_case_id: str, data: TestFlowCreate, db: AsyncSession = Depends(get_db),
):
    _validate_parser_names(data.nodes)

    # Verify test case exists
    tc_result = await db.execute(select(TestCase).where(TestCase.id == test_case_id))
    if not tc_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail={
            "code": 40004, "message": "Test case not found",
        })

    # Check for existing flow
    existing = await db.execute(select(TestFlow).where(TestFlow.testcase_id == test_case_id))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail={
            "code": 40010, "message": "Flow already exists for this test case",
        })

    flow = TestFlow(
        testcase_id=test_case_id,
        nodes=json.dumps(data.nodes, ensure_ascii=False),
        edges=json.dumps(data.edges, ensure_ascii=False),
        viewport=json.dumps(data.viewport, ensure_ascii=False) if data.viewport else None,
    )
    db.add(flow)
    await db.commit()
    await db.refresh(flow)

    # Link flow to test case
    tc_refresh = await db.execute(select(TestCase).where(TestCase.id == test_case_id))
    tc = tc_refresh.scalar_one_or_none()
    if tc:
        tc.flow_id = flow.id
        await db.commit()

    return {
        "code": 0, "message": "success",
        "data": {
            "id": flow.id, "testcase_id": flow.testcase_id,
            "nodes": data.nodes, "edges": data.edges,
            "viewport": data.viewport,
        },
    }


@router.put("/{test_case_id}/flow")
async def update_test_flow(
    test_case_id: str, data: TestFlowUpdate, db: AsyncSession = Depends(get_db),
):
    _validate_parser_names(data.nodes)

    result = await db.execute(select(TestFlow).where(TestFlow.testcase_id == test_case_id))
    flow = result.scalar_one_or_none()
    if not flow:
        raise HTTPException(status_code=404, detail={
            "code": 40004, "message": "Flow not found",
        })

    if data.nodes is not None:
        flow.nodes = json.dumps(data.nodes, ensure_ascii=False)
    if data.edges is not None:
        flow.edges = json.dumps(data.edges, ensure_ascii=False)
    if data.viewport is not None:
        flow.viewport = json.dumps(data.viewport, ensure_ascii=False)

    await db.commit()
    await db.refresh(flow)

    return {
        "code": 0, "message": "success",
        "data": {
            "id": flow.id, "testcase_id": flow.testcase_id,
            "nodes": _parse_json(flow.nodes), "edges": _parse_json(flow.edges),
            "viewport": _parse_json(flow.viewport),
        },
    }


# ============ Result Parsing ============

def _validate_parser_names(nodes: Optional[List[Dict[str, Any]]]) -> None:
    """Parsed field names must be unique across the whole test case.

    A name is how a parsed value is identified in the trend view, so a
    duplicate would be ambiguous - reject it and let the user rename.
    """
    if not nodes:
        return
    seen: Dict[str, str] = {}  # name -> owning step label
    for node in nodes:
        cfg = node.get("config") or {}
        label = (
            (node.get("data") or {}).get("label")
            or node.get("label")
            or str(node.get("id") or "?")
        )
        for spec in cfg.get("parsers") or []:
            name = str(spec.get("name") or "").strip()
            if not name:
                raise HTTPException(status_code=400, detail={
                    "code": 40011,
                    "message": f"步骤「{label}」的解析项名称不能为空",
                })
            if name in seen:
                raise HTTPException(status_code=400, detail={
                    "code": 40012,
                    "message": (
                        f"解析项名称「{name}」重复"
                        f"（步骤「{seen[name]}」与「{label}」），请重新命名"
                    ),
                })
            seen[name] = label


# ============ Result Parsing Preview ============

@router.post("/parse-preview")
async def preview_result_parsing(payload: dict):
    """Preview how a raw response would be parsed and judged.

    Lets the configuration UI show the parsed value and PASS/FAIL verdict
    immediately, using exactly the engine that the execution will use.
    """
    raw = payload.get("raw", "")
    parsers = payload.get("parsers") or []
    try:
        parsed = response_parser.parse_all(raw, parsers)
    except Exception as e:  # never let a bad config break the UI
        raise HTTPException(status_code=400, detail={
            "code": 40010, "message": f"解析配置无效: {e}",
        })
    all_passed, summary = response_parser.summarize(parsed)
    # the exact bytes the parser slices, shown in the UI so the user can see
    # what "start/length" really points at
    data_bytes = response_parser.to_bytes(raw)
    return {
        "code": 0, "message": "success",
        "data": {
            "parsed": parsed,
            "all_passed": all_passed,
            "summary": summary,
            "raw_bytes": list(data_bytes),
            "raw_bytes_hex": " ".join(f"{b:02X}" for b in data_bytes),
            "empty_frame": response_parser.is_empty_frame(raw),
        },
    }


@router.get("/{test_case_id}/parsed-trend")
async def get_parsed_trend(
    test_case_id: str,
    limit: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    """Historical trend of parsed result values for a test case.

    Values are read back from the ``parsed_results`` already stored on each
    step, so no separate metrics table is needed. ``num`` is the numeric view
    used for plotting (null for values that are not numeric, e.g. strings).
    """
    data = await collect_parsed_series(db, test_case_id, limit=limit)
    return {"code": 0, "message": "success", "data": data}

    step_rows = await db.execute(
        select(TestStepResult)
        .where(
            TestStepResult.execution_id.in_(exec_ids),
            TestStepResult.parsed_results.isnot(None),
        )
        .order_by(TestStepResult.step_index.asc())
    )
    steps = list(step_rows.scalars().all())

    def _samples_of(parsed: Any) -> List[List[Dict[str, Any]]]:
        """``parsed_results`` is either the new per-reply series object or the
        legacy flat list (one sample)."""
        if isinstance(parsed, dict):
            samples = parsed.get("samples")
            if isinstance(samples, list) and samples:
                return [s for s in samples if isinstance(s, list)]
            last = parsed.get("last")
            return [last] if isinstance(last, list) else []
        if isinstance(parsed, list):
            return [parsed]
        return []

    series: Dict[str, List[Dict[str, Any]]] = {}
    for s in steps:
        try:
            parsed = json.loads(s.parsed_results or "[]")
        except (TypeError, ValueError):
            continue
        samples = _samples_of(parsed)
        if not samples:
            continue
        meta = exec_meta.get(s.execution_id, {})
        # one point per reply, so a step that repeated a command N times
        # contributes N points instead of a single collapsed one
        for seq, sample in enumerate(samples):
            for p in sample:
                if not isinstance(p, dict):
                    continue
                name = str(p.get("name") or "").strip()
                if not name:
                    continue
                value = p.get("value")
                num = response_parser.to_number(value)
                series.setdefault(name, []).append({
                    "execution_id": s.execution_id,
                    "step_index": s.step_index,
                    "seq": seq,
                    "total": len(samples),
                    "completed_at": s.completed_at.isoformat() if s.completed_at else None,
                    "started_at": meta.get("started_at"),
                    "value": value,
                    "num": num,
                    "ok": bool(p.get("ok")),
                    "status": p.get("status") or ("ok" if p.get("ok") else "fail"),
                    "detail": p.get("detail"),
                })

    # keep each field's points in chronological order
    order = {e[0]: i for i, e in enumerate(executions)}
    for points in series.values():
        points.sort(
            key=lambda pt: (
                order.get(pt["execution_id"], 0), pt["step_index"], pt["seq"]
            )
        )

    return {
        "code": 0, "message": "success",
        "data": {
            "fields": list(series.keys()),
            "series": series,
            "executions": [
                {"id": e[0], **exec_meta[e[0]]} for e in executions
            ],
            "total_points": sum(len(v) for v in series.values()),
        },
    }


# ============ Code Generation ============

@router.post("/{test_case_id}/generate-code")
async def generate_flow_code(test_case_id: str, db: AsyncSession = Depends(get_db)):
    """Generate executable Python code from a test case's flowchart."""
    tc_result = await db.execute(select(TestCase).where(TestCase.id == test_case_id))
    tc = tc_result.scalar_one_or_none()
    if not tc:
        raise HTTPException(status_code=404, detail={
            "code": 40004, "message": "Test case not found",
        })

    flow_result = await db.execute(select(TestFlow).where(TestFlow.testcase_id == test_case_id))
    flow = flow_result.scalar_one_or_none()
    if not flow:
        raise HTTPException(status_code=404, detail={
            "code": 40004, "message": "Flow not found — save a flowchart first",
        })

    nodes = _parse_json(flow.nodes) or []
    edges = _parse_json(flow.edges) or []

    code = codegen_service.generate_python(nodes, edges, test_case_name=tc.name)
    summary = codegen_service.generate_json_summary(nodes, edges, name=tc.name)

    return {
        "code": 0, "message": "success",
        "data": {
            "test_case_id": test_case_id,
            "test_case_name": tc.name,
            "code": code,
            "summary": summary,
        },
    }
