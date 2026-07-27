"""Pydantic schemas for API request/response validation.

Aligned with API_SPEC.md — all endpoints follow unified {code, message, data} format.
"""
from __future__ import annotations
from datetime import datetime
from typing import Optional, Any, List, Dict
from pydantic import BaseModel, Field


# ============ Device Schemas ============

class DeviceCreate(BaseModel):
    name: str
    type: str  # device type: oscilloscope, power_supply, etc.
    protocol: str  # scpi, can, serial, ethernet, etc.
    connection_type: str  # usb, ethernet, gpib, serial, can
    visa_address: Optional[str] = None
    can_channel: Optional[str] = None
    serial_port: Optional[str] = None
    ip_address: Optional[str] = None
    port: Optional[int] = None
    config: Optional[Dict[str, Any]] = None
    extra_meta: Optional[Dict[str, Any]] = Field(None, alias="metadata")


class DeviceResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    name: str
    type: str
    protocol: str
    connection_type: str
    visa_address: Optional[str] = None
    can_channel: Optional[str] = None
    serial_port: Optional[str] = None
    ip_address: Optional[str] = None
    port: Optional[int] = None
    status: str
    config: Optional[Any] = None
    extra_meta: Optional[Any] = Field(None, alias="metadata")
    connected_at: Optional[datetime] = None
    disconnected_at: Optional[datetime] = None
    last_seen: Optional[datetime] = None
    created_at: datetime


