"""AI model integration service — uses the AI provider abstraction layer.

Supports OpenAI, Anthropic Claude, Ollama, LocalAI, vLLM, and more
through a unified ProviderFactory.
"""
from __future__ import annotations
import json
import logging
import re
from typing import Optional, List, Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.models import AIModelConfig, ChatHistory, TestCase, ChatInputType, generate_short_id
from app.ai import ai_provider_factory, AIProvider
from app.core.exceptions import AIModelNotFoundError, AICallError
from app.services.plugin_service import plugin_service

logger = logging.getLogger(__name__)


def _build_skill_context(
    skill_protocols: Optional[List[str]],
    *,
    auto_detect_text: Optional[str] = None,
) -> str:
    """Assemble plugin skill + manual markdown into an AI context block.

    ``skill_protocols`` are explicitly requested protocols; if
    ``auto_detect_text`` is given, skills whose name/keywords appear in the
    text are auto-attached as well (so "用 Mini Gateway 100 生成测试用例"
    works without manual import).
    """
    protocols: List[str] = list(skill_protocols or [])
    if auto_detect_text:
        try:
            for p in plugin_service.match_skills_for_text(auto_detect_text):
                if p not in protocols:
                    protocols.append(p)
        except Exception as e:
            logger.warning(f"Skill auto-detection failed: {e}")

    sections = []
    for protocol in protocols:
        try:
            content = plugin_service.get_plugin_skill_content(protocol)
        except Exception as e:
            logger.warning(f"Failed to load skill '{protocol}': {e}")
            continue
        if not content:
            continue
        part = f"## 设备 Skill: {content['name']} (protocol: {protocol})\n\n{content['skill']}"
        if content.get("manual"):
            part += f"\n\n## 设备使用手册: {content['name']}\n\n{content['manual']}"
        sections.append(part)

    if not sections:
        return ""
    return (
        "# 已导入的设备插件知识（Skill / 使用手册）\n\n"
        "生成测试用例或回答设备相关问题时，必须严格遵循以下设备的命令格式、"
        "协议约束与测试流程：\n\n" + "\n\n---\n\n".join(sections)
    )


def _provider_with_min_tokens(model, min_tokens: int):
    """Build a provider for ``model`` but guarantee a sane ``max_tokens`` floor.

    Reasoning-capable models (e.g. DeepSeek-R1/v4) spend a large share of the
    output budget on ``reasoning_content``; if the configured ``max_tokens`` is
    too small the final ``content`` (or the JSON payload) gets truncated, which
    previously produced empty test-case results. We therefore enforce a minimum
    so the model always has room to emit a complete answer.
    """
    params: dict = {}
    if model.parameters:
        try:
            params = json.loads(model.parameters)
        except (json.JSONDecodeError, TypeError):
            params = {}
    if not isinstance(params, dict):
        params = {}
    try:
        cur = int(params.get("max_tokens") or 0)
    except (TypeError, ValueError):
        cur = 0
    if cur < min_tokens:
        params["max_tokens"] = min_tokens
    return ai_provider_factory.create(
        provider=model.provider,
        model_name=model.model_name,
        api_key=model.api_key_encrypted,
        base_url=model.base_url,
        parameters=params,
    )


def _slice_balanced(s: str, start: int, open_ch: str, close_ch: str) -> Optional[str]:
    """Return ``s[start:]`` up to the bracket matching ``open_ch`` at ``start``."""
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(s)):
        ch = s[i]
        if esc:
            esc = False
            continue
        if ch == "\\":
            esc = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                return s[start : i + 1]
    return None


