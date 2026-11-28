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
import math
import os
import re
from typing import Optional, Tuple

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.dbc_service import dbc_service
from app.services.dbc_parser import decode_signal

router = APIRouter(prefix="/api/dbc", tags=["DBC"])

# A DBC is a text file; 5 MiB is already far larger than any real CAN database.
# Without a cap, one upload allocates bytes + str + sha256 + a Text column.
_MAX_DBC_BYTES = 5 * 1024 * 1024
_MAX_PREVIEW_BYTES = 4096


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


def _decode_dbc_bytes(data: bytes) -> Tuple[str, str]:
    """Decode a DBC upload, reporting which encoding was used.

    Vendor DBCs are frequently CP1252 / GBK rather than UTF-8. Decoding with
    ``errors="replace"`` used to import "successfully" while permanently
    corrupting every non-ASCII comment, unit and node name.
    """
    if data.startswith(b"\xef\xbb\xbf"):
        try:
            return data[3:].decode("utf-8"), "utf-8-sig"
        except UnicodeDecodeError:
            pass
    for encoding in ("utf-8", "gbk", "cp1252"):
        try:
            return data.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1"), "latin-1"


def _bad_import(exc: Exception) -> HTTPException:
    """Turn parse/persistence failures into a client-facing 400, not a 500."""
    if isinstance(exc, ValueError):
        return HTTPException(status_code=400, detail=str(exc))
    return HTTPException(
        status_code=400,
        detail=f"DBC 导入失败（数值超出范围或数据库约束冲突）: {exc}",
    )


def _check_size(size: int) -> None:
    if size > _MAX_DBC_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"DBC 文件过大：{size} 字节，上限 {_MAX_DBC_BYTES} 字节",
        )


@router.post("/import")
async def import_dbc(payload: DbcImportRequest, db: AsyncSession = Depends(get_db)):
    _check_size(len(payload.content.encode("utf-8", errors="replace")))
    try:
        return await dbc_service.import_dbc(db, payload.content, payload.filename)
    except (ValueError, SQLAlchemyError, OverflowError) as e:
        raise _bad_import(e)


@router.post("/upload")
async def upload_dbc(file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
    chunks, total = [], 0
    while True:
        chunk = await file.read(64 * 1024)
        if not chunk:
            break
        total += len(chunk)
        _check_size(total)
        chunks.append(chunk)
    content = b"".join(chunks)
    if not content:
        raise HTTPException(status_code=400, detail="上传的 DBC 文件为空")

    text, encoding = _decode_dbc_bytes(content)
    try:
        result = await dbc_service.import_dbc(
            db, text, os.path.basename(file.filename or "untitled.dbc")
        )
    except (ValueError, SQLAlchemyError, OverflowError) as e:
        raise _bad_import(e)
    if encoding != "utf-8":
        result = {
            **result,
            "encoding": encoding,
            "warning": f"文件非 UTF-8，已按 {encoding} 解码导入",
        }
    return result


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
    if not math.isfinite(payload.factor) or not math.isfinite(payload.offset):
        raise HTTPException(status_code=400, detail="factor / offset 必须是有限数值")
    # Accept the formats engineers paste: "11 22", "0x1122", "11:22:33", CRLF.
    hex_text = re.sub(r"0[xX]", "", payload.payload_hex)
    hex_text = re.sub(r"[^0-9a-fA-F]", "", hex_text)
    if not hex_text or len(hex_text) % 2:
        raise HTTPException(status_code=400, detail="payload_hex 不是合法十六进制")
    if len(hex_text) // 2 > _MAX_PREVIEW_BYTES:
        raise HTTPException(status_code=400, detail="payload_hex 过长")
    try:
        data = bytes.fromhex(hex_text)
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
        raise HTTPException(status_code=400, detail="负载长度不足以解出该信号，或数值非法")
    return {"value": value}
