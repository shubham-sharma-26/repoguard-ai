import json
import logging
from datetime import datetime

from sqlalchemy import DateTime, String, Text, create_engine, select
from sqlalchemy import text as sql_text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from app.core.config import get_settings

logger = logging.getLogger("repoguard.database")


class Base(DeclarativeBase):
    pass


class AnalysisRecord(Base):
    __tablename__ = "analysis_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner: Mapped[str] = mapped_column(String(100), index=True)
    name: Mapped[str] = mapped_column(String(100), index=True)
    commit_sha: Mapped[str] = mapped_column(String(40), index=True)
    status: Mapped[str] = mapped_column(String(24), index=True)
    analyzed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    payload: Mapped[str] = mapped_column(Text)


def _database_url() -> str:
    return get_settings().database_url or "sqlite:///./repoguard.db"


def _make_engine():
    settings = get_settings()
    url = _database_url()
    kwargs = {"check_same_thread": False} if url.startswith("sqlite") else {}
    if url.startswith("postgresql"):
        timeout_seconds = max(1, min(90, int(settings.rag_request_timeout)))
        kwargs["connect_args"] = {
            "connect_timeout": timeout_seconds,
            "options": f"-c statement_timeout={timeout_seconds * 1000}",
        }
    return create_engine(url, connect_args=kwargs, pool_pre_ping=True)


engine = _make_engine()
SessionLocal = sessionmaker(engine, expire_on_commit=False)


def init_db() -> None:
    Base.metadata.create_all(engine)


def save_analysis(payload: dict) -> None:
    init_db()
    with SessionLocal.begin() as session:
        session.add(
            AnalysisRecord(
                id=payload["id"],
                owner=payload["owner"],
                name=payload["name"],
                commit_sha=payload["commit_sha"],
                status=payload["status"],
                analyzed_at=datetime.fromisoformat(payload["analyzed_at"].replace("Z", "+00:00")),
                payload=json.dumps(payload),
            )
        )
    if engine.dialect.name == "postgresql":
        try:
            _save_postgres_vectors(payload)
        except Exception as exc:
            logger.warning("pgvector storage unavailable (%s); persisted snapshot remains usable", type(exc).__name__)


def _vector_table(dimensions: int) -> str:
    if not 1 <= dimensions <= 4096:
        raise ValueError("Unsupported embedding dimensions")
    return f"repoguard_chunk_vectors_{dimensions}"


def _ensure_vector_table(dimensions: int) -> str:
    table = _vector_table(dimensions)
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS vector")
        connection.exec_driver_sql(
            f"CREATE TABLE IF NOT EXISTS {table} ("
            "analysis_id VARCHAR(36) NOT NULL, commit_sha VARCHAR(40) NOT NULL, "
            "chunk_index INTEGER NOT NULL, path TEXT NOT NULL, start_line INTEGER NOT NULL, "
            "end_line INTEGER NOT NULL, embedding_model VARCHAR(200) NOT NULL, "
            f"embedding vector({dimensions}) NOT NULL, "
            "PRIMARY KEY (analysis_id, commit_sha, chunk_index))"
        )
        connection.exec_driver_sql(
            f"CREATE INDEX IF NOT EXISTS ix_{table}_snapshot_model "
            f"ON {table} (analysis_id, commit_sha, embedding_model)"
        )
        if dimensions <= 2000:
            connection.exec_driver_sql(
                f"CREATE INDEX IF NOT EXISTS ix_{table}_cosine "
                f"ON {table} USING hnsw (embedding vector_cosine_ops)"
            )
    return table


def _save_postgres_vectors(payload: dict) -> None:
    chunks = payload.get("chunks", [])
    if not chunks:
        return
    embedded = [
        (index, chunk)
        for index, chunk in enumerate(chunks)
        if chunk.get("embedding") and chunk.get("embedding_model")
    ]
    if not embedded:
        return
    dimensions = len(embedded[0][1]["embedding"])
    table = _ensure_vector_table(dimensions)
    statement = sql_text(
        f"INSERT INTO {table} (analysis_id, commit_sha, chunk_index, path, start_line, "
        "end_line, embedding_model, embedding) VALUES (:analysis_id, :commit_sha, "
        ":chunk_index, :path, :start_line, :end_line, :embedding_model, "
        "CAST(:embedding AS vector)) ON CONFLICT (analysis_id, commit_sha, chunk_index) "
        "DO UPDATE SET path=EXCLUDED.path, start_line=EXCLUDED.start_line, "
        "end_line=EXCLUDED.end_line, embedding_model=EXCLUDED.embedding_model, "
        "embedding=EXCLUDED.embedding"
    )
    with engine.begin() as connection:
        for index, chunk in embedded:
            if len(chunk["embedding"]) != dimensions:
                continue
            connection.execute(
                statement,
                {
                    "analysis_id": payload["id"],
                    "commit_sha": payload["commit_sha"],
                    "chunk_index": index,
                    "path": chunk["path"],
                    "start_line": chunk["start_line"],
                    "end_line": chunk["end_line"],
                    "embedding_model": chunk["embedding_model"],
                    "embedding": "[" + ",".join(str(float(value)) for value in chunk["embedding"]) + "]",
                },
            )


def search_snapshot_vectors(
    analysis_id: str,
    commit_sha: str,
    embedding_model: str,
    query_vector: list[float],
    limit: int,
) -> dict[int, float] | None:
    """Return scoped cosine scores, or None when pgvector is not available/configured."""
    if engine.dialect.name != "postgresql":
        return None
    dimensions = len(query_vector)
    table = _vector_table(dimensions)
    try:
        with engine.connect() as connection:
            rows = connection.execute(
                sql_text(
                    f"SELECT chunk_index, 1 - (embedding <=> CAST(:query AS vector)) AS score "
                    f"FROM {table} WHERE analysis_id=:analysis_id AND commit_sha=:commit_sha "
                    "AND embedding_model=:embedding_model "
                    "ORDER BY embedding <=> CAST(:query AS vector) LIMIT :limit"
                ),
                {
                    "query": "[" + ",".join(str(float(value)) for value in query_vector) + "]",
                    "analysis_id": analysis_id,
                    "commit_sha": commit_sha,
                    "embedding_model": embedding_model,
                    "limit": max(1, min(limit, 20)),
                },
            )
            return {int(row.chunk_index): float(row.score) for row in rows}
    except Exception as exc:
        logger.info("pgvector query unavailable (%s); using snapshot cosine fallback", type(exc).__name__)
        return None


def get_analysis(analysis_id: str) -> dict | None:
    init_db()
    with SessionLocal() as session:
        record = session.get(AnalysisRecord, analysis_id)
        return json.loads(record.payload) if record else None


def list_analyses(limit: int = 50) -> list[dict]:
    init_db()
    with SessionLocal() as session:
        records = session.scalars(
            select(AnalysisRecord).order_by(AnalysisRecord.analyzed_at.desc()).limit(limit)
        )
        return [json.loads(record.payload) for record in records]
