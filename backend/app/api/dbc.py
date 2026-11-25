"""CAN DBC import / browse / signal-to-parser-spec API (Issue #24).

POST   /api/dbc/import                 - import DBC from JSON {filename, content}
POST   /api/dbc/upload                 - import DBC from a multipart file upload
GET    /api/dbc/files                  - list imported DBC files
GET    /api/dbc/files/{id}             - one file with messages + signals
GET    /api/dbc/files/{id}/search?q=   - search messages/signals by name
GET    /api/dbc/messages/{id}          - one message with its signals
GET    /api/dbc/signals/{id}           - one signal
POST   /api/dbc/signals/{id}/parser-spec - generate a platform ParserSpec
POST   /api/dbc/preview                - decode a hex payload against a signal
"""
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.dbc_service import dbc_service
from app.services.dbc_parser import decode_signal

router = APIRouter(prefix="/api/dbc", tags=["DBC"])


class DbcImportRequest(BaseModel):
    filename: Optional[str] = None
    content: str


class DbcPreviewRequest(BaseModel):
    byte_order: str = "little_endian"
    start: int = 0
    length: int = 8
    is_signed: bool = False
    factor: float = 1.0
    offset: float = 0.0
    payload_hex: str = ""


@router.post("/import")
async def import_dbc(payload: DbcImportRequest, db: AsyncSession = Depends(get_db)):
    try:
        result = await dbc_service.import_dbc(db, payload.content, payload.filename)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return result


@router.post("/upload")
async def upload_dbc(file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
    content = await file.read()
    text = content.decode("utf-8", errors="replace")
    try:
        return await dbc_service.import_dbc(db, text, file.filename)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/files")
async def list_files(db: AsyncSession = Depends(get_db)):
    return await dbc_service.list_files(db)


@router.get("/files/{file_id}")
async def get_file(file_id: str, db: AsyncSession = Depends(get_db)):
    data = await dbc_service.get_file(db, file_id)
    if data is None:
        raise HTTPException(status_code=404, detail="DBC 文件不存在")
    return data


@router.get("/files/{file_id}/search")
async def search_file(file_id: str, q: str = "", db: AsyncSession = Depends(get_db)):
    return await dbc_service.search(db, file_id, q)


@router.get("/messages/{message_id}")
async def get_message(message_id: str, db: AsyncSession = Depends(get_db)):
    data = await dbc_service.get_message(db, message_id)
    if data is None:
        raise HTTPException(status_code=404, detail="DBC 报文不存在")
    return data


@router.get("/signals/{signal_id}")
async def get_signal(signal_id: str, db: AsyncSession = Depends(get_db)):
    data = await dbc_service.get_signal(db, signal_id)
    if data is None:
        raise HTTPException(status_code=404, detail="DBC 信号不存在")
    return data


@router.post("/signals/{signal_id}/parser-spec")
async def signal_parser_spec(signal_id: str, db: AsyncSession = Depends(get_db)):
    spec = await dbc_service.signal_parser_spec(db, signal_id)
    if spec is None:
        raise HTTPException(status_code=404, detail="DBC 信号不存在")
    return spec


@router.post("/preview")
async def preview_decode(payload: DbcPreviewRequest):
    try:
        data = bytes.fromhex(payload.payload_hex.replace(" ", ""))
    except ValueError:
        raise HTTPException(status_code=400, detail="payload_hex 不是合法十六进制")
    value = decode_signal(
        data,
        payload.start,
        payload.length,
        payload.byte_order,
        payload.is_signed,
        payload.factor,
        payload.offset,
    )
    if value is None:
        raise HTTPException(status_code=400, detail="负载长度不足以解出该信号")
    return {"value": value}