class DeviceUpdate(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None
    protocol: Optional[str] = None
    connection_type: Optional[str] = None
    visa_address: Optional[str] = None
    can_channel: Optional[str] = None
    serial_port: Optional[str] = None
    ip_address: Optional[str] = None
    port: Optional[int] = None
    config: Optional[Dict[str, Any]] = None
    extra_meta: Optional[Dict[str, Any]] = Field(None, alias="metadata")


class DeviceConnectRequest(BaseModel):
    device_id: str
    config: Optional[Dict[str, Any]] = None


class DeviceCommandRequest(BaseModel):
    command: str
    parameters: Optional[Dict[str, Any]] = None


class DeviceCommandResponse(BaseModel):
    device_id: str
    command: str
    response: str
    duration_ms: Optional[int] = None


# ============ AI Model Schemas ============

class AIModelConfigCreate(BaseModel):
    model_config = {"protected_namespaces": ()}

    name: str
    provider: str  # openai, anthropic, ollama, localai, vllm, hunyuan, qwen, ernie, deepseek, minimax, custom
    model_name: str  # e.g., gpt-4o, claude-3-opus, llama3:8b, deepseek-chat
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    is_default: Optional[bool] = False
    parameters: Optional[Dict[str, Any]] = Field(default_factory=dict)


class AIModelConfigUpdate(BaseModel):
    name: Optional[str] = None
    provider: Optional[str] = None
    model_name: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = None
    is_default: Optional[bool] = None


class AIModelConfigResponse(BaseModel):
    model_config = {"from_attributes": True, "protected_namespaces": ()}

    id: str
    name: str
    provider: str
    model_name: str
    base_url: Optional[str] = None
    is_default: bool
    status: str
    parameters: Optional[Any] = None
    last_tested_at: Optional[datetime] = None
    created_at: datetime


class AIChatRequest(BaseModel):
    model_config = {"protected_namespaces": ()}

    model_id: str
    message: str
    input_type: str = "text"  # text or voice
    session_id: Optional[str] = None
    system_prompt: Optional[str] = None
    # Plugin skills to import into the conversation context (protocol names).
    skill_protocols: List[str] = Field(default_factory=list)


class AIChatResponse(BaseModel):
    session_id: str
    response: str
    usage: Optional[Dict[str, Any]] = None


# ============ Test Case Schemas ============

class TestStep(BaseModel):
    step_number: int
    action: str
    expected_result: str
    parameters: Dict[str, Any] = Field(default_factory=dict)
    device_type: Optional[str] = None


class TestCaseCreate(BaseModel):
    name: str
    description: Optional[str] = None
    requirement_raw: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    ai_model_id: Optional[str] = None


class TestCaseGenerateRequest(BaseModel):
    model_config = {"protected_namespaces": ()}

    requirements: str
    input_type: str = "text"  # text or voice
    model_id: Optional[str] = None
    available_devices: List[Dict[str, Any]] = Field(default_factory=list)
    # Plugin skills to use for generation (protocol names).
    skill_protocols: List[str] = Field(default_factory=list)


class TestCaseGenerateResponse(BaseModel):
    raw_response: str
    parsed: Dict[str, Any]
    usage: Optional[Dict[str, Any]] = None


class TestCaseResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    name: str
    description: Optional[str] = None
    requirement_raw: Optional[str] = None
    status: str
    flow_id: Optional[str] = None
    ai_model_id: Optional[str] = None
    tags: Optional[Any] = None
    created_at: datetime
    updated_at: datetime


class TestCaseUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    tags: Optional[List[str]] = None


# ============ Test Flow (Flowchart) Schemas ============

class FlowNode(BaseModel):
    id: str
    type: str  # start, test_step, condition, loop, end, etc.
    label: str
    position: Dict[str, float] = Field(default_factory=lambda: {"x": 0, "y": 0})
    config: Dict[str, Any] = Field(default_factory=dict)


class FlowEdge(BaseModel):
    id: str
    source: str
    target: str
    label: Optional[str] = None


class FlowViewport(BaseModel):
    x: float = 0
    y: float = 0
    zoom: float = 1


class TestFlowCreate(BaseModel):
    nodes: List[Dict[str, Any]] = Field(default_factory=list)
    edges: List[Dict[str, Any]] = Field(default_factory=list)
    viewport: Optional[Dict[str, Any]] = None


class TestFlowUpdate(BaseModel):
    nodes: Optional[List[Dict[str, Any]]] = None
    edges: Optional[List[Dict[str, Any]]] = None
    viewport: Optional[Dict[str, Any]] = None


class TestFlowResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    testcase_id: str
    nodes: Any  # JSON
    edges: Any  # JSON
    viewport: Optional[Any] = None
    created_at: datetime
    updated_at: datetime


# ============ Test Execution Schemas ============

class ExecutionStartRequest(BaseModel):
    test_case_id: str
    options: Optional[Dict[str, Any]] = None


class ExecutionResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    testcase_id: str
    status: str
    result: Optional[str] = None
    options: Optional[Any] = None
    total_steps: int
    passed_steps: int
    failed_steps: int
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    created_at: datetime


class StepResultResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    execution_id: str
    step_index: int
    node_id: str
    node_type: str
    label: str
    status: str
    command: Optional[str] = None
    expected: Optional[str] = None
    actual: Optional[str] = None
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_ms: Optional[int] = None


class ExecutionDetailResponse(ExecutionResponse):
    step_results: List[StepResultResponse] = Field(default_factory=list)


# ============ Communication Log Schemas ============

class LogResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    timestamp: datetime
    device_id: str
    execution_id: Optional[str] = None
    step_result_id: Optional[str] = None
    direction: str  # sent / received
    protocol: str
    raw_data: str
    raw_data_hex: Optional[str] = None
    raw_data_size: Optional[int] = None
    status: str
    error_message: Optional[str] = None
    duration_ms: Optional[int] = None
    extra_meta: Optional[Any] = Field(None, alias="metadata")


class LogQueryRequest(BaseModel):
    device_id: Optional[str] = None
    execution_id: Optional[str] = None
    protocol: Optional[str] = None
    direction: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    page: int = 1
    page_size: int = 50


# ============ Natural Language Query Schemas ============

class NLQueryRequest(BaseModel):
    model_config = {"protected_namespaces": ()}

    query: str
    input_type: str = "text"  # text or voice
    model_id: Optional[str] = None


class NLQueryResponse(BaseModel):
    query: str
    sql_generated: Optional[str] = None
    results: List[Dict[str, Any]]
    result_count: int
    explanation: Optional[str] = None


# ============ Report Schemas ============

class ReportGenerateRequest(BaseModel):
    title: str
    execution_id: str
    template_id: Optional[str] = None
    fields: Dict[str, Any] = Field(default_factory=dict)
    format: str = "pdf"  # pdf, html, docx


class ReportResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    title: str
    execution_id: str
    template_id: Optional[str] = None
    format: str
    status: str
    file_path: Optional[str] = None
    file_size: Optional[int] = None
    fields: Optional[Any] = None
    error_message: Optional[str] = None
    created_at: datetime
    generated_at: Optional[datetime] = None


class ReportTemplateCreate(BaseModel):
    name: str
    description: Optional[str] = None
    fields: List[Dict[str, Any]] = Field(default_factory=list)
    template_content: Optional[str] = None


class ReportTemplateUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    fields: Optional[List[Dict[str, Any]]] = None
    template_content: Optional[str] = None


class ReportTemplateResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    name: str
    description: Optional[str] = None
    fields: Optional[Any] = None
    template_content: Optional[str] = None
    created_at: datetime
    updated_at: datetime


# ============ Plugin Schemas ============

class PluginInstallRequest(BaseModel):
    name: str
    version: str
    description: Optional[str] = None
    author: Optional[str] = None
    protocol_type: str
    file_path: str
    module_name: str
    class_name: str
    config_schema: Optional[Dict[str, Any]] = None
    config: Optional[Dict[str, Any]] = None
    entry_point: Optional[str] = None


class PluginResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    name: str
    version: str
    description: Optional[str] = None
    author: Optional[str] = None
    protocol_type: str
    status: str
    config: Optional[Any] = None
    error_message: Optional[str] = None
    installed_at: datetime
    enabled_at: Optional[datetime] = None


class PluginUpdateRequest(BaseModel):
    config: Optional[Dict[str, Any]] = None
    status: Optional[str] = None


# ============ Speech Schemas ============

class SpeechTranscribeResponse(BaseModel):
    text: str
    language: Optional[str] = None
    duration: Optional[float] = None


# ============ Common Schemas ============

class PaginatedResponse(BaseModel):
    items: List[Any]
    total: int
    page: int
    page_size: int


class ApiResponse(BaseModel):
    code: int = 0
    message: str = "success"
    data: Optional[Any] = None


class ErrorResponse(BaseModel):
    code: int
    message: str
    detail: Optional[str] = None
