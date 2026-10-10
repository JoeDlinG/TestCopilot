"""SQLAlchemy database models for AITestLab.

Aligned with DB_DESIGN.md — 11 tables with UUID4 short-format IDs,
proper indexes, foreign keys, and JSON fields.
"""
from __future__ import annotations
import uuid
import secrets
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Column, String, Text, Float, Integer, Boolean,
    DateTime, ForeignKey, JSON, Enum as SAEnum, Index,
)
from sqlalchemy.orm import relationship
import enum

from app.core.database import Base
from app.core.timeutils import utc_now, UTCDateTime


def generate_short_id(prefix: str) -> str:
    """Generate a short UUID-based ID with a prefix.

    Format: {prefix}_xxxxxxxx (8 hex chars from UUID4)
    Example: dev_a1b2c3d4
    """
    short = uuid.uuid4().hex[:8]
    return f"{prefix}_{short}"


# ============ Enums ============

class DeviceType(str, enum.Enum):
    POWER_SUPPLY = "power_supply"
    OSCILLOSCOPE = "oscilloscope"
    MULTIMETER = "multimeter"
    SIGNAL_GENERATOR = "signal_generator"
    SPECTRUM_ANALYZER = "spectrum_analyzer"
    ELECTRONIC_LOAD = "electronic_load"
    CAN_TOOL = "can_tool"
    GENERIC = "generic"


class ProtocolType(str, enum.Enum):
    SCPI = "scpi"
    CAN = "can"
    USB = "usb"
    SERIAL = "serial"
    ETHERNET = "ethernet"
    GPIB = "gpib"
    CUSTOM = "custom"


class ConnectionType(str, enum.Enum):
    USB = "usb"
    ETHERNET = "ethernet"
    GPIB = "gpib"
    SERIAL = "serial"
    CAN = "can"


class DeviceStatus(str, enum.Enum):
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    ERROR = "error"


class TestCaseStatus(str, enum.Enum):
    DRAFT = "draft"
    READY = "ready"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    ARCHIVED = "archived"


class ExecutionStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"
    STOPPED = "stopped"


class ExecutionResult(str, enum.Enum):
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"
    ABORTED = "aborted"


class StepStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"
    SKIPPED = "skipped"


class LogDirection(str, enum.Enum):
    SENT = "sent"
    RECEIVED = "received"


class LogStatus(str, enum.Enum):
    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"


