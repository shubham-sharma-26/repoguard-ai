from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from app.core.config import get_settings


def test_baseline_migration_upgrades_isolated_sqlite_database(tmp_path, monkeypatch) -> None:
    database_path = tmp_path / "migration-check.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database_path.as_posix()}")
    get_settings.cache_clear()
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))

    try:
        command.upgrade(config, "head")
    finally:
        get_settings.cache_clear()

    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    try:
        inspector = inspect(engine)
        assert "analysis_runs" in inspector.get_table_names()
        assert "alembic_version" in inspector.get_table_names()
        assert {index["name"] for index in inspector.get_indexes("analysis_runs")} >= {
            "ix_analysis_runs_owner",
            "ix_analysis_runs_name",
            "ix_analysis_runs_commit_sha",
            "ix_analysis_runs_status",
            "ix_analysis_runs_analyzed_at",
        }
    finally:
        engine.dispose()
