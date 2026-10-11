from datetime import UTC, datetime

import httpx
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_is_available() -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_unknown_analysis_is_not_found() -> None:
    response = client.get("/api/analyses/not-a-real-id")
    assert response.status_code == 404


def test_openapi_documents_api() -> None:
    response = client.get("/openapi.json")
    assert response.status_code == 200
    assert "/api/analyses/{analysis_id}/ask" in response.json()["paths"]
    assert "/api/analyses/{analysis_id}/file-content" in response.json()["paths"]


def test_unsupported_repository_url_is_rejected_before_network_access() -> None:
    response = client.post("/api/analyses", json={"url": "https://example.com/not/a/repository"})
    assert response.status_code == 422


def test_github_connection_failure_has_actionable_network_message(monkeypatch) -> None:
    async def fail(_url):
        raise httpx.ConnectError(
            "All connection attempts failed",
            request=httpx.Request("GET", "https://api.github.com/repos/octocat/Hello-World"),
        )

    monkeypatch.setattr("app.main.analyze_repository", fail)
    response = client.post("/api/analyses", json={"url": "https://github.com/octocat/Hello-World"})
    assert response.status_code == 502
    assert "secure connection to GitHub" in response.json()["detail"]
    assert "All connection attempts failed" not in response.json()["detail"]


def test_github_timeout_has_distinct_message(monkeypatch) -> None:
    async def fail(_url):
        raise httpx.ConnectTimeout(
            "timed out",
            request=httpx.Request("GET", "https://api.github.com/repos/octocat/Hello-World"),
        )

    monkeypatch.setattr("app.main.analyze_repository", fail)
    response = client.post("/api/analyses", json={"url": "https://github.com/octocat/Hello-World"})
    assert response.status_code == 504
    assert "timed out" in response.json()["detail"]


def test_repository_error_remains_distinct_from_connectivity(monkeypatch) -> None:
    from app.services.analyzer import AnalysisError

    async def fail(_url):
        raise AnalysisError("Repository was not found or is not publicly accessible.")

    monkeypatch.setattr("app.main.analyze_repository", fail)
    response = client.post("/api/analyses", json={"url": "https://github.com/octocat/does-not-exist"})
    assert response.status_code == 422
    assert "Repository was not found" in response.json()["detail"]


def test_unexpected_analysis_exception_does_not_log_exception_text(monkeypatch, caplog) -> None:
    async def fail(_url):
        raise RuntimeError("sentinel-secret-from-untrusted-error")

    monkeypatch.setattr("app.main.analyze_repository", fail)
    response = client.post(
        "/api/analyses", json={"url": "https://github.com/octocat/Hello-World"}
    )
    assert response.status_code == 502
    assert "sentinel-secret-from-untrusted-error" not in caplog.text
    assert "Repository analysis failed (RuntimeError)" in caplog.text


def test_api_responses_include_security_headers() -> None:
    response = client.get("/api/health")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"


def test_api_rejects_oversized_request_body() -> None:
    response = client.post(
        "/api/analyses",
        content=b"{}",
        headers={"Content-Length": "20000", "Content-Type": "application/json"},
    )
    assert response.status_code == 413


def test_history_returns_compact_summaries() -> None:
    response = client.get("/api/analyses")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def _analysis_payload() -> dict:
    return {
        "id": "snapshot-1",
        "owner": "octocat",
        "name": "sample",
        "url": "https://github.com/octocat/sample",
        "commit_sha": "a" * 40,
        "default_branch": "main",
        "analyzed_at": datetime.now(UTC).isoformat(),
        "status": "completed",
        "file_count": 1,
        "total_bytes": 10,
        "languages": {"Python": 1},
        "files": [{"path": "main.py", "size": 10, "language": "Python", "line_count": 1}],
        "symbols": [],
        "findings": [
            {
                "severity": "low",
                "rule_id": "F401",
                "title": "<script>alert(1)</script>",
                "message": "Unused import",
                "path": "main.py",
                "line": 1,
                "end_line": 1,
                "source": "Ruff",
                "evidence": "import secret_value",
            }
        ],
        "chunks": [
            {
                "path": "main.py",
                "language": "Python",
                "start_line": 1,
                "end_line": 1,
                "text": "print('hello')",
                "embedding": [0.5, 0.5],
                "embedding_model": "test-model",
            }
        ],
        "skipped": [],
        "tool_versions": {"ruff": "0.12.2", "bandit": "1.8.6"},
        "analysis_coverage": {
            "Python": "analyzed",
            "JavaScript": "not_analyzed",
            "TypeScript": "not_analyzed",
        },
        "duration_ms": 123,
    }


