"""Verify the fix: call ai_service.generate_test_cases and inspect parsed output."""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

import app.models.models  # noqa: F401
from app.services.ai_service import ai_service

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "aitestlab.db")
DATABASE_URL = f"sqlite+aiosqlite:///{DB_PATH}"
engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def main():
    prompt = "通过mini Gateway 100发送每隔200ms发送一条CAN消息 0x850201,ID:0x13，并显示回复的消息。"
    async with AsyncSessionLocal() as db:
        result = await ai_service.generate_test_cases(
            db,
            model_id="model_c3751729",
            requirements=prompt,
            available_devices=[],
            skill_protocols=["mini_gateway100"],
        )
        print("RAW LEN:", len(result["raw_response"]))
        print("FINISH/EMPTY CHECK: raw empty?", result["raw_response"].strip() == "")
        print("TEST CASE COUNT:", len(result["parsed"].get("test_cases", [])))
        for i, tc in enumerate(result["parsed"].get("test_cases", []), 1):
            print(f"\n--- Case {i}: {tc.get('name')} ---")
            print("  desc:", (tc.get('description') or '')[:80])
            print("  steps:", len(tc.get('steps', [])))
            if tc.get('steps'):
                print("    step1:", tc['steps'][0])
            print("  expected:", (tc.get('expected_result') or '')[:80])


if __name__ == "__main__":
    asyncio.run(main())
