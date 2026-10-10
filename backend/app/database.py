import json
from datetime import datetime

from sqlalchemy import DateTime, String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from app.core.config import get_settings


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
    url = _database_url()
    kwargs = {"check_same_thread": False} if url.startswith("sqlite") else {}
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