def test_file_preview_is_pinned_and_rejects_traversal(monkeypatch) -> None:
    monkeypatch.setattr("app.main.get_analysis", lambda _analysis_id: _analysis_payload())
    response = client.get("/api/analyses/snapshot-1/file-content?path=main.py")
    assert response.status_code == 200
    assert response.json()["chunks"][0]["text"] == "print('hello')"
    assert "embedding" not in response.json()["chunks"][0]
    unsafe = client.get("/api/analyses/snapshot-1/file-content?path=..%2Fsecrets.txt")
    assert unsafe.status_code == 422


def test_ask_drops_citations_from_another_commit(monkeypatch) -> None:
    monkeypatch.setattr("app.main.get_analysis", lambda _analysis_id: _analysis_payload())
    async def fake_answer(_analysis, _question):
        return {
            "answer": "Untrusted citation",
            "citations": [
                {
                    "path": "main.py",
                    "start_line": 1,
                    "end_line": 1,
                    "commit_sha": "b" * 40,
                }
            ],
            "mode": "lexical",
        }

    monkeypatch.setattr("app.main.answer_question", fake_answer)
    response = client.post(
        "/api/analyses/snapshot-1/ask", json={"question": "What is here?"}
    )
    assert response.status_code == 200
    assert response.json()["citations"] == []
    assert response.json()["evidence_sufficient"] is False
    assert "could not validate" in response.json()["answer"]


def test_ask_uses_requested_snapshot_and_drops_nonexistent_paths_and_ranges(monkeypatch) -> None:
    monkeypatch.setattr("app.main.get_analysis", lambda _analysis_id: _analysis_payload())
    received = []

    async def fake_answer(analysis, _question):
        received.append((analysis.id, analysis.commit_sha))
        return {
            "answer": "Untrusted citations",
            "citations": [
                {
                    "path": "missing.py",
                    "start_line": 1,
                    "end_line": 1,
                    "commit_sha": analysis.commit_sha,
                },
                {
                    "path": "main.py",
                    "start_line": 1,
                    "end_line": 2,
                    "commit_sha": analysis.commit_sha,
                },
            ],
            "mode": "lexical",
        }

    monkeypatch.setattr("app.main.answer_question", fake_answer)
    response = client.post("/api/analyses/snapshot-1/ask", json={"question": "What is here?"})

    assert response.status_code == 200
    assert received == [("snapshot-1", "a" * 40)]
    assert response.json()["citations"] == []
    assert response.json()["generation_mode"] == "none"
    assert response.json()["evidence_sufficient"] is False
    assert "Untrusted citations" not in response.json()["answer"]


def test_reports_escape_untrusted_markdown_and_omit_raw_source(monkeypatch) -> None:
    monkeypatch.setattr("app.main.get_analysis", lambda _analysis_id: _analysis_payload())
    report = client.get("/api/analyses/snapshot-1/report.md")
    assert report.status_code == 200
    assert "## Severity distribution" in report.text
    assert "## Static analysis coverage" in report.text
    assert "JavaScript: not analyzed" in report.text
    assert "&lt;script&gt;" in report.text
    assert "<script>" not in report.text
    json_report = client.get("/api/analyses/snapshot-1/report.json")
    assert json_report.status_code == 200
    assert "chunks" not in json_report.json()
    assert "test-model" not in json_report.text
