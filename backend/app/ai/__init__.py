"""AI provider abstraction layer for AITestLab.

Supports OpenAI, Anthropic Claude, Ollama, LocalAI, vLLM, DeepSeek, MiniMax,
and custom providers through a unified interface.
"""
from __future__ import annotations
import logging
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List

import httpx

logger = logging.getLogger(__name__)


class AIProvider(ABC):
    """Abstract base class for AI model providers."""

    def __init__(
        self,
        model_name: str,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        parameters: Optional[Dict[str, Any]] = None,
    ):
        self.model_name = model_name
        self.api_key = api_key
        self.base_url = base_url
        self.parameters = parameters or {}
        self.last_error: Optional[str] = None

    @abstractmethod
    async def chat(
        self,
        messages: List[Dict[str, str]],
        stream: bool = False,
    ) -> Dict[str, Any]:
        """Send a chat completion request."""
        ...

    async def test_connection(self) -> bool:
        """Test if the provider is reachable.

        The concrete error reason (if any) is stored in ``self.last_error``
        so callers can surface a meaningful diagnostic to the user instead of
        a generic "connection failed".
        """
        self.last_error = None
        try:
            await self.chat([{"role": "user", "content": "ping"}])
            return True
        except Exception as e:
            self.last_error = str(e)
            logger.warning(f"Provider test failed: {e}")
            return False

    def _raise_for_status(self, response: "httpx.Response") -> None:
        """Like ``response.raise_for_status`` but attach the response body."""
        if response.is_success:
            return
        body = ""
        try:
            body = response.text
        except Exception:
            body = ""
        raise httpx.HTTPStatusError(
            f"HTTP {response.status_code}: {body[:1000]}",
            request=response.request,
            response=response,
        )


class OpenAIProvider(AIProvider):
    """OpenAI and OpenAI-compatible API provider.

    Works with: OpenAI, Ollama, LocalAI, vLLM, 腾讯混元, 阿里通义千问, etc.
    """

    def __init__(
        self,
        model_name: str,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        parameters: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(model_name, api_key, base_url, parameters)
        self.base_url = (base_url or "https://api.openai.com/v1").rstrip("/")

    async def chat(
        self,
        messages: List[Dict[str, str]],
        stream: bool = False,
    ) -> Dict[str, Any]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = {
            "model": self.model_name,
            "messages": messages,
            "stream": stream,
            **self.parameters,
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
            self._raise_for_status(response)
            data = response.json()

        return {
            "content": data["choices"][0]["message"]["content"],
            "reasoning_content": data["choices"][0]["message"].get("reasoning_content"),
            "usage": data.get("usage", {}),
            "model": data.get("model", self.model_name),
        }


class AnthropicProvider(AIProvider):
    """Anthropic Claude API provider."""

    def __init__(
        self,
        model_name: str,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        parameters: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(model_name, api_key, base_url, parameters)
        self.base_url = (base_url or "https://api.anthropic.com/v1").rstrip("/")

    async def chat(
        self,
        messages: List[Dict[str, str]],
        stream: bool = False,
    ) -> Dict[str, Any]:
        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key or "",
            "anthropic-version": "2023-06-01",
        }

        # Separate system message
        system_msg = None
        user_messages = []
        for m in messages:
            if m["role"] == "system":
                system_msg = m["content"]
            else:
                user_messages.append(m)

        payload = {
            "model": self.model_name,
            "messages": user_messages,
            "max_tokens": self.parameters.get("max_tokens", 4096),
        }
        if system_msg:
            payload["system"] = system_msg

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{self.base_url}/messages",
                headers=headers,
                json=payload,
            )
            self._raise_for_status(response)
            data = response.json()

        return {
            "content": data["content"][0]["text"],
            "usage": data.get("usage", {}),
            "model": data.get("model", self.model_name),
        }


class OllamaProvider(OpenAIProvider):
    """Ollama local model provider (uses OpenAI-compatible API)."""

    def __init__(
        self,
        model_name: str,
        base_url: Optional[str] = None,
        parameters: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            model_name=model_name,
            api_key=None,
            base_url=base_url or "http://localhost:11434/v1",
            parameters=parameters,
        )


class ProviderFactory:
    """Factory for creating AI provider instances."""

    PROVIDER_MAP = {
        "openai": OpenAIProvider,
        "ollama": OllamaProvider,
        "anthropic": AnthropicProvider,
        "localai": OpenAIProvider,
        "vllm": OpenAIProvider,
        "hunyuan": OpenAIProvider,
        "qwen": OpenAIProvider,
        "ernie": OpenAIProvider,
        "deepseek": OpenAIProvider,
        "minimax": OpenAIProvider,
        "custom": OpenAIProvider,
    }

    # Default base URLs per provider. When a model does not store an explicit
    # base_url, the factory fills in the provider-appropriate endpoint instead
    # of silently falling back to OpenAI (which previously caused confusing
    # "connection failed" errors for e.g. DeepSeek/Qwen/Hunyuan models).
    DEFAULT_BASE_URLS = {
        "openai": "https://api.openai.com/v1",
        "deepseek": "https://api.deepseek.com/v1",
        "hunyuan": "https://api.hunyuan.cloud.tencent.com/v1",
        "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "ernie": "https://qianfan.baidubce.com/v2",
        "minimax": "https://api.minimax.chat/v1",
        "localai": "http://localhost:8080/v1",
        "vllm": "http://localhost:8000/v1",
        # "custom" and "ollama" have no global default; OllamaProvider supplies
        # its own localhost default, while custom must be set explicitly.
        "custom": None,
        "ollama": None,
    }

    @classmethod
    def create(
        cls,
        provider: str,
        model_name: str,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> AIProvider:
        """Create an AI provider instance based on provider type."""
        provider_class = cls.PROVIDER_MAP.get(provider, OpenAIProvider)
        # Resolve a provider-specific default base URL when none is stored.
        if not base_url:
            base_url = cls.DEFAULT_BASE_URLS.get(provider)
        return provider_class(
            model_name=model_name,
            api_key=api_key,
            base_url=base_url,
            parameters=parameters,
        )

    @classmethod
    def register(cls, name: str, provider_class: type):
        """Register a custom provider."""
        cls.PROVIDER_MAP[name] = provider_class


ai_provider_factory = ProviderFactory()
