"""DBC import / browse / signal-to-parser-spec service (Issue #24)."""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.models import DbcFile, DbcMessage, DbcSignal
from app.services.dbc_parser import (
    parse_dbc,
    signal_to_parser_spec,
    decode_signal,
)


def _sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _signal_to_dict(sig: DbcSignal) -> Dict[str, Any]:
    out = {
        "id": sig.id,
        "name": sig.name,
        "start": sig.start,
        "length": sig.length,
        "byte_order": sig.byte_order,
        "is_signed": sig.is_signed,
        "factor": sig.factor,
        "offset": sig.offset,
        "physical_unit": sig.physical_unit,
        "multiplexer": sig.multiplexer,
        "comment": sig.comment,
    }
    for field in ("receivers", "choices"):
        raw = getattr(sig, field)
        if raw:
            try:
                out[field] = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                out[field] = []
        else:
            out[field] = []
    if sig.min_value is not None:
        out["min"] = sig.min_value
    if sig.max_value is not None:
        out["max"] = sig.max_value
    return out


def _message_to_dict(msg: DbcMessage, include_signals: bool = True) -> Dict[str, Any]:
    out = {
        "id": msg.id,
        "message_id": msg.message_id,
        "name": msg.name,
        "dlc": msg.dlc,
        "sender": msg.sender,
        "comment": msg.comment,
    }
    if include_signals:
        out["signals"] = [_signal_to_dict(s) for s in msg.signals]
    return out


class DbcService:
    async def import_dbc(self, db: AsyncSession, content: str, filename: Optional[str] = None) -> Dict[str, Any]:
        """Parse + persist a DBC file, de-duplicated by content hash."""
        content = content or ""
        digest = _sha256(content)

        existing = (await db.execute(
            select(DbcFile).where(DbcFile.sha256 == digest)
        )).scalars().first()
        if existing is not None:
            return {"id": existing.id, "name": existing.name, "duplicate": True}

        parsed = parse_dbc(content)
        name = filename or "untitled.dbc"
        if name.endswith(".dbc"):
            name = name[:-4]

        dbf = DbcFile(
            name=name,
            filename=filename,
            sha256=digest,
            content=content,
            message_count=len(parsed["messages"]),
            signal_count=sum(len(m["signals"]) for m in parsed["messages"]),
        )
        db.add(dbf)
        await db.flush()  # assign dbf.id

        for m in parsed["messages"]:
            dbm = DbcMessage(
                file_id=dbf.id,
                message_id=m["id"],
                name=m["name"],
                dlc=m["length"],
                sender=m.get("sender"),
                comment=m.get("comment") or None,
            )
            db.add(dbm)
            await db.flush()

            for s in m["signals"]:
                db.add(DbcSignal(
                    message_id_fk=dbm.id,
                    name=s["name"],
                    start=s["start"],
                    length=s["length"],
                    byte_order=s["byte_order"],
                    is_signed=s["is_signed"],
                    factor=s["factor"],
                    offset=s["offset"],
                    min_value=s["min"],
                    max_value=s["max"],
                    physical_unit=s.get("unit") or None,
                    receivers=json.dumps(s.get("receivers") or [], ensure_ascii=False),
                    multiplexer=s.get("multiplexer"),
                    comment=s.get("comment") or None,
                    choices=json.dumps(
                        [{"value": v, "text": t} for v, t in (s.get("choices") or [])],
                        ensure_ascii=False,
                    ),
                ))
        await db.commit()
        await db.refresh(dbf)
        return {"id": dbf.id, "name": dbf.name, "duplicate": False}

    async def list_files(self, db: AsyncSession) -> List[Dict[str, Any]]:
        rows = (await db.execute(
            select(DbcFile).order_by(DbcFile.created_at.desc())
        )).scalars().all()
        return [{
            "id": f.id,
            "name": f.name,
            "filename": f.filename,
            "message_count": f.message_count,
            "signal_count": f.signal_count,
            "created_at": f.created_at.isoformat() if f.created_at else None,
        } for f in rows]

    async def get_file(self, db: AsyncSession, file_id: str) -> Optional[Dict[str, Any]]:
        f = (await db.execute(
            select(DbcFile).where(DbcFile.id == file_id)
        )).scalars().first()
        if f is None:
            return None
        msgs = (await db.execute(
            select(DbcMessage).where(DbcMessage.file_id == file_id)
            .options(selectinload(DbcMessage.signals))
        )).scalars().all()
        return {
            "id": f.id,
            "name": f.name,
            "filename": f.filename,
            "message_count": f.message_count,
            "signal_count": f.signal_count,
            "created_at": f.created_at.isoformat() if f.created_at else None,
            "messages": [_message_to_dict(m, include_signals=True) for m in msgs],
        }

    async def get_message(self, db: AsyncSession, message_id: str) -> Optional[Dict[str, Any]]:
        m = (await db.execute(
            select(DbcMessage).where(DbcMessage.id == message_id)
            .options(selectinload(DbcMessage.signals))
        )).scalars().first()
        return _message_to_dict(m, include_signals=True) if m else None

    async def get_signal(self, db: AsyncSession, signal_id: str) -> Optional[Dict[str, Any]]:
        s = (await db.execute(
            select(DbcSignal).where(DbcSignal.id == signal_id)
        )).scalars().first()
        return _signal_to_dict(s) if s else None

    async def signal_parser_spec(self, db: AsyncSession, signal_id: str) -> Optional[Dict[str, Any]]:
        """Build a platform ParserSpec from a stored DBC signal."""
        s = (await db.execute(
            select(DbcSignal).where(DbcSignal.id == signal_id)
        )).scalars().first()
        if s is None:
            return None
        msg = (await db.execute(
            select(DbcMessage).where(DbcMessage.id == s.message_id_fk)
        )).scalars().first()
        return signal_to_parser_spec(_signal_to_dict(s), message_id=msg.message_id if msg else None)

    async def search(self, db: AsyncSession, file_id: str, query: str) -> List[Dict[str, Any]]:
        """Search messages/signals by name (case-insensitive substring)."""
        q = (query or "").strip().lower()
        data = await self.get_file(db, file_id)
        if data is None:
            return []
        results: List[Dict[str, Any]] = []
        if not q:
            for m in data["messages"]:
                results.append({"type": "message", "message_id": m["message_id"], "name": m["name"]})
            return results
        for m in data["messages"]:
            if q in m["name"].lower():
                results.append({"type": "message", "message_id": m["message_id"], "name": m["name"]})
            for s in m["signals"]:
                if q in s["name"].lower():
                    results.append({
                        "type": "signal",
                        "message_id": m["message_id"],
                        "message_name": m["name"],
                        "name": s["name"],
                        "signal_id": s["id"],
                    })
        return results

    @staticmethod
    def preview_decode(signal: Dict[str, Any], payload: bytes) -> Optional[float]:
        """Decode a raw payload with a stored signal (reuses dbc_parser)."""
        return decode_signal(
            payload,
            signal.get("start", 0),
            signal.get("length", 8),
            signal.get("byte_order", "little_endian"),
            signal.get("is_signed", False),
            signal.get("factor", 1.0),
            signal.get("offset", 0.0),
        )


dbc_service = DbcService()