class ModelProvider(str, enum.Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    OLLAMA = "ollama"
    LOCALAI = "localai"
    VLLM = "vllm"
    HUNYUAN = "hunyuan"
    QWEN = "qwen"
    ERNIE = "ernie"
    DEEPSEEK = "deepseek"
    MINIMAX = "minimax"
    CUSTOM = "custom"


class ModelStatus(str, enum.Enum):
    ACTIVE = "active"
    DISABLED = "disabled"
    ERROR = "error"


class PluginStatus(str, enum.Enum):
    INSTALLED = "installed"
    ENABLED = "enabled"
    DISABLED = "disabled"
    ERROR = "error"


class ReportFormat(str, enum.Enum):
    PDF = "pdf"
    HTML = "html"
    DOCX = "docx"
    CSV = "csv"


class ReportStatus(str, enum.Enum):
    GENERATING = "generating"
    GENERATED = "generated"
    FAILED = "failed"


class ChatInputType(str, enum.Enum):
    TEXT = "text"
    VOICE = "voice"


# ============ Models ============


class Device(Base):
    """3.1 devices — Test instrument device table."""
    __tablename__ = "devices"

    id = Column(String(20), primary_key=True, default=lambda: generate_short_id("dev"))
    name = Column(String(200), nullable=False)
    type = Column(String(50), nullable=False, index=True)
    protocol = Column(String(20), nullable=False, index=True)
    connection_type = Column(String(20), nullable=False)
    visa_address = Column(String(500), nullable=True)
    can_channel = Column(String(100), nullable=True)
    serial_port = Column(String(200), nullable=True)
    ip_address = Column(String(45), nullable=True)
    port = Column(Integer, nullable=True)
    status = Column(String(20), nullable=False, default=DeviceStatus.DISCONNECTED.value, index=True)
    config = Column(Text, nullable=True)  # JSON string
    extra_meta = Column("metadata", Text, nullable=True)  # JSON string, mapped from column 'metadata'
    connected_at = Column(UTCDateTime, nullable=True)
    disconnected_at = Column(UTCDateTime, nullable=True)
    last_seen = Column(UTCDateTime, nullable=True)
    created_at = Column(UTCDateTime, nullable=False, default=utc_now)
    updated_at = Column(UTCDateTime, nullable=False, default=utc_now, onupdate=utc_now)

    __table_args__ = (
        Index("idx_devices_status", "status"),
        Index("idx_devices_type", "type"),
        Index("idx_devices_protocol", "protocol"),
    )

    # Relationships
    logs = relationship("CommunicationLog", back_populates="device", cascade="all, delete-orphan")


class AIModelConfig(Base):
    """3.7 ai_models — AI model configuration table."""
    __tablename__ = "ai_models"

    id = Column(String(20), primary_key=True, default=lambda: generate_short_id("model"))
    name = Column(String(200), nullable=False)
    provider = Column(String(50), nullable=False, index=True)
    model_name = Column(String(200), nullable=False)
    api_key_encrypted = Column(Text, nullable=True)
    base_url = Column(String(500), nullable=True)
    parameters = Column(Text, nullable=True)  # JSON string
    is_default = Column(Boolean, nullable=False, default=False, index=True)
    status = Column(String(20), nullable=False, default=ModelStatus.ACTIVE.value)
    last_tested_at = Column(UTCDateTime, nullable=True)
    created_at = Column(UTCDateTime, nullable=False, default=utc_now)
    updated_at = Column(UTCDateTime, nullable=False, default=utc_now, onupdate=utc_now)

    __table_args__ = (
        Index("idx_ai_models_provider", "provider"),
        Index("idx_ai_models_is_default", "is_default"),
    )


class TestCase(Base):
    """3.2 test_cases — Test case table."""
    __tablename__ = "test_cases"

    id = Column(String(20), primary_key=True, default=lambda: generate_short_id("tc"))
    name = Column(String(300), nullable=False)
    description = Column(Text, nullable=True)
    requirement_raw = Column(Text, nullable=True)  # Original requirement text/voice input
    status = Column(String(20), nullable=False, default=TestCaseStatus.DRAFT.value, index=True)
    flow_id = Column(String(20), nullable=True)  # linked via TestFlow.testcase_id relationship
    ai_model_id = Column(String(20), ForeignKey("ai_models.id"), nullable=True)
    tags = Column(Text, nullable=True)  # JSON array string
    created_at = Column(UTCDateTime, nullable=False, default=utc_now)
    updated_at = Column(UTCDateTime, nullable=False, default=utc_now, onupdate=utc_now)

    __table_args__ = (
        Index("idx_test_cases_status", "status"),
        Index("idx_test_cases_flow_id", "flow_id"),
    )

    # Relationships
    flow = relationship("TestFlow", back_populates="test_case", uselist=False)
    executions = relationship("TestExecution", back_populates="test_case", cascade="all, delete-orphan")


class TestFlow(Base):
    """3.3 test_flows — Test flow diagram table (stores ReactFlow JSON)."""
    __tablename__ = "test_flows"

    id = Column(String(20), primary_key=True, default=lambda: generate_short_id("flow"))
    testcase_id = Column(String(20), ForeignKey("test_cases.id"), unique=True, nullable=False)
    nodes = Column(Text, nullable=False, default="[]")  # JSON string
    edges = Column(Text, nullable=False, default="[]")  # JSON string
    viewport = Column(Text, nullable=True)  # JSON string
    created_at = Column(UTCDateTime, nullable=False, default=utc_now)
    updated_at = Column(UTCDateTime, nullable=False, default=utc_now, onupdate=utc_now)

    # Relationships
    test_case = relationship("TestCase", back_populates="flow", uselist=False)


class TestExecution(Base):
    """3.4 test_executions — Test execution record table."""
    __tablename__ = "test_executions"

    id = Column(String(20), primary_key=True, default=lambda: generate_short_id("exec"))
    testcase_id = Column(String(20), ForeignKey("test_cases.id"), nullable=False, index=True)
    status = Column(String(20), nullable=False, default=ExecutionStatus.PENDING.value, index=True)
    result = Column(String(20), nullable=True, index=True)
    options = Column(Text, nullable=True)  # JSON string
    total_steps = Column(Integer, nullable=False, default=0)
    passed_steps = Column(Integer, nullable=False, default=0)
    failed_steps = Column(Integer, nullable=False, default=0)
    error_message = Column(Text, nullable=True)
    started_at = Column(UTCDateTime, nullable=True)
    completed_at = Column(UTCDateTime, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    created_at = Column(UTCDateTime, nullable=False, default=utc_now)
    # --- batch execution linkage (execution manager) --------------------
    # All four stay NULL for a plain single-case run, so existing behaviour
    # and every existing statistic are unchanged.
    plan_run_id = Column(String(20), nullable=True)    # owning batch run
    plan_item_id = Column(String(20), nullable=True)   # owning plan item
    iteration = Column(Integer, nullable=True)         # 1-based loop index
    group_no = Column(Integer, nullable=True)          # parallel group number

    __table_args__ = (
        Index("idx_executions_testcase_id", "testcase_id"),
        Index("idx_executions_status", "status"),
        Index("idx_executions_result", "result"),
        Index("idx_executions_created_at", "created_at"),
        Index("idx_executions_plan_run", "plan_run_id"),
    )

    # Relationships
    test_case = relationship("TestCase", back_populates="executions")
    step_results = relationship("TestStepResult", back_populates="execution", cascade="all, delete-orphan")
    logs = relationship("CommunicationLog", back_populates="execution", cascade="all, delete-orphan")
    reports = relationship("TestReport", back_populates="execution")


class TestStepResult(Base):
    """3.5 test_step_results — Step-level execution results."""
    __tablename__ = "test_step_results"

    id = Column(String(20), primary_key=True, default=lambda: generate_short_id("step"))
    execution_id = Column(String(20), ForeignKey("test_executions.id"), nullable=False, index=True)
    step_index = Column(Integer, nullable=False)
    node_id = Column(String(50), nullable=False)
    node_type = Column(String(20), nullable=False)
    label = Column(String(300), nullable=False)
    status = Column(String(20), nullable=False)
    command = Column(Text, nullable=True)
    expected = Column(Text, nullable=True)
    actual = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    # Result parsing + judgement outcome for this step. One sample per reply,
    # because a step may repeat the same command N times:
    #   {"count": N,
    #    "samples": [[{"name": "电压", "value": 12.3, "status": "ok",
    #                  "ok": true, "detail": "..."}], ...],
    #    "last": [ ... same shape as one sample ... ]}
    # "status" is ok | fail | unknown (empty frame, judgement skipped) | error.
    # Legacy rows may still hold a bare list (= a single sample).
    parsed_results = Column(Text, nullable=True)
    started_at = Column(UTCDateTime, nullable=True)
    completed_at = Column(UTCDateTime, nullable=True)
    duration_ms = Column(Integer, nullable=True)

    __table_args__ = (
        Index("idx_step_results_execution_id", "execution_id"),
        Index("idx_step_results_execution_step", "execution_id", "step_index"),
    )

    # Relationships
    execution = relationship("TestExecution", back_populates="step_results")
    logs = relationship("CommunicationLog", back_populates="step_result")


class CommunicationLog(Base):
    """3.6 communication_logs — Device communication log table."""
    __tablename__ = "communication_logs"

    id = Column(String(20), primary_key=True, default=lambda: generate_short_id("log"))
    timestamp = Column(UTCDateTime, nullable=False, default=utc_now, index=True)
    device_id = Column(String(20), ForeignKey("devices.id"), nullable=False, index=True)
    execution_id = Column(String(20), ForeignKey("test_executions.id"), nullable=True, index=True)
    step_result_id = Column(String(20), ForeignKey("test_step_results.id"), nullable=True)
    direction = Column(String(10), nullable=False)  # sent / received
    protocol = Column(String(20), nullable=False)
    raw_data = Column(Text, nullable=False)
    raw_data_hex = Column(Text, nullable=True)
    raw_data_size = Column(Integer, nullable=True)
    status = Column(String(20), nullable=False, default=LogStatus.SUCCESS.value)
    error_message = Column(Text, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    response_log_id = Column(String(20), ForeignKey("communication_logs.id"), nullable=True)
    extra_meta = Column("metadata", Text, nullable=True)  # JSON string

    __table_args__ = (
        Index("idx_logs_timestamp", "timestamp"),
        Index("idx_logs_device_id", "device_id"),
        Index("idx_logs_execution_id", "execution_id"),
        Index("idx_logs_device_timestamp", "device_id", "timestamp"),
        Index("idx_logs_direction", "direction"),
    )

    # Relationships
    device = relationship("Device", back_populates="logs")
    execution = relationship("TestExecution", back_populates="logs")
    step_result = relationship("TestStepResult", back_populates="logs")
    response_log = relationship("CommunicationLog", remote_side=[id], uselist=False)


class TestReport(Base):
    """3.9 test_reports — Test report table."""
    __tablename__ = "test_reports"

    id = Column(String(20), primary_key=True, default=lambda: generate_short_id("rpt"))
    title = Column(String(300), nullable=False)
    execution_id = Column(String(20), ForeignKey("test_executions.id"), nullable=False, index=True)
    template_id = Column(String(20), ForeignKey("report_templates.id"), nullable=True)
    format = Column(String(10), nullable=False, default=ReportFormat.PDF.value)
    status = Column(String(20), nullable=False, default=ReportStatus.GENERATING.value)
    file_path = Column(String(500), nullable=True)
    file_size = Column(Integer, nullable=True)
    fields = Column(Text, nullable=True)  # JSON string
    error_message = Column(Text, nullable=True)
    created_at = Column(UTCDateTime, nullable=False, default=utc_now)
    generated_at = Column(UTCDateTime, nullable=True)

    __table_args__ = (
        Index("idx_reports_execution_id", "execution_id"),
    )

    # Relationships
    execution = relationship("TestExecution", back_populates="reports")
    template = relationship("ReportTemplate", back_populates="reports")


class ReportTemplate(Base):
    """3.10 report_templates — Report template table."""
    __tablename__ = "report_templates"

    id = Column(String(20), primary_key=True, default=lambda: generate_short_id("tpl"))
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    fields = Column(Text, nullable=True)  # JSON string — field definitions
    template_content = Column(Text, nullable=True)  # Jinja2 template content
    created_at = Column(UTCDateTime, nullable=False, default=utc_now)
    updated_at = Column(UTCDateTime, nullable=False, default=utc_now, onupdate=utc_now)

    # Relationships
    reports = relationship("TestReport", back_populates="template")


class Plugin(Base):
    """3.8 plugins — Plugin registry table."""
    __tablename__ = "plugins"

    id = Column(String(20), primary_key=True, default=lambda: generate_short_id("plg"))
    name = Column(String(200), nullable=False, unique=True)
    version = Column(String(50), nullable=False)
    description = Column(Text, nullable=True)
    author = Column(String(200), nullable=True)
    protocol_type = Column(String(50), nullable=False, index=True)
    status = Column(String(20), nullable=False, default=PluginStatus.INSTALLED.value, index=True)
    file_path = Column(String(500), nullable=False)
    module_name = Column(String(200), nullable=False)
    class_name = Column(String(200), nullable=False)
    config_schema = Column(Text, nullable=True)  # JSON Schema string
    config = Column(Text, nullable=True)  # JSON string
    entry_point = Column(String(200), nullable=True)
    error_message = Column(Text, nullable=True)
    installed_at = Column(UTCDateTime, nullable=False, default=utc_now)
    enabled_at = Column(UTCDateTime, nullable=True)
    disabled_at = Column(UTCDateTime, nullable=True)
    updated_at = Column(UTCDateTime, nullable=False, default=utc_now, onupdate=utc_now)

    __table_args__ = (
        Index("idx_plugins_name", "name", unique=True),
        Index("idx_plugins_status", "status"),
        Index("idx_plugins_protocol_type", "protocol_type"),
    )


class ChatHistory(Base):
    """AI chat history table (supplemental)."""
    __tablename__ = "chat_history"

    id = Column(String(20), primary_key=True, default=lambda: generate_short_id("chat"))
    session_id = Column(String(20), nullable=False, index=True)
    role = Column(String(20), nullable=False)  # user, assistant, system
    content = Column(Text, nullable=False)
    input_type = Column(String(20), default=ChatInputType.TEXT.value)  # text, voice
    extra_meta = Column("metadata", Text, nullable=True)  # JSON string
    created_at = Column(UTCDateTime, nullable=False, default=utc_now)


class Dashboard(Base):
    """3.12 dashboards — User-assembled custom dashboard.

    A dashboard is *only* a description: a grid layout plus a list of widget
    definitions. No measured values are ever stored here — widgets reference a
    data source (test case / device / fields) and every value is resolved at
    request time from ``test_step_results.parsed_results``.
    """
    __tablename__ = "dashboards"

    id = Column(String(20), primary_key=True, default=lambda: generate_short_id("dash"))
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    # react-grid-layout layout array: [{i, x, y, w, h, minW, minH}, ...]
    layout = Column(Text, nullable=True)
    # widget definitions: [{id, type, title, config: {...}}, ...]
    widgets = Column(Text, nullable=True)
    # shared data source for the parsed-value widgets
    data_source = Column(Text, nullable=True)  # JSON: {test_case_id, limit, refresh_sec}
    is_default = Column(Boolean, nullable=False, default=False, index=True)
    created_at = Column(UTCDateTime, nullable=False, default=utc_now)
    updated_at = Column(UTCDateTime, nullable=False, default=utc_now, onupdate=utc_now)

    __table_args__ = (
        Index("idx_dashboards_is_default", "is_default"),
    )


class SystemConfig(Base):
    """3.11 system_config — System configuration table."""
    __tablename__ = "system_config"

    id = Column(String(20), primary_key=True, default=lambda: generate_short_id("cfg"))
    key = Column(String(100), nullable=False, unique=True, index=True)
    value = Column(Text, nullable=True)
    description = Column(Text, nullable=True)
    updated_at = Column(UTCDateTime, nullable=False, default=utc_now, onupdate=utc_now)


# ====================================================================== #
# Execution manager — batch plans, plan items and batch runs
# ====================================================================== #

class ResolvedState(str, enum.Enum):
    """How confident we are about *which* device a plan item will occupy."""

    RESOLVED = "resolved"        # exactly one concrete device
    CANDIDATES = "candidates"    # protocol matched several devices
    UNRESOLVED = "unresolved"    # nothing could be determined


class PlanRunStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    STOPPED = "stopped"
    ERROR = "error"


class ExecutionPlan(Base):
    """3.13 execution_plans — a reusable batch *template*.

    The plan itself never runs: starting it produces an ``ExecutionPlanRun``.
    """
    __tablename__ = "execution_plans"

    id = Column(String(20), primary_key=True, default=lambda: generate_short_id("pln"))
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    plan_loop_count = Column(Integer, nullable=False, default=1)     # plan-level loop
    max_parallel = Column(Integer, nullable=False, default=4)        # 1..16
    on_error = Column(String(20), nullable=False, default="abort_all")  # abort_all|continue|abort_group
    last_run_id = Column(String(20), nullable=True)
    created_at = Column(UTCDateTime, nullable=False, default=utc_now)
    updated_at = Column(UTCDateTime, nullable=False, default=utc_now, onupdate=utc_now)

    __table_args__ = (
        Index("idx_plans_updated_at", "updated_at"),
    )

    items = relationship(
        "ExecutionPlanItem",
        back_populates="plan",
        cascade="all, delete-orphan",
        order_by="ExecutionPlanItem.seq",
    )


class ExecutionPlanItem(Base):
    """3.14 execution_plan_items — one row = one test case + its run config.

    Items sharing a ``group_no`` run in parallel; groups run in ascending
    ``group_no`` order.
    """
    __tablename__ = "execution_plan_items"

    id = Column(String(20), primary_key=True, default=lambda: generate_short_id("pitem"))
    plan_id = Column(String(20), ForeignKey("execution_plans.id"), nullable=False, index=True)
    testcase_id = Column(String(20), nullable=False)
    seq = Column(Integer, nullable=False)           # display / default order
    group_no = Column(Integer, nullable=False)      # parallel group
    loop_count = Column(Integer, nullable=False, default=1)
    delay_before_ms = Column(Integer, nullable=False, default=0)
    delay_after_ms = Column(Integer, nullable=False, default=0)
    loop_interval_ms = Column(Integer, nullable=False, default=0)
    device_id = Column(String(20), nullable=True)   # explicit override (nullable = infer)
    resolved_device_ids = Column(Text, nullable=True)   # JSON array snapshot
    resolved_state = Column(
        String(20), nullable=False, default=ResolvedState.UNRESOLVED.value
    )
    node_count = Column(Integer, nullable=True)     # flow size at resolve time (0 = empty flow)
    created_at = Column(UTCDateTime, nullable=False, default=utc_now)
    updated_at = Column(UTCDateTime, nullable=False, default=utc_now, onupdate=utc_now)

    __table_args__ = (
        Index("idx_pitems_plan", "plan_id", "group_no"),
    )

    plan = relationship("ExecutionPlan", back_populates="items")


class ExecutionPlanRun(Base):
    """3.15 execution_plan_runs — one concrete execution of a plan.

    ``plan_snapshot`` freezes the plan/items at launch time so later edits to
    the plan can never rewrite the meaning of a historical run.
    """
    __tablename__ = "execution_plan_runs"

    id = Column(String(20), primary_key=True, default=lambda: generate_short_id("prun"))
    plan_id = Column(String(20), nullable=True, index=True)   # NULL = ad-hoc plan
    plan_name = Column(String(200), nullable=True)
    plan_snapshot = Column(Text, nullable=False)              # JSON
    status = Column(String(20), nullable=False, default=PlanRunStatus.PENDING.value, index=True)
    total_items = Column(Integer, nullable=False, default=0)
    completed_items = Column(Integer, nullable=False, default=0)
    passed_items = Column(Integer, nullable=False, default=0)
    failed_items = Column(Integer, nullable=False, default=0)
    error_message = Column(Text, nullable=True)
    started_at = Column(UTCDateTime, nullable=True)
    completed_at = Column(UTCDateTime, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    created_at = Column(UTCDateTime, nullable=False, default=utc_now)

    __table_args__ = (
        Index("idx_pruns_plan", "plan_id"),
        Index("idx_pruns_status", "status"),
    )
