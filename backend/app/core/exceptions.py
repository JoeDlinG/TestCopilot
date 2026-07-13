"""Custom exception classes for AITestLab."""
from typing import Optional, Any


class AITestLabException(Exception):
    """Base exception for AITestLab."""
    def __init__(self, message: str, code: int = 50000, detail: Optional[str] = None):
        self.message = message
        self.code = code
        self.detail = detail or message
        super().__init__(message)


class DeviceNotFoundError(AITestLabException):
    def __init__(self, device_id: str):
        super().__init__(
            message=f"Device not found: {device_id}",
            code=40001,
            detail=f"No device with id={device_id}",
        )


class DeviceConnectionError(AITestLabException):
    def __init__(self, device_id: str, reason: str = ""):
        super().__init__(
            message=f"Failed to connect device: {device_id}",
            code=40002,
            detail=f"Connection to device {device_id} failed. {reason}",
        )


class DeviceTimeoutError(AITestLabException):
    def __init__(self, device_id: str):
        super().__init__(
            message=f"Device communication timeout: {device_id}",
            code=40003,
            detail=f"Timeout waiting for response from device {device_id}",
        )


class TestCaseNotFoundError(AITestLabException):
    def __init__(self, test_case_id: str):
        super().__init__(
            message=f"Test case not found: {test_case_id}",
            code=40004,
            detail=f"No test case with id={test_case_id}",
        )


class ExecutionNotFoundError(AITestLabException):
    def __init__(self, execution_id: str):
        super().__init__(
            message=f"Execution not found: {execution_id}",
            code=40005,
            detail=f"No execution with id={execution_id}",
        )


class AIModelNotFoundError(AITestLabException):
    def __init__(self, model_id: str):
        super().__init__(
            message=f"AI model not found: {model_id}",
            code=40006,
            detail=f"No AI model config with id={model_id}",
        )


class AICallError(AITestLabException):
    def __init__(self, provider: str, reason: str = ""):
        super().__init__(
            message=f"AI call failed: {provider}",
            code=40007,
            detail=f"Call to AI provider {provider} failed. {reason}",
        )


class PluginNotFoundError(AITestLabException):
    def __init__(self, plugin_id: str):
        super().__init__(
            message=f"Plugin not found: {plugin_id}",
            code=40008,
            detail=f"No plugin with id={plugin_id}",
        )


class PluginLoadError(AITestLabException):
    def __init__(self, plugin_name: str, reason: str = ""):
        super().__init__(
            message=f"Failed to load plugin: {plugin_name}",
            code=40009,
            detail=f"Plugin {plugin_name} failed to load. {reason}",
        )


class ValidationError(AITestLabException):
    def __init__(self, message: str, detail: Optional[str] = None):
        super().__init__(
            message=message,
            code=40010,
            detail=detail or message,
        )


class ReportGenerationError(AITestLabException):
    def __init__(self, reason: str = ""):
        super().__init__(
            message="Report generation failed",
            code=40011,
            detail=f"Failed to generate report. {reason}",
        )
