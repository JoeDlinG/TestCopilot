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
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.models.models import TestCase, TestFlow
from app.schemas.schemas import (
    TestCaseCreate, TestCaseResponse, TestCaseUpdateRequest,
    TestCaseGenerateRequest, TestCaseGenerateResponse,
    TestFlowCreate, TestFlowUpdate, TestFlowResponse,
)
from app.services.testgen_service import testgen_service

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
        )
        return {"code": 0, "message": "success", "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail={
            "code": 40007, "message": "Generation failed", "detail": str(e),
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
