"""Report generation service — uses Jinja2 templates for HTML/PDF/Markdown reports."""
from __future__ import annotations
import json
import os
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.models import TestReport, ReportTemplate, TestExecution, TestStepResult, ReportStatus
from app.core.config import settings
from app.core.timeutils import utc_now

logger = logging.getLogger(__name__)


class ReportService:
    """Service for test report generation."""

    async def generate_report(
        self,
        db: AsyncSession,
        title: str,
        execution_id: str,
        template_id: Optional[str] = None,
        fields: Optional[Dict[str, Any]] = None,
        format: str = "pdf",
    ) -> TestReport:
        # Get execution data
        exec_result = await db.execute(
            select(TestExecution).where(TestExecution.id == execution_id)
        )
        execution = exec_result.scalar_one_or_none()
        if not execution:
            raise ValueError(f"Execution {execution_id} not found")

        # Get step results
        steps_result = await db.execute(
            select(TestStepResult)
            .where(TestStepResult.execution_id == execution_id)
            .order_by(TestStepResult.step_index)
        )
        steps = steps_result.scalars().all()

        # Get template if specified
        template = None
        if template_id:
            tpl_result = await db.execute(
                select(ReportTemplate).where(ReportTemplate.id == template_id)
            )
            template = tpl_result.scalar_one_or_none()

        # Create report record
        report = TestReport(
            title=title,
            execution_id=execution_id,
            template_id=template_id,
            format=format,
            status=ReportStatus.GENERATING.value,
            fields=json.dumps(fields, ensure_ascii=False) if fields else None,
        )
        db.add(report)
        await db.commit()
        await db.refresh(report)

        try:
            # Build report content
            content = {
                "title": title,
                "execution_id": execution_id,
                "execution_status": execution.status,
                "execution_result": execution.result,
                "total_steps": execution.total_steps,
                "passed_steps": execution.passed_steps,
                "failed_steps": execution.failed_steps,
                "duration_ms": execution.duration_ms,
                "started_at": execution.started_at.isoformat() if execution.started_at else None,
                "completed_at": execution.completed_at.isoformat() if execution.completed_at else None,
                "steps": [
                    {
                        "index": s.step_index,
                        "label": s.label,
                        "status": s.status,
                        "command": s.command,
                        "expected": s.expected,
                        "actual": s.actual,
                        "error": s.error_message,
                        "duration_ms": s.duration_ms,
                    }
                    for s in steps
                ],
                "custom_fields": fields or {},
            }

            # Generate file
            if format == "csv":
                file_path = self._generate_csv(report.id, content)
            elif format == "html":
                file_path = self._generate_html(report.id, content, template)
            else:
                file_path = self._generate_html(report.id, content, template)  # Default to HTML

            report.file_path = file_path
            report.file_size = os.path.getsize(file_path) if os.path.exists(file_path) else 0
            report.status = ReportStatus.GENERATED.value
            report.generated_at = utc_now()
            await db.commit()
            await db.refresh(report)

            return report
        except Exception as e:
            logger.error(f"Report generation failed: {e}")
            report.status = ReportStatus.FAILED.value
            report.error_message = str(e)
            await db.commit()
            raise

    def _generate_csv(self, report_id: str, content: dict) -> str:
        import csv
        os.makedirs(settings.REPORT_DIR, exist_ok=True)
        file_path = os.path.join(settings.REPORT_DIR, f"{report_id}.csv")

        with open(file_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["Report", content["title"]])
            writer.writerow(["Execution ID", content["execution_id"]])
            writer.writerow(["Status", content["execution_status"]])
            writer.writerow(["Result", content["execution_result"]])
            writer.writerow(["Passed", content["passed_steps"]])
            writer.writerow(["Failed", content["failed_steps"]])
            writer.writerow(["Duration (ms)", content["duration_ms"]])
            writer.writerow([])
            writer.writerow(["Step", "Label", "Status", "Command", "Expected", "Actual", "Error", "Duration (ms)"])
            for step in content["steps"]:
                writer.writerow([
                    step["index"], step["label"], step["status"],
                    step["command"], step["expected"], step["actual"],
                    step["error"], step["duration_ms"],
                ])

        return file_path

    def _generate_html(self, report_id: str, content: dict, template: Optional[ReportTemplate] = None) -> str:
        os.makedirs(settings.REPORT_DIR, exist_ok=True)
        file_path = os.path.join(settings.REPORT_DIR, f"{report_id}.html")

        passed_pct = 0
        if content["total_steps"] > 0:
            passed_pct = (content["passed_steps"] / content["total_steps"]) * 100

        # Build step rows
        step_rows = ""
        for step in content["steps"]:
            status_color = {
                "passed": "#52c41a", "failed": "#ff4d4f",
                "error": "#faad14", "skipped": "#d9d9d9",
                "running": "#1890ff",
            }.get(step["status"], "#000")

            step_rows += f"""
            <tr>
                <td>{step["index"]}</td>
                <td>{step["label"]}</td>
                <td style="color:{status_color};font-weight:bold">{step["status"].upper()}</td>
                <td><code>{step["command"] or "-"}</code></td>
                <td>{step["expected"] or "-"}</td>
                <td>{step["actual"] or "-"}</td>
                <td style="color:#ff4d4f">{step["error"] or ""}</td>
                <td>{step["duration_ms"] or "-"} ms</td>
            </tr>"""

        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>{content["title"]}</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
               max-width: 1000px; margin: 0 auto; padding: 20px; color: #333; }}
        h1 {{ color: #1a1a2e; border-bottom: 3px solid #1890ff; padding-bottom: 10px; }}
        .summary {{ display: flex; gap: 20px; margin: 20px 0; flex-wrap: wrap; }}
        .summary-card {{ background: #f5f5f5; border-radius: 8px; padding: 16px; min-width: 150px; }}
        .summary-card .label {{ font-size: 12px; color: #888; text-transform: uppercase; }}
        .summary-card .value {{ font-size: 24px; font-weight: bold; margin-top: 4px; }}
        .progress-bar {{ width: 100%; height: 20px; background: #e8e8e8; border-radius: 10px; overflow: hidden; }}
        .progress-fill {{ height: 100%; background: linear-gradient(90deg, #52c41a, #73d13d); transition: width 0.3s; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
        th, td {{ padding: 10px 12px; text-align: left; border-bottom: 1px solid #e8e8e8; }}
        th {{ background: #fafafa; font-weight: 600; }}
        tr:hover {{ background: #f5f5f5; }}
        .footer {{ margin-top: 30px; padding-top: 10px; border-top: 1px solid #e8e8e8; font-size: 12px; color: #888; }}
    </style>
</head>
<body>
    <h1>{content["title"]}</h1>

    <div class="summary">
        <div class="summary-card">
            <div class="label">Status</div>
            <div class="value">{content["execution_status"].upper()}</div>
        </div>
        <div class="summary-card">
            <div class="label">Result</div>
            <div class="value">{content["execution_result"].upper() if content["execution_result"] else "N/A"}</div>
        </div>
        <div class="summary-card">
            <div class="label">Passed</div>
            <div class="value" style="color:#52c41a">{content["passed_steps"]}/{content["total_steps"]}</div>
        </div>
        <div class="summary-card">
            <div class="label">Failed</div>
            <div class="value" style="color:#ff4d4f">{content["failed_steps"]}</div>
        </div>
        <div class="summary-card">
            <div class="label">Duration</div>
            <div class="value">{content["duration_ms"] or "-"} ms</div>
        </div>
    </div>

    <div class="progress-bar">
        <div class="progress-fill" style="width:{passed_pct:.1f}%"></div>
    </div>
    <p style="margin-top:5px;color:#888">{passed_pct:.1f}% passed</p>

    <h2>Test Steps</h2>
    <table>
        <thead>
            <tr>
                <th>#</th>
                <th>Label</th>
                <th>Status</th>
                <th>Command</th>
                <th>Expected</th>
                <th>Actual</th>
                <th>Error</th>
                <th>Duration</th>
            </tr>
        </thead>
        <tbody>{step_rows}</tbody>
    </table>

    <div class="footer">
        Generated by AITestLab at {utc_now().strftime("%Y-%m-%d %H:%M:%S UTC")}
    </div>
</body>
</html>"""

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(html)

        return file_path

    async def list_reports(self, db: AsyncSession) -> List[TestReport]:
        result = await db.execute(
            select(TestReport).order_by(TestReport.created_at.desc())
        )
        return result.scalars().all()

    async def get_report(self, db: AsyncSession, report_id: str) -> Optional[TestReport]:
        result = await db.execute(
            select(TestReport).where(TestReport.id == report_id)
        )
        return result.scalar_one_or_none()

    async def create_template(self, db: AsyncSession, data: dict) -> ReportTemplate:
        fields = data.pop("fields", None)
        template = ReportTemplate(**data)
        if fields:
            template.fields = json.dumps(fields, ensure_ascii=False)
        db.add(template)
        await db.commit()
        await db.refresh(template)
        return template

    async def list_templates(self, db: AsyncSession) -> List[ReportTemplate]:
        result = await db.execute(
            select(ReportTemplate).order_by(ReportTemplate.created_at.desc())
        )
        return result.scalars().all()

    async def get_template(self, db: AsyncSession, template_id: str) -> Optional[ReportTemplate]:
        result = await db.execute(
            select(ReportTemplate).where(ReportTemplate.id == template_id)
        )
        return result.scalar_one_or_none()

    async def update_template(
        self, db: AsyncSession, template_id: str, data: dict
    ) -> Optional[ReportTemplate]:
        template = await self.get_template(db, template_id)
        if not template:
            return None

        for key, value in data.items():
            if key == "fields" and value is not None:
                template.fields = json.dumps(value, ensure_ascii=False)
            elif value is not None:
                setattr(template, key, value)

        await db.commit()
        await db.refresh(template)
        return template

    async def delete_template(self, db: AsyncSession, template_id: str) -> bool:
        template = await self.get_template(db, template_id)
        if not template:
            return False
        await db.delete(template)
        await db.commit()
        return True


report_service = ReportService()
