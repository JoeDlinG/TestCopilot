"""Database engine and session management."""
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base

from app.core.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    connect_args={"check_same_thread": False},
)


@event.listens_for(engine.sync_engine, "connect")
def _sqlite_pragmas(dbapi_conn, _connection_record):
    """Tune SQLite for a logging-heavy workload.

    Executed once per new connection:

    * ``WAL``      — readers never block the writer, so logging a burst of
      frames during a test run does not stall the UI polling the same DB;
    * ``NORMAL``   — safe with WAL (a crash can only lose the last txn) while
      removing an fsync per commit;
    * ``cache_size`` — ~16 MB page cache instead of the 2 MB default;
    * ``temp_store`` — keep sort/temp structures in memory.

    ``foreign_keys`` is deliberately left at SQLite's default (OFF): parts of
    the codebase delete parents before children in bulk and enabling it now
    would turn those into runtime errors.
    """
    cursor = dbapi_conn.cursor()
    for pragma in (
        "PRAGMA journal_mode=WAL",
        "PRAGMA synchronous=NORMAL",
        "PRAGMA cache_size=-16000",
        "PRAGMA temp_store=MEMORY",
    ):
        try:
            cursor.execute(pragma)
        except Exception:  # noqa: BLE001 - never fail startup on a pragma
            pass
    cursor.close()

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
    # Indexes left behind by ``index=True`` on model columns that are also
    # covered by an explicitly named ``idx_*`` index. They are byte-identical
    # duplicates: dropping them halves the index write amplification on the
    # communication-log hot path without changing any query plan.
    for index in (
        "ix_communication_logs_timestamp",
        "ix_communication_logs_device_id",
        "ix_communication_logs_execution_id",
    ):
        try:
            conn.execute(text(f"DROP INDEX IF EXISTS {index}"))
        except Exception:  # noqa: BLE001 - never fail startup on this
            pass

    added = []
    for table, column, decl in (
        ("test_step_results", "parsed_results", "TEXT"),
        # execution manager: batch linkage on existing single-run records
        ("test_executions", "plan_run_id", "TEXT"),
        ("test_executions", "plan_item_id", "TEXT"),
        ("test_executions", "iteration", "INTEGER"),
        ("test_executions", "group_no", "INTEGER"),
        ("execution_plan_items", "node_count", "INTEGER"),
        # stable, user-facing device identifier (see Device.device_key)
        ("devices", "device_key", "VARCHAR(64)"),
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

    _ensure_device_keys(conn)


def _ensure_device_keys(conn) -> None:
    """Give every device a stable, human-facing identifier (``DEV-001`` …).

    ``devices.id`` is a random primary key: deleting and re-adding a device
    hands out a new one, which orphaned every flow that pinned it. Flows now
    bind to ``device_key`` instead, so existing rows are backfilled here —
    ordered by creation time so the numbering is stable across restarts.
    """
    try:
        cols = [row[1] for row in conn.execute(text("PRAGMA table_info(devices)"))]
    except Exception:
        return
    if not cols or "device_key" not in cols:
        return

    try:
        pending = conn.execute(
            text(
                "SELECT id FROM devices "
                "WHERE device_key IS NULL OR TRIM(device_key) = '' "
                "ORDER BY created_at, id"
            )
        ).fetchall()
        if not pending:
            return
        used = {
            row[0]
            for row in conn.execute(
                text("SELECT device_key FROM devices WHERE device_key IS NOT NULL")
            ).fetchall()
        }
    except Exception:
        return

    seq = 1
    for (dev_id,) in pending:
        while f"DEV-{seq:03d}" in used:
            seq += 1
        key = f"DEV-{seq:03d}"
        used.add(key)
        conn.execute(
            text("UPDATE devices SET device_key = :k WHERE id = :i"),
            {"k": key, "i": dev_id},
        )
    print(f"[db] assigned device_key to {len(pending)} device(s)")


async def init_db():
    """Create all tables and apply pending column additions."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_apply_light_migrations)
