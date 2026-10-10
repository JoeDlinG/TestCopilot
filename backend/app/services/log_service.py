"""Communication log service — querying, filtering, and exporting logs."""
from __future__ import annotations
import csv
import io
import json
from datetime import datetime
from typing import Optional, List, Tuple

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.models.models import CommunicationLog
from app.core.config import settings

import logging
from app.core.timeutils import utc_now
logger = logging.getLogger(__name__)


class LogService:
    """Service for communication log management."""

    async def query_logs(
        self,
        db: AsyncSession,
        device_id: Optional[str] = None,
        execution_id: Optional[str] = None,
        protocol: Optional[str] = None,
        direction: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> Tuple[List[CommunicationLog], int]:
        query = select(CommunicationLog)
        count_query = select(func.count(CommunicationLog.id))

        if device_id:
            query = query.where(CommunicationLog.device_id == device_id)
            count_query = count_query.where(CommunicationLog.device_id == device_id)
        if execution_id:
            query = query.where(CommunicationLog.execution_id == execution_id)
            count_query = count_query.where(CommunicationLog.execution_id == execution_id)
        if protocol:
            query = query.where(CommunicationLog.protocol == protocol)
            count_query = count_query.where(CommunicationLog.protocol == protocol)
        if direction:
            query = query.where(CommunicationLog.direction == direction)
            count_query = count_query.where(CommunicationLog.direction == direction)
        if start_time:
            query = query.where(CommunicationLog.timestamp >= start_time)
            count_query = count_query.where(CommunicationLog.timestamp >= start_time)
        if end_time:
            query = query.where(CommunicationLog.timestamp <= end_time)
            count_query = count_query.where(CommunicationLog.timestamp <= end_time)

        # Count
        count_result = await db.execute(count_query)
        total = count_result.scalar() or 0

        # Paginate
        query = query.order_by(CommunicationLog.timestamp.desc())
        query = query.offset((page - 1) * page_size).limit(page_size)
        result = await db.execute(query)
        logs = result.scalars().all()

        return logs, total

    async def get_log(self, db: AsyncSession, log_id: str) -> Optional[CommunicationLog]:
        result = await db.execute(
            select(CommunicationLog).where(CommunicationLog.id == log_id)
        )
        return result.scalar_one_or_none()

    async def export_csv(
        self,
        db: AsyncSession,
        device_id: Optional[str] = None,
        execution_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> tuple[io.StringIO, str]:
        """Export logs as CSV.

        Rows are fetched in batches (default 5000) so memory stays bounded even
        for very large result sets — 大数据量导出性能优化（不再一次性全量加载）。
        """
        query = select(CommunicationLog).order_by(CommunicationLog.timestamp.desc())

        if device_id:
            query = query.where(CommunicationLog.device_id == device_id)
        if execution_id:
            query = query.where(CommunicationLog.execution_id == execution_id)
        if start_time:
            query = query.where(CommunicationLog.timestamp >= start_time)
        if end_time:
            query = query.where(CommunicationLog.timestamp <= end_time)

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "ID", "Timestamp", "Device ID", "Execution ID", "Step Result ID",
            "Direction", "Protocol", "Raw Data", "Data Hex", "Data Size",
            "Status", "Error", "Duration (ms)", "Metadata",
        ])

        batch_size = 5000
        offset = 0
        while True:
            batch_q = query.offset(offset).limit(batch_size)
            result = await db.execute(batch_q)
            logs = result.scalars().all()
            if not logs:
                break
            for log in logs:
                metadata_str = log.extra_meta or ""
                writer.writerow([
                    log.id,
                    log.timestamp.isoformat() if log.timestamp else "",
                    log.device_id,
                    log.execution_id or "",
                    log.step_result_id or "",
                    log.direction,
                    log.protocol,
                    log.raw_data,
                    log.raw_data_hex or "",
                    log.raw_data_size or "",
                    log.status,
                    log.error_message or "",
                    log.duration_ms or "",
                    metadata_str,
                ])
            if len(logs) < batch_size:
                break
            offset += batch_size

        output.seek(0)
        filename = f"communication_logs_{utc_now().strftime('%Y%m%d_%H%M%S')}.csv"
        return output, filename


log_service = LogService()
