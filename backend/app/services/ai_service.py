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

from app.models.models import AIModelConfig, ChatHistory, TestCase, ChatInputType
from app.ai import ai_provider_factory, AIProvider
from app.core.exceptions import AIModelNotFoundError, AICallError

logger = logging.getLogger(__name__)


class AIService:
    """Unified AI service for local and cloud models."""

    async def configure_model(self, db: AsyncSession, data: dict) -> AIModelConfig:
        # Set api_key_encrypted separately from api_key field
        api_key = data.pop("api_key", None)
        parameters = data.pop("parameters", None)

        model = AIModelConfig(**data)
        if api_key:
            model.api_key_encrypted = api_key  # TODO: encrypt in production
        if parameters:
            model.parameters = json.dumps(parameters, ensure_ascii=False)
        db.add(model)
        await db.commit()
        await db.refresh(model)
        return model

    async def update_model(self, db: AsyncSession, model_id: str, data: dict) -> Optional[AIModelConfig]:
        model = await self.get_model(db, model_id)
        if not model:
            return None

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
        """Test if a model is reachable and working."""
        model = await self.get_model(db, model_id)
        if not model:
            raise AIModelNotFoundError(model_id)

        try:
            provider = self._get_provider(model)
            is_ok = await provider.test_connection()

            model.last_tested_at = None  # Will be set on commit
            await db.commit()

            return {"model_id": model_id, "status": "ok" if is_ok else "failed"}
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
    ) -> dict:
        model = await self.get_model(db, model_id)
        if not model:
            raise AIModelNotFoundError(model_id)

        provider = self._get_provider(model)

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
    ) -> dict:
        # Use active model if none specified
        if model_id:
            model = await self.get_model(db, model_id)
        else:
            model = await self.get_active_model(db)

        if not model:
            raise AIModelNotFoundError(model_id or "default")

        provider = self._get_provider(model)

        system_prompt = """You are a test automation expert. Generate structured test cases from the given requirements.
Output MUST be valid JSON in the following format:
{
    "test_cases": [
        {
            "name": "Test case name",
            "description": "Detailed description of what this test verifies",
            "steps": [
                {
                    "step_number": 1,
                    "action": "Specific action to perform (e.g., Set power supply to 12V)",
                    "expected_result": "Expected outcome of this step",
                    "parameters": {},
                    "device_type": "Type of device used (optional)"
                }
            ],
            "expected_result": "Overall expected test result",
            "parameters": {},
            "devices_required": ["power_supply", "multimeter"],
            "tags": ["functional", "voltage"],
            "flow_description": "Description of test flow suitable for flowchart creation"
        }
    ]
}
Generate comprehensive test cases covering normal, edge, and error scenarios."""

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

        # Parse JSON from response
        try:
            json_match = re.search(r'\{[\s\S]*\}', response_text)
            if json_match:
                parsed = json.loads(json_match.group())
            else:
                parsed = {"test_cases": []}
        except json.JSONDecodeError:
            logger.warning("Failed to parse AI response as JSON")
            parsed = {"test_cases": []}

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

        provider = self._get_provider(model)

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
