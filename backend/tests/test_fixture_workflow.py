from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import database
from app.main import app
from app.schemas import AnalysisResult, Chunk, FileInfo, Symbol
from app.services.analyzer import _static_findings


def test_controlled_snapshot_workflow_and_persistence(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("app.services.rag.configured_provider", lambda _settings: None)
    db_path = tmp_path / "fixture.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(database, "SessionLocal", sessionmaker(engine, expire_on_commit=False))

    source_text = "import os\n\ndef answer():\n    return 42\n"
    findings, tool_versions = _static_findings([("src/example.py", source_text)])
    snapshot = AnalysisResult(
        id="fixture-analysis",
        owner="example",
        name="fixture",
        url="https://github.com/example/fixture",
        commit_sha="a" * 40,
        default_branch="main",
        analyzed_at=datetime.now(UTC),
        status="completed",
        file_count=1,
        total_bytes=len(source_text.encode("utf-8")),
        languages={"Python": 1},
        files=[
            FileInfo(
                path="src/example.py",
                size=len(source_text.encode("utf-8")),
                language="Python",
                line_count=4,
            )
        ],
        symbols=[
            Symbol(
                name="answer",
                kind="function",
                path="src/example.py",
                start_line=3,
                end_line=4,
                summary="Return the fixture answer.",
            )
        ],
        findings=findings,
        chunks=[
            Chunk(
                path="src/example.py",
                language="Python",
                start_line=1,
                end_line=4,
                text=source_text,
            )
        ],
        skipped=[],
        tool_versions=tool_versions,
        duration_ms=1,
    )

    async def analyze_fixture(_url: str) -> AnalysisResult:
        return snapshot

    monkeypatch.setattr("app.main.analyze_repository", analyze_fixture)

    with TestClient(app) as client:
        created = client.post(
            "/api/analyses", json={"url": "https://github.com/example/fixture"}
        )
        assert created.status_code == 201
        analysis_id = created.json()["id"]
        assert created.json()["commit_sha"] == "a" * 40

        detail = client.get(f"/api/analyses/{analysis_id}").json()
        assert detail["file_count"] == 1
        assert detail["languages"] == {"Python": 1}
        assert detail["symbols"][0]["start_line"] == 3
        assert detail["symbols"][0]["end_line"] == 4

        tree = client.get(f"/api/analyses/{analysis_id}/files").json()
        assert tree["items"][0]["path"] == "src/example.py"
        preview = client.get(
            f"/api/analyses/{analysis_id}/file-content", params={"path": "src/example.py"}
        ).json()
        assert preview["chunks"][0]["text"].startswith("import os")

        findings_response = client.get(
            f"/api/analyses/{analysis_id}/findings", params={"source": "Ruff"}
        )
        assert findings_response.status_code == 200
        assert findings_response.json()["total"] >= 1
        assert findings_response.json()["items"][0]["source"] == "Ruff"
        assert any(
            item["rule_id"] == "F401" for item in findings_response.json()["items"]
        )

        answer = client.post(
            f"/api/analyses/{analysis_id}/ask", json={"question": "Where is answer defined?"}
        ).json()
        assert answer["retrieval_mode"] == "lexical"
        assert answer["generation_mode"] == "extractive_fallback"
        assert answer["provider_status"] == "not_configured"
        assert answer["evidence_sufficient"] is True
        assert answer["citations"] == [
            {
                "path": "src/example.py",
                "start_line": 1,
                "end_line": 4,
                "commit_sha": "a" * 40,
            }
        ]
        unknown = client.post(
            f"/api/analyses/{analysis_id}/ask", json={"question": "Unrelated astronomy topic"}
        ).json()
        assert unknown["citations"] == []
        assert "could not find enough" in unknown["answer"]
        assert unknown["evidence_sufficient"] is False
        assert unknown["generation_mode"] == "none"

        markdown = client.get(f"/api/analyses/{analysis_id}/report.md")
        assert markdown.status_code == 200
        assert "a" * 40 in markdown.text
        json_report = client.get(f"/api/analyses/{analysis_id}/report.json")
        assert json_report.status_code == 200
        assert json_report.json()["commit_sha"] == "a" * 40

    # Reopen the same SQLite file with a fresh engine to verify persisted history.
    engine.dispose()
    reopened_engine = create_engine(f"sqlite:///{db_path}")
    monkeypatch.setattr(database, "engine", reopened_engine)
    monkeypatch.setattr(
        database, "SessionLocal", sessionmaker(reopened_engine, expire_on_commit=False)
    )
    restored = database.get_analysis("fixture-analysis")
    assert restored is not None
    assert restored["commit_sha"] == "a" * 40
    assert restored["files"][0]["path"] == "src/example.py"
    reopened_engine.dispose()