def _extract_json_object(text: str) -> Optional[dict]:
    """Best-effort extraction of a JSON object from arbitrary model output.

    Robust to: markdown code fences, surrounding prose, a bare JSON array
    ``[{...}]`` (wrapped into ``{"test_cases": [...]}``), the canonical
    ``{"test_cases": [...]}`` shape, and a lone JSON object.
    """
    if not text or not text.strip():
        return None
    s = text.strip()

    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", s)
    if fence:
        s = fence.group(1).strip()

    # 1) Direct parse
    try:
        obj = json.loads(s)
        if isinstance(obj, dict):
            return obj
        if isinstance(obj, list):
            return {"test_cases": obj}
    except (json.JSONDecodeError, ValueError):
        pass

    # 2) {"test_cases": [...]}
    m = re.search(r'\{\s*"test_cases"\s*:\s*\[', s)
    if m:
        sub = _slice_balanced(s, m.start(), "{", "}")
        if sub is not None:
            try:
                obj = json.loads(sub)
                if isinstance(obj, dict):
                    return obj
            except (json.JSONDecodeError, ValueError):
                pass

    # 3) Bare top-level JSON array
    m = re.search(r"\[\s*\{", s)
    if m:
        sub = _slice_balanced(s, m.start(), "[", "]")
        if sub is not None:
            try:
                arr = json.loads(sub)
                if isinstance(arr, list):
                    return {"test_cases": arr}
            except (json.JSONDecodeError, ValueError):
                pass

    # 4) First balanced object as last resort
    m = re.search(r"\{", s)
    if m:
        sub = _slice_balanced(s, m.start(), "{", "}")
        if sub is not None:
            try:
                obj = json.loads(sub)
                if isinstance(obj, dict):
                    return obj
            except (json.JSONDecodeError, ValueError):
                pass

    # 5) Salvage truncated JSON — reasoning models may exhaust their token
    #    budget on reasoning_content, leaving the final JSON payload truncated
    #    (missing closing braces / brackets).  We count unmatched open tokens
    #    and append the needed closers, then try to parse the result.
    m = re.search(r'\{\s*"test_cases"\s*:\s*\[', s)
    if m:
        salvage = s[m.start():]
        # Count unmatched braces and brackets
        depth_obj = 0
        depth_arr = 0
        in_str = False
        esc = False
        for ch in salvage:
            if esc:
                esc = False
                continue
            if ch == "\\":
                esc = True
                continue
            if ch == '"':
                in_str = not in_str
                continue
            if in_str:
                continue
            if ch == "{":
                depth_obj += 1
            elif ch == "}":
                depth_obj -= 1
            elif ch == "[":
                depth_arr += 1
            elif ch == "]":
                depth_arr -= 1
        # Close unmatched brackets
        suffix = "]" * max(depth_arr, 0) + "}" * max(depth_obj, 0)
        if suffix:
            candidate = salvage + suffix
            try:
                obj = json.loads(candidate)
                if isinstance(obj, dict):
                    return obj
            except (json.JSONDecodeError, ValueError):
                pass

    return None


def _normalize_test_cases(parsed: dict) -> dict:
    """Normalize whatever the model returned into a stable test-case structure.

    Guarantees each case has ``name``, ``description``, ``steps`` (list of
    ``{step_number, action, expected_result, parameters, device_type}``),
    ``expected_result``, ``parameters``, ``devices_required``, ``tags`` and
    ``flow_description`` — so both the UI render and the save endpoint receive a
    predictable shape even when the model uses alternate key names
    (``testCaseId``, ``expectedResults``, string-only steps, ...).
    """
    raw_list = parsed.get("test_cases") if isinstance(parsed, dict) else None
    if not isinstance(raw_list, list):
        if isinstance(parsed, dict) and any(
            k in parsed for k in ("name", "testCaseId", "title", "description")
        ):
            raw_list = [parsed]
        else:
            raw_list = []

    cases = []
    for idx, raw in enumerate(raw_list, 1):
        if not isinstance(raw, dict):
            continue
        name = (
            raw.get("name")
            or raw.get("testCaseId")
            or raw.get("title")
            or f"测试用例 {idx}"
        )
        description = raw.get("description") or raw.get("summary") or ""
        steps_raw = raw.get("steps") or []
        steps = []
        if isinstance(steps_raw, list):
            for si, st in enumerate(steps_raw, 1):
                if isinstance(st, dict):
                    steps.append({
                        "step_number": st.get("step_number") or si,
                        "action": st.get("action") or st.get("description")
                        or st.get("step") or "",
                        "expected_result": st.get("expected_result")
                        or st.get("expectedResult") or st.get("expected") or "",
                        "parameters": st.get("parameters") or {},
                        "device_type": st.get("device_type"),
                    })
                elif isinstance(st, str):
                    steps.append({
                        "step_number": si,
                        "action": st,
                        "expected_result": "",
                        "parameters": {},
                        "device_type": None,
                    })
        expected_result = (
            raw.get("expected_result")
            or raw.get("expectedResult")
            or raw.get("expectedResults")
            or ""
        )
        parameters = raw.get("parameters") or {}
        devices_required = raw.get("devices_required") or raw.get("devicesRequired") or []
        tags = raw.get("tags") or []
        flow_description = (
            raw.get("flow_description")
            or raw.get("flowDescription")
            or description
        )
        cases.append({
            "name": name,
            "description": description,
            "steps": steps,
            "expected_result": expected_result,
            "parameters": parameters if isinstance(parameters, dict) else {},
            "devices_required": devices_required if isinstance(devices_required, list) else [],
            "tags": tags if isinstance(tags, list) else [],
            "flow_description": flow_description,
        })
    return {"test_cases": cases}


