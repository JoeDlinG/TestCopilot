"""Database engine and session management."""
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base

from app.core.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    connect_args={"check_same_thread": False},
)

async_session = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


Base = declarative_base()


async def get_db() -> AsyncSession:
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()


def _apply_light_migrations(conn):
    """Add columns introduced after the initial schema (SQLite has no migrator).

    ``create_all`` only creates missing *tables*, so new columns on existing
    databases must be added explicitly.
    """
    added = []
    for table, column, decl in (
        ("test_step_results", "parsed_results", "TEXT"),
        # execution manager: batch linkage on existing single-run records
        ("test_executions", "plan_run_id", "TEXT"),
        ("test_executions", "plan_item_id", "TEXT"),
        ("test_executions", "iteration", "INTEGER"),
        ("test_executions", "group_no", "INTEGER"),
        ("execution_plan_items", "node_count", "INTEGER"),
    ):
        try:
            cols = [row[1] for row in conn.execute(text(f"PRAGMA table_info({table})"))]
        except Exception:
            continue
        if cols and column not in cols:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {decl}"))
            added.append(f"{table}.{column}")
    if added:
        print(f"[db] schema updated: {', '.join(added)}")


async def init_db():
    """Create all tables and apply pending column additions."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_apply_light_migrations)