class AIService:
    """Unified AI service for local and cloud models."""

    # Providers whose APIs enforce exact model names.  Any value NOT in the list
    # (or, for list-check providers, any value that doesn't match one of them)
    # is rejected at save time so the user gets immediate feedback instead of an
    # opaque "400 Bad Request" error later during a test or chat.
    _PROVIDER_STRICT_MODEL_NAMES: Dict[str, List[str]] = {
        "deepseek": ["deepseek-v4-pro", "deepseek-v4-flash"],
    }

    def _validate_model_config(self, data: dict) -> None:
        """Reject configurations that cannot possibly connect.

        Checks:
        1. ``custom`` provider MUST have an explicit ``base_url``.
        2. Known providers with a strict model-name contract (e.g. DeepSeek)
           only accept the exact names listed in ``_PROVIDER_STRICT_MODEL_NAMES``.
        """
        provider = data.get("provider", "")
        model_name = data.get("model_name", "")

        # 1. custom provider needs a base_url
        if provider == "custom":
            base_url = data.get("base_url")
            if not base_url or not str(base_url).strip():
                raise ValueError(
                    "自定义 (custom) 供应商必须填写 Base URL（OpenAI 兼容接口地址）"
                )

        # 2. strict model name check
        if provider in self._PROVIDER_STRICT_MODEL_NAMES:
            valid = self._PROVIDER_STRICT_MODEL_NAMES[provider]
            if model_name and model_name not in valid:
                raise ValueError(
                    f"供应商 '{provider}' 仅接受以下模型名称: {', '.join(valid)}。"
                    f"当前值 '{model_name}' 无效，请修改后重试。"
                )

    async def configure_model(self, db: AsyncSession, data: dict) -> AIModelConfig:
        # Set api_key_encrypted separately from api_key field
        api_key = data.pop("api_key", None)
        parameters = data.pop("parameters", None)
        is_default = data.pop("is_default", False)

        self._validate_model_config(data)

        model = AIModelConfig(**data)
        if api_key:
            model.api_key_encrypted = api_key  # TODO: encrypt in production
        if parameters:
            model.parameters = json.dumps(parameters, ensure_ascii=False)

        # If this model is set as default, deactivate all others
        if is_default:
            model.is_default = True
            all_models = await self.list_models(db)
            for m in all_models:
                m.is_default = False

        db.add(model)
        await db.commit()
        await db.refresh(model)
        return model

    async def update_model(self, db: AsyncSession, model_id: str, data: dict) -> Optional[AIModelConfig]:
        model = await self.get_model(db, model_id)
        if not model:
            return None

        # Validate the effective configuration (provider may change to custom)
        effective = {
            "provider": data.get("provider", model.provider),
            "base_url": data.get("base_url", model.base_url),
        }
        self._validate_model_config(effective)

        for key, value in data.items():
            if key == "parameters" and value is not None:
                model.parameters = json.dumps(value, ensure_ascii=False)
            elif key == "api_key" and value is not None:
                model.api_key_encrypted = value
            elif value is not None:
                setattr(model, key, value)

        await db.commit()
        await db.refresh(model)
        return model

    async def list_models(self, db: AsyncSession) -> List[AIModelConfig]:
        result = await db.execute(select(AIModelConfig).order_by(AIModelConfig.created_at.desc()))
        return result.scalars().all()

    async def get_model(self, db: AsyncSession, model_id: str) -> Optional[AIModelConfig]:
        result = await db.execute(select(AIModelConfig).where(AIModelConfig.id == model_id))
        return result.scalar_one_or_none()

    async def get_active_model(self, db: AsyncSession) -> Optional[AIModelConfig]:
        result = await db.execute(
            select(AIModelConfig).where(AIModelConfig.is_default == True)
        )
        return result.scalar_one_or_none()

    async def set_active_model(self, db: AsyncSession, model_id: str) -> AIModelConfig:
        model = await self.get_model(db, model_id)
        if not model:
            raise AIModelNotFoundError(model_id)

        # Deactivate all models
        all_models = await self.list_models(db)
        for m in all_models:
            m.is_default = (m.id == model_id)
        await db.commit()

        return model

    async def delete_model(self, db: AsyncSession, model_id: str) -> bool:
        model = await self.get_model(db, model_id)
        if not model:
            return False
        await db.delete(model)
        await db.commit()
        return True

    def _get_provider(self, model: AIModelConfig) -> AIProvider:
        """Create an AI provider instance from model config."""
        params = {}
        if model.parameters:
            try:
                params = json.loads(model.parameters)
            except json.JSONDecodeError:
                pass

        return ai_provider_factory.create(
            provider=model.provider,
            model_name=model.model_name,
            api_key=model.api_key_encrypted,
            base_url=model.base_url,
            parameters=params,
        )

    async def test_model(self, db: AsyncSession, model_id: str) -> dict:
        """Test if a model is reachable and working.

        Returns ``{"model_id", "status", "error"}`` where ``error`` carries the
        concrete failure reason (e.g. invalid API key, wrong model name,
        unreachable host) so the user can fix the configuration.
        """
        model = await self.get_model(db, model_id)
        if not model:
            raise AIModelNotFoundError(model_id)

        try:
            provider = self._get_provider(model)
            is_ok = await provider.test_connection()
            error = getattr(provider, "last_error", None)

            # Reset status to active on success; mark error on failure
            model.status = "active" if is_ok else "error"
            model.last_tested_at = None  # Will be set on commit
            await db.commit()

            return {
                "model_id": model_id,
                "status": "ok" if is_ok else "failed",
                "error": error,
            }
        except Exception as e:
            model.status = "error"
            await db.commit()
            raise AICallError(model.provider, str(e))

    async def chat(
        self,
        db: AsyncSession,
        model_id: str,
        message: str,
        session_id: Optional[str] = None,
        system_prompt: Optional[str] = None,
        input_type: str = "text",
        skill_protocols: Optional[List[str]] = None,
    ) -> dict:
        model = await self.get_model(db, model_id)
        if not model:
            raise AIModelNotFoundError(model_id)

        # Attach plugin skills: explicitly imported ones + auto-detected from
        # the user's message (e.g. mentions "Mini Gateway 100").
        skill_context = _build_skill_context(
            skill_protocols, auto_detect_text=message
        )
        if skill_context:
            system_prompt = (
                f"{system_prompt}\n\n{skill_context}" if system_prompt else skill_context
            )

        # A chat session must have an id so history can be grouped; if the
        # client didn't supply one (e.g. the very first message), generate it.
        # This also satisfies the NOT NULL constraint on chat_history.session_id.
        if not session_id:
            session_id = generate_short_id("sess")

        # Reasoning models need headroom or long answers get truncated.
        provider = _provider_with_min_tokens(model, 16384)

        # Save user message
        chat_msg = ChatHistory(
            session_id=session_id,
            role="user",
            content=message,
            input_type=input_type,
        )
        db.add(chat_msg)

        # Build messages with history
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        if session_id:
            history_result = await db.execute(
                select(ChatHistory)
                .where(ChatHistory.session_id == session_id)
                .order_by(ChatHistory.created_at.desc())
                .limit(10)
            )
            history = history_result.scalars().all()
            for h in reversed(history):
                messages.append({"role": h.role, "content": h.content})

        if not messages or messages[-1].get("role") != "user":
            messages.append({"role": "user", "content": message})

        try:
            result = await provider.chat(messages)
        except Exception as e:
            logger.error(f"AI chat error ({model.provider}): {e}")
            raise AICallError(model.provider, str(e))

        # Save assistant response
        assistant_msg = ChatHistory(
            session_id=session_id,
            role="assistant",
            content=result["content"],
        )
        db.add(assistant_msg)
        await db.commit()

        return {
            "session_id": session_id,
            "response": result["content"],
            "usage": result.get("usage"),
        }

    async def generate_test_cases(
        self,
        db: AsyncSession,
        model_id: Optional[str],
        requirements: str,
        available_devices: Optional[List[Dict[str, Any]]] = None,
        skill_protocols: Optional[List[str]] = None,
    ) -> dict:
        # Use active model if none specified
        if model_id:
            model = await self.get_model(db, model_id)
        else:
            model = await self.get_active_model(db)

        if not model:
            raise AIModelNotFoundError(model_id or "default")

        # Reasoning models (DeepSeek-V4/R1) split max_tokens between
        # reasoning_content and the final content.  With a large system
        # prompt the model can exhaust most of the budget on reasoning,
        # leaving an empty or truncated JSON payload.  A generous floor
        # guarantees the model always has room for a complete answer.
        provider = _provider_with_min_tokens(model, 32768)

        system_prompt = """You are a test automation expert. Generate structured test cases as a single JSON object: {"test_cases": [...]}.

Each test case object: {name, description, steps, expected_result, parameters, devices_required, tags, flow_description}
Each step object: {step_number, action, expected_result, parameters, device_type?, flow_type?}

Flow node types:
- "action" (default): sequential step. No extra fields needed.
- "condition": if/else branch. Include "condition" (Python expr), "true_branch" (action), "false_branch" (action).
- "loop": repeating block. Include "loop_type" ("for"|"while"), "loop_variable" (for loop var name), "loop_expression" (range or while cond), "loop_body" (action description).

Output ONLY the JSON object. No markdown fences, no explanatory text. Preserve this exact top-level key: "test_cases" (array)."""

        # Attach plugin skills (explicit + auto-detected from requirements) so
        # generated test cases follow the device's real command protocol.
        skill_context = _build_skill_context(
            skill_protocols, auto_detect_text=requirements
        )
        if skill_context:
            system_prompt += f"\n\n{skill_context}"

        devices_info = ""
        if available_devices:
            devices_info = "\nAvailable devices:\n" + json.dumps(available_devices, indent=2)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Generate test cases for:\n{requirements}{devices_info}"},
        ]

        try:
            result = await provider.chat(messages)
            response_text = result["content"]
        except Exception as e:
            raise AICallError(model.provider, str(e))

        # Parse JSON from response (robust to fences / bare arrays / truncation)
        response_text = response_text or ""
        parsed_raw = _extract_json_object(response_text)
        if parsed_raw is None:
            logger.warning(
                "Failed to parse AI test-case response as JSON (len=%d); "
                "returning empty test_cases.",
                len(response_text),
            )
            parsed = {"test_cases": []}
        else:
            parsed = _normalize_test_cases(parsed_raw)

        return {
            "raw_response": response_text,
            "parsed": parsed,
            "usage": result.get("usage"),
        }

    async def natural_language_query(
        self,
        db: AsyncSession,
        model_id: Optional[str],
        query: str,
    ) -> dict:
        if model_id:
            model = await self.get_model(db, model_id)
        else:
            model = await self.get_active_model(db)

        if not model:
            raise AIModelNotFoundError(model_id or "default")

        # Reasoning models (DeepSeek-V4/R1) split max_tokens between
        # reasoning_content and the final content.  With a large system
        # prompt the model can exhaust most of the budget on reasoning,
        # leaving an empty or truncated JSON payload.  A generous floor
        # guarantees the model always has room for a complete answer.
        provider = _provider_with_min_tokens(model, 32768)

        schema_info = """
Database tables:
- devices(id, name, type, protocol, connection_type, status, visa_address, ip_address, connected_at, created_at)
- test_cases(id, name, description, requirement_raw, status, tags, created_at)
- test_flows(id, testcase_id, nodes, edges, created_at)
- test_executions(id, testcase_id, status, result, total_steps, passed_steps, failed_steps, started_at, completed_at, duration_ms, created_at)
- test_step_results(id, execution_id, step_index, node_id, node_type, label, status, command, expected, actual, duration_ms)
- communication_logs(id, timestamp, device_id, execution_id, direction, protocol, raw_data, status, duration_ms)
- test_reports(id, title, execution_id, format, status, created_at)
- ai_models(id, name, provider, model_name, is_default, status)
- plugins(id, name, version, protocol_type, status)
"""

        system_prompt = f"""You are a SQL query generator for SQLite. Given the schema and a natural language query, output ONLY the SQL query.

Schema:
{schema_info}

Rules:
1. Output ONLY the SQL query, no explanations
2. Use standard SQLite syntax
3. Use LIKE for fuzzy text matching
4. Limit results to 100 unless specified otherwise"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query},
        ]

        try:
            result = await provider.chat(messages)
            response_text = result["content"]
        except Exception as e:
            raise AICallError(model.provider, str(e))

        # Extract SQL
        sql = response_text.strip()
        sql_match = re.search(r'```sql\n?([\s\S]*?)```', response_text)
        if sql_match:
            sql = sql_match.group(1).strip()
        elif not sql.upper().startswith("SELECT"):
            # Try to find the SELECT statement
            select_match = re.search(r'(SELECT[\s\S]+?)(?:;|$)', response_text, re.IGNORECASE)
            if select_match:
                sql = select_match.group(1).strip()

        # Execute SQL safely
        try:
            from sqlalchemy import text
            result = await db.execute(text(sql))
            rows = result.fetchall()
            columns = list(result.keys())
            results_list = [dict(zip(columns, row)) for row in rows]

            return {
                "query": query,
                "sql_generated": sql,
                "results": results_list,
                "result_count": len(results_list),
                "explanation": f"Found {len(results_list)} results.",
            }
        except Exception as e:
            logger.error(f"SQL execution error: {e}")
            return {
                "query": query,
                "sql_generated": sql,
                "results": [],
                "result_count": 0,
                "explanation": f"Query execution failed: {str(e)}",
            }


ai_service = AIService()
